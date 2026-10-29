"""Demo command contracts and HTTP integration journeys, not browser automation."""
import csv
import io
import os
import secrets
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditEvent
from incidents.models import Incident, IncidentAction, IncidentEvent, IncidentReport, IncidentRKEGAssessment
from incidents.rkeg_reporting import deadlines, evaluate_incident
from organizations.models import Organization
from risks.models import Risk, RiskControl, RiskMeasure
from services.models import CriticalService, Location, ServiceDependency
from .demo_data import ENERGY_NAME, LOGISTICS_NAME, SCENARIOS, USER_ROLES, demo_summary, seed_demo_data

FAST_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class DemoCommandTests(TestCase):
    def run_seed(self):
        output = io.StringIO()
        with patch.dict(os.environ, {'DEMO_PASSWORD': self.password}):
            call_command('seed_demo_data', stdout=output)
        self.assertNotIn(self.password, output.getvalue())
        return output.getvalue()

    def setUp(self):
        self.password = secrets.token_urlsafe(24)

    def test_password_required_without_writes(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesMessage(CommandError, 'DEMO_PASSWORD'):
            call_command('seed_demo_data')
        self.assertFalse(Organization.objects.exists())

    def test_whitespace_password_rejected(self):
        self.password = '   '
        with self.assertRaises(CommandError):
            self.run_seed()
        self.assertFalse(get_user_model().objects.exists())

    def test_command_creates_expected_counts(self):
        self.assertIn('angelegt', self.run_seed())
        self.assertEqual(demo_summary(list(Organization.objects.all())), {
            'Organisationen': 2, 'Benutzer': 5, 'Services': 4, 'Locations': 6,
            'Dependencies': 7, 'Risiken': 11, 'Controls': 8, 'RiskMeasures': 8,
            'Incidents': 6, 'IncidentEvents': 12, 'IncidentActions': 5,
            'Assessments': 6, 'Meldungsentwuerfe': 2, 'AuditEvents': 15,
        })

    def test_repeat_leaves_every_row_and_password_unchanged(self):
        self.run_seed()
        from django.apps import apps
        models = list(apps.get_models(include_auto_created=True))
        def snapshot():
            return {model._meta.label: list(model.objects.order_by('pk').values()) for model in models}
        before = snapshot()
        self.password = secrets.token_urlsafe(24)
        self.assertIn('bereits vorhanden', self.run_seed())
        self.assertEqual(snapshot(), before)

    def test_existing_unrelated_data_preserved(self):
        org = Organization.objects.create(name='Vorhandener Mandant', legal_name='Unveraendert')
        user = get_user_model().objects.create_user(username='existing', password=self.password)
        risk = Risk.objects.create(organization=org, created_by=user, title='Bestehendes Risiko')
        before = Risk.objects.filter(pk=risk.pk).values().get()
        self.run_seed()
        self.assertEqual(Risk.objects.filter(pk=risk.pk).values().get(), before)
        org.refresh_from_db()
        self.assertEqual(org.legal_name, 'Unveraendert')

    def test_existing_organization_name_collision_aborts(self):
        org = Organization.objects.create(name=ENERGY_NAME, legal_name='Echter Bestand')
        with self.assertRaises(CommandError):
            self.run_seed()
        self.assertEqual(Organization.objects.count(), 1)
        self.assertFalse(get_user_model().objects.exists())
        org.refresh_from_db()
        self.assertEqual(org.legal_name, 'Echter Bestand')

    def test_existing_username_collision_aborts(self):
        user = get_user_model().objects.create_user(username='demo_admin', password=self.password)
        before = user.password
        with self.assertRaises(CommandError):
            self.run_seed()
        user.refresh_from_db()
        self.assertEqual(user.password, before)
        self.assertFalse(Organization.objects.exists())

    def test_partial_dataset_not_silently_rebuilt(self):
        self.run_seed()
        RiskControl.objects.first().delete()
        with self.assertRaisesMessage(CommandError, 'unvollstaendig'):
            self.run_seed()
        self.assertEqual(RiskControl.objects.count(), 7)

    def test_user_edits_not_reset(self):
        self.run_seed()
        risk = Risk.objects.first()
        risk.title = 'Manuell bearbeitete Demo'
        risk.save()
        self.run_seed()
        risk.refresh_from_db()
        self.assertEqual(risk.title, 'Manuell bearbeitete Demo')

    def test_failure_rolls_back_entire_seed(self):
        with patch('core.demo_data.create_logistics', side_effect=RuntimeError('Test rollback')):
            with self.assertRaises(RuntimeError):
                self.run_seed()
        self.assertFalse(Organization.objects.exists())
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(AuditEvent.objects.exists())


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class DemoJourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = secrets.token_urlsafe(24)
        seed_demo_data(cls.password)
        cls.energy = Organization.objects.get(name=ENERGY_NAME)
        cls.logistics = Organization.objects.get(name=LOGISTICS_NAME)
        cls.risk = Risk.objects.filter(organization=cls.energy).order_by('pk').first()
        cls.service = CriticalService.objects.filter(organization=cls.energy).order_by('pk').first()
        cls.incident = Incident.objects.get(organization=cls.energy, title__contains='| A -')
        cls.control = RiskControl.objects.get(risk=cls.risk)
        cls.measure = RiskMeasure.objects.get(risk=cls.risk)
        cls.report = IncidentReport.objects.get(incident=cls.incident)
        cls.assessment = IncidentRKEGAssessment.objects.get(incident=cls.incident)
        cls.foreign_risk = Risk.objects.get(organization=cls.logistics)
        cls.foreign_service = CriticalService.objects.get(organization=cls.logistics)
        cls.foreign_incident = Incident.objects.get(organization=cls.logistics)
        cls.foreign_report = IncidentReport.objects.get(organization=cls.logistics)
        cls.foreign_assessment = IncidentRKEGAssessment.objects.get(organization=cls.logistics)

    def login(self, username='demo_admin'):
        response = self.client.post('/login/', {'username': username, 'password': self.password})
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

    def own_urls(self):
        return [
            '/dashboard/', reverse('services:detail', args=[self.service.pk]),
            reverse('risks:detail', args=[self.risk.pk]),
            reverse('risks:control-detail', args=[self.risk.pk, self.control.pk]),
            reverse('risks:measure-detail', args=[self.risk.pk, self.measure.pk]),
            reverse('incidents:detail', args=[self.incident.pk]),
            reverse('incidents:assessment-detail', args=[self.incident.pk, self.assessment.pk]),
            reverse('incidents:report-detail', args=[self.incident.pk, self.report.pk]),
            '/audit/', '/reports/management/',
        ]

    def write_urls(self):
        return [
            '/risks/new/', reverse('risks:edit', args=[self.risk.pk]),
            reverse('risks:control-edit', args=[self.risk.pk, self.control.pk]),
            reverse('risks:measure-edit', args=[self.risk.pk, self.measure.pk]),
            '/incidents/new/', reverse('incidents:edit', args=[self.incident.pk]),
            reverse('incidents:event-create', args=[self.incident.pk]),
            reverse('incidents:action-create', args=[self.incident.pk]),
            reverse('incidents:assessment-create', args=[self.incident.pk]),
            reverse('incidents:reporting-data', args=[self.incident.pk]),
            reverse('incidents:report-edit', args=[self.incident.pk, self.report.pk]),
            '/services/new/', '/services/locations/new/',
        ]

    def test_demo_roles_are_active_and_not_superusers(self):
        for username, role in USER_ROLES.items():
            user = get_user_model().objects.get(username=username)
            self.assertTrue(user.check_password(self.password))
            self.assertFalse(user.is_superuser or user.is_staff)
            membership = user.memberships.get()
            self.assertTrue(membership.is_active)
            self.assertEqual(membership.role, role)
            self.assertEqual(membership.organization_id, self.logistics.pk if username == 'demo_logistics' else self.energy.pk)

    def test_organization_and_service_configuration(self):
        self.assertTrue(self.energy.rkeg_classified)
        self.assertIn('FIKTIVER', self.energy.rkeg_classification_reference)
        from incidents.rkeg_rules import RULE_BY_CODE
        for service in CriticalService.objects.filter(organization=self.energy):
            self.assertIn(service.rkeg_service_code, RULE_BY_CODE)
            self.assertLessEqual(service.recovery_time_objective, service.maximum_tolerable_downtime)
            self.assertTrue(service.locations.exists())
            self.assertTrue(service.service_owner.memberships.filter(organization=self.energy, is_active=True).exists())
        self.assertEqual(Location.objects.filter(organization=self.energy).count(), 5)
        self.assertGreaterEqual(ServiceDependency.objects.filter(organization=self.energy, single_point_of_failure=True).count(), 2)
        self.assertTrue(ServiceDependency.objects.filter(organization=self.energy, contingency_available=False).exists())

    def test_demo_risk_scores_and_overdue_measures(self):
        risks = list(Risk.objects.filter(organization=self.energy))
        self.assertEqual(len(risks), 10)
        self.assertGreaterEqual(sum(r.risk_score >= 17 for r in risks), 2)
        self.assertGreaterEqual(sum(10 <= r.residual_risk_score <= 16 for r in risks), 2)
        self.assertTrue(any(r.residual_risk_score <= 4 for r in risks))
        self.assertEqual(RiskMeasure.objects.filter(organization=self.energy, due_date__lt=timezone.localdate()).exclude(status='IMPLEMENTED').count(), 2)

    def test_engine_scenarios_and_draft(self):
        for key, (_, expected) in SCENARIOS.items():
            incident = Incident.objects.get(organization=self.energy, title__contains=f'| {key} -')
            self.assertEqual(evaluate_incident(incident).result, expected)
            self.assertEqual(IncidentRKEGAssessment.objects.get(incident=incident).result, expected)
        self.assertIsNotNone(self.incident.rkeg_awareness_at)
        self.assertEqual(self.report.status, 'DRAFT')
        self.assertEqual(self.assessment.result, 'REPORTABLE')
        timing = deadlines(self.incident, evaluate_incident(self.incident))
        self.assertEqual(timing['initial_due_at'], self.incident.rkeg_awareness_at+timedelta(hours=24))

    def test_ended_threshold_intervals_are_exact_and_stable(self):
        exact = Incident.objects.get(organization=self.energy, title__contains='| B -')
        duration = (exact.disruption_ended_at-exact.disruption_started_at).total_seconds()/3600
        self.assertEqual(duration*exact.affected_metering_points, 250000)
        future = timezone.now()+timedelta(days=30)
        with patch('django.utils.timezone.now', return_value=future):
            self.assertEqual(evaluate_incident(exact).result, 'BELOW_THRESHOLD')
            manual = Incident.objects.get(organization=self.energy, title__contains='| D -')
            self.assertEqual(evaluate_incident(manual).result, 'MANUAL_REVIEW')

    def test_event_chronology_and_action_ownership(self):
        for incident in Incident.objects.filter(organization=self.energy, title__regex=r'\| [AB] -'):
            events = list(IncidentEvent.objects.filter(incident=incident).order_by('event_time'))
            self.assertEqual(len(events), 6)
            self.assertEqual(len({e.event_type for e in events}), 6)
            self.assertTrue(all(a.event_time < b.event_time for a, b in zip(events, events[1:])))
            self.assertTrue(all(e.organization_id == self.energy.pk for e in events))
        self.assertEqual(IncidentAction.objects.filter(organization=self.energy).count(), 5)

    def test_admin_complete_read_journey(self):
        self.login()
        for url in self.own_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'LOGISTIK EXKLUSIV')
        self.assertEqual(self.risk.risk_score, 25)
        self.assertEqual(self.risk.residual_risk_score, 16)
        detail = self.client.get(reverse('incidents:detail', args=[self.incident.pk]))
        for event in IncidentEvent.objects.filter(incident=self.incident):
            self.assertContains(detail, event.description)

    def test_login_csrf_and_logout(self):
        client = Client(enforce_csrf_checks=True)
        client.get('/login/')
        data = {'username': 'demo_admin', 'password': self.password}
        self.assertEqual(client.post('/login/', data).status_code, 403)
        data['csrfmiddlewaretoken'] = client.cookies['csrftoken'].value
        self.assertEqual(client.post('/login/', data).status_code, 302)
        self.assertEqual(client.get('/logout/').status_code, 405)
        self.assertEqual(client.post('/logout/', {'csrfmiddlewaretoken': client.cookies['csrftoken'].value}).status_code, 302)
        self.assertEqual(client.get('/dashboard/').status_code, 302)

    def test_viewer_complete_read_journey(self):
        self.login('demo_viewer')
        for url in self.own_urls():
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_viewer_cannot_write(self):
        self.login('demo_viewer')
        before = AuditEvent.objects.count()
        for url in self.write_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {'title': 'Manipulation'}).status_code, 403)
        self.assertEqual(AuditEvent.objects.count(), before)
        self.risk.refresh_from_db()
        self.assertNotEqual(self.risk.title, 'Manipulation')

    def test_viewer_reports_exports_and_prints(self):
        self.login('demo_viewer')
        for kind in ('risks', 'actions', 'services', 'incidents', 'rkeg'):
            self.assertEqual(self.client.get(f'/reports/{kind}/?format=csv').status_code, 200)
            self.assertEqual(self.client.get(f'/reports/{kind}/print/').status_code, 200)

    def test_both_matrix_modes_render_demo_data(self):
        self.login()
        for kind in ('gross', 'residual'):
            response = self.client.get('/risks/matrix/', {'type': kind})
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'LOGISTIK EXKLUSIV')

    def test_foreign_filter_ids_rejected_in_exports(self):
        self.login()
        for kind, field, value in (
            ('risks', 'service', self.foreign_service.pk),
            ('actions', 'responsible_user', get_user_model().objects.get(username='demo_logistics').pk),
        ):
            self.assertEqual(self.client.get(f'/reports/{kind}/', {field: value, 'format': 'csv'}).status_code, 400)

    def test_anonymous_redirects(self):
        for url in self.own_urls()+['/reports/risks/?format=csv', '/reports/management/print/']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn('/login/', response.url)

    def test_foreign_direct_urls_blocked(self):
        self.login()
        urls = [reverse('risks:detail', args=[self.foreign_risk.pk]),
                reverse('risks:edit', args=[self.foreign_risk.pk]),
                reverse('services:detail', args=[self.foreign_service.pk]),
                reverse('incidents:detail', args=[self.foreign_incident.pk]),
                reverse('incidents:edit', args=[self.foreign_incident.pk]),
                reverse('incidents:report-detail', args=[self.foreign_incident.pk, self.foreign_report.pk]),
                reverse('incidents:assessment-detail', args=[self.foreign_incident.pk, self.foreign_assessment.pk]),
                reverse('incidents:report-detail', args=[self.incident.pk, self.foreign_report.pk])]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        for name in ('edit', 'event-create', 'action-create', 'assessment-create', 'report-create'):
            self.assertEqual(self.client.post(reverse('incidents:'+name, args=[self.foreign_incident.pk]), {}).status_code, 404)

    def test_dashboard_only_energy_counts(self):
        self.login()
        response = self.client.get('/dashboard/', {'organization': self.logistics.pk})
        self.assertEqual(response.context['counts']['total'], 10)
        self.assertEqual(response.context['service_counts']['active'], 3)
        self.assertEqual(response.context['dependency_counts']['single_points'], 4)
        self.assertEqual(response.context['incident_counts']['critical'], 1)
        self.assertNotContains(response, 'LOGISTIK EXKLUSIV')

    def test_lists_and_audit_do_not_leak_foreign_data(self):
        self.login()
        for url in ('/risks/', '/incidents/', '/services/', '/services/locations/', '/audit/'):
            response = self.client.get(url, {'organization': self.logistics.pk})
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'LOGISTIK EXKLUSIV')
            self.assertNotContains(response, self.foreign_service.name)
            self.assertNotContains(response, LOGISTICS_NAME)

    def test_reports_print_views_and_management_counts(self):
        self.login()
        for kind in ('management', 'risks', 'actions', 'services', 'incidents', 'rkeg'):
            for suffix in ('', 'print/'):
                response = self.client.get(f'/reports/{kind}/{suffix}')
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, ENERGY_NAME)
                self.assertNotContains(response, 'LOGISTIK EXKLUSIV')
        metrics = dict(self.client.get('/reports/management/').context['metrics'])
        self.assertEqual(metrics['Risiken gesamt'], 10)
        self.assertEqual(metrics['Aktive Dienstleistungen'], 3)
        self.assertEqual(metrics['Single Points of Failure'], 4)

    def test_csv_exports_filled_and_tenant_scoped(self):
        self.login()
        for kind, count in (('risks', 10), ('actions', 13), ('services', 3), ('incidents', 5), ('rkeg', 5)):
            response = self.client.get(f'/reports/{kind}/', {'format': 'csv', 'organization': self.logistics.pk})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
            text = response.content.decode('utf-8-sig')
            rows = list(csv.reader(io.StringIO(text), delimiter=';'))
            self.assertEqual(len(rows), count+1, kind)
            self.assertIn(ENERGY_NAME, text)
            self.assertNotIn('LOGISTIK EXKLUSIV', text)
            self.assertNotIn(LOGISTICS_NAME, text)

    def test_logistics_sees_only_own_records(self):
        self.login('demo_logistics')
        response = self.client.get('/risks/')
        self.assertContains(response, self.foreign_risk.title)
        self.assertNotContains(response, self.risk.title)
        self.assertEqual(self.client.get('/dashboard/').context['counts']['total'], 1)
        self.assertEqual(self.client.get(reverse('incidents:detail', args=[self.incident.pk])).status_code, 404)

    def test_admin_risk_update_and_post_tampering(self):
        self.login()
        url = reverse('risks:edit', args=[self.risk.pk])
        form = self.client.get(url).context['form']
        data = {'title': self.risk.title, 'description': 'Demo-Bearbeitung', 'status': 'OPEN',
                'likelihood': 5, 'impact': 5, 'residual_likelihood': 4, 'residual_impact': 4,
                'treatment_strategy': 'REDUCE', 'organization_context': form['organization_context'].value(),
                'critical_services': [self.foreign_service.pk]}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('critical_services', response.context['form'].errors)
        data.update(critical_services=[self.service.pk], organization=self.logistics.pk,
                    created_by=get_user_model().objects.get(username='demo_logistics').pk, risk_score=1, residual_risk_score=1)
        creator = self.risk.created_by_id
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.risk.refresh_from_db()
        self.assertEqual(self.risk.organization_id, self.energy.pk)
        self.assertEqual(self.risk.created_by_id, creator)
        self.assertEqual(self.risk.description, 'Demo-Bearbeitung')
        self.assertEqual(self.risk.risk_score, 25)
        self.assertEqual(self.risk.residual_risk_score, 16)
