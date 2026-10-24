from datetime import timedelta
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.test_helpers import TenantTestCase
from organizations.models import Membership
from risks.models import Risk
from .models import Incident, IncidentAction, IncidentEvent


class IncidentTestCase(TenantTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.occurred = timezone.now().replace(second=0, microsecond=0) - timedelta(days=1)
        cls.incident = Incident.objects.create(
            organization=cls.organization, created_by=cls.user, title='Stromausfall Zentrale',
            description='Unterbrechung im Rechenzentrum', impact_description='Pumpen ausgefallen',
            occurred_at=cls.occurred, detected_at=cls.occurred + timedelta(minutes=5),
            incident_type=Incident.IncidentType.TECHNICAL,
        )
        cls.foreign = Incident.objects.create(
            organization=cls.other_organization, created_by=cls.other_user, title='Fremder Vorfall',
            description='Vertrauliche Beschreibung', impact_description='Geheime Auswirkungen',
            occurred_at=cls.occurred, detected_at=cls.occurred, severity=5,
            reporting_status=Incident.ReportingStatus.UNDER_REVIEW,
        )
        cls.event = IncidentEvent.objects.create(incident=cls.incident, event_time=cls.occurred,
            event_type=IncidentEvent.EventType.DETECTION, description='Eigener Eintrag', created_by=cls.user)
        cls.foreign_event = IncidentEvent.objects.create(incident=cls.foreign, event_time=cls.occurred,
            description='Fremder Eintrag', created_by=cls.other_user)
        cls.action = IncidentAction.objects.create(incident=cls.incident, title='Notversorgung')
        cls.foreign_action = IncidentAction.objects.create(incident=cls.foreign, title='Fremde Sofortmassnahme')

    def incident_url(self, action='detail', incident=None):
        args = [] if action in ('list', 'create') else [(incident or self.incident).pk]
        return reverse(f'incidents:{action}', args=args)

    def child_url(self, action, incident=None, child=None):
        args = [(incident or self.incident).pk]
        if action == 'action-edit':
            args.append((child or self.action).pk)
        return reverse(f'incidents:{action}', args=args)

    def incident_payload(self, url=None, **overrides):
        url = url or self.incident_url('create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = {
            'title': 'Neuer Vorfall', 'description': 'Beschreibung', 'impact_description': 'Auswirkungen',
            'occurred_at': timezone.localtime(self.occurred).strftime('%Y-%m-%dT%H:%M'),
            'detected_at': timezone.localtime(self.occurred + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M'),
            'status': Incident.Status.NEW, 'severity': 2, 'incident_type': Incident.IncidentType.OTHER,
            'reporting_status': Incident.ReportingStatus.NOT_ASSESSED,
            'responsible_user': '', 'risks': [],
            'organization_context': response.context['form']['organization_context'].value(),
        }
        data.update(overrides)
        return data

    def event_payload(self, **overrides):
        data = {'event_time': timezone.localtime(self.occurred).strftime('%Y-%m-%dT%H:%M'),
                'event_type': IncidentEvent.EventType.ACTION, 'description': 'Neue Chronologie'}
        data.update(overrides)
        return data

    def action_payload(self, **overrides):
        data = {'title': 'Neue Sofortmassnahme', 'description': 'Beschreibung',
                'status': IncidentAction.Status.OPEN, 'responsible_user': '', 'due_date': '', 'completed_at': ''}
        data.update(overrides)
        return data


class IncidentModelTests(IncidentTestCase):
    def test_defaults_and_strings(self):
        self.assertEqual(str(self.incident), 'Stromausfall Zentrale')
        self.assertEqual(self.incident.status, Incident.Status.NEW)
        self.assertEqual(self.incident.reporting_status, Incident.ReportingStatus.NOT_ASSESSED)
        self.assertFalse(self.incident.suspected_reportable)
        self.assertEqual(self.event.organization, self.organization)
        self.assertEqual(self.action.organization, self.organization)
        self.assertIn(self.incident.title, str(self.event))
        self.assertEqual(str(self.action), 'Notversorgung')

    def test_detection_must_not_precede_occurrence(self):
        self.incident.detected_at = self.occurred - timedelta(seconds=1)
        with self.assertRaises(ValidationError):
            self.incident.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Incident.objects.filter(pk=self.incident.pk).update(detected_at=self.incident.detected_at)
        self.incident.detected_at = self.occurred
        self.incident.save()

    def test_severity_validation_and_no_automatic_reporting(self):
        for severity in (0, 6):
            self.incident.severity = severity
            with self.assertRaises(ValidationError):
                self.incident.save()
            with self.assertRaises(IntegrityError), transaction.atomic():
                Incident.objects.filter(pk=self.incident.pk).update(severity=severity)
        self.incident.severity = 5
        self.incident.suspected_reportable = True
        self.incident.save()
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.reporting_status, Incident.ReportingStatus.NOT_ASSESSED)

    def test_responsible_validation_in_models(self):
        for obj in (self.incident, self.action):
            obj.responsible_user = self.other_user
            with self.assertRaises(ValidationError):
                obj.save()

    def test_children_reject_mismatched_organization(self):
        for obj in (self.event, self.action):
            obj.organization = self.other_organization
            with self.assertRaises(ValidationError):
                obj.save()

    def test_incident_organization_cannot_change(self):
        self.incident.organization = self.other_organization
        with self.assertRaises(ValidationError):
            self.incident.save()

    def test_m2m_validation_in_both_directions(self):
        self.incident.risks.add(self.risk)
        with self.assertRaises(ValidationError), transaction.atomic():
            self.incident.risks.add(self.other_risk)
        with self.assertRaises(ValidationError), transaction.atomic():
            self.other_risk.incidents.add(self.incident)
        self.assertEqual(list(self.incident.risks.all()), [self.risk])

    def test_m2m_set_rejects_foreign_risk_atomically(self):
        self.incident.risks.add(self.risk)
        with self.assertRaises(ValidationError), transaction.atomic():
            self.incident.risks.set([self.other_risk])
        self.assertEqual(list(self.incident.risks.all()), [self.risk])

    def test_linked_risk_cannot_move_organization(self):
        self.incident.risks.add(self.risk)
        self.risk.organization = self.other_organization
        with self.assertRaises(ValidationError):
            self.risk.save()

    def test_action_completion_time_requires_done(self):
        self.action.completed_at = self.occurred
        with self.assertRaises(ValidationError):
            self.action.save()
        self.action.status = IncidentAction.Status.DONE
        self.action.save()
        self.action.refresh_from_db()
        self.assertEqual(self.action.completed_at, self.occurred)


class IncidentViewTests(IncidentTestCase):
    def test_create_assigns_organization_and_creator(self):
        response = self.client.post(self.incident_url('create'), self.incident_payload(
            organization=self.other_organization.pk, created_by=self.other_user.pk,
            responsible_user=self.user.pk, risks=[self.risk.pk], id=self.foreign.pk))
        created = Incident.objects.get(title='Neuer Vorfall')
        self.assertRedirects(response, self.incident_url(incident=created))
        self.assertEqual(created.organization, self.organization)
        self.assertEqual(created.created_by, self.user)
        self.assertEqual(created.responsible_user, self.user)
        self.assertEqual(created.occurred_at, self.occurred)
        self.assertEqual(list(created.risks.all()), [self.risk])
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.title, 'Fremder Vorfall')

    def test_edit_cannot_change_organization_or_creator(self):
        self.incident.created_by = self.other_user
        self.incident.save()
        url = self.incident_url('edit')
        response = self.client.post(url, self.incident_payload(url, organization=self.other_organization.pk,
                                                              created_by=self.user.pk, id=self.foreign.pk))
        self.assertEqual(response.status_code, 302)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.organization, self.organization)
        self.assertEqual(self.incident.created_by, self.other_user)

    def test_list_and_detail_do_not_expose_foreign_data(self):
        self.incident.risks.add(self.risk)
        self.foreign.risks.add(self.other_risk)
        for url in (self.incident_url('list'), self.incident_url()):
            response = self.client.get(url)
            self.assertContains(response, self.incident.title)
            for text in (self.foreign.title, self.other_risk.title, self.foreign_event.description, self.foreign_action.title):
                self.assertNotContains(response, text)

    def test_foreign_detail_and_edit_blocked(self):
        for action in ('detail', 'edit'):
            url = self.incident_url(action, self.foreign)
            self.assertEqual(self.client.get(url).status_code, 404)
            if action == 'edit':
                self.assertEqual(self.client.post(url, {'title': 'Manipuliert'}).status_code, 404)

    def test_viewer_can_read_only(self):
        self.set_role(Membership.Role.VIEWER)
        response = self.client.get(self.incident_url())
        self.assertContains(response, self.incident.title)
        self.assertContains(response, self.event.description)
        self.assertContains(response, self.action.title)
        self.assertNotContains(response, self.incident_url('edit'))
        self.assertEqual(self.client.get(self.incident_url('list')).status_code, 200)
        for action in ('create', 'edit'):
            self.assertEqual(self.client.get(self.incident_url(action)).status_code, 403)
            self.assertEqual(self.client.post(self.incident_url(action), {'title': 'Manipuliert'}).status_code, 403)
        self.assertEqual(Incident.objects.count(), 2)

    def test_all_write_roles_can_create_and_edit(self):
        for role in (Membership.Role.ADMIN, Membership.Role.RESILIENCE_MANAGER,
                     Membership.Role.RISK_MANAGER, Membership.Role.EDITOR):
            self.set_role(role)
            self.assertEqual(self.client.post(self.incident_url('create'), self.incident_payload(title=role)).status_code, 302)
            url = self.incident_url('edit')
            self.assertEqual(self.client.post(url, self.incident_payload(url, title=f'Updated {role}')).status_code, 302)
            self.incident.refresh_from_db()
            self.assertEqual(self.incident.title, f'Updated {role}')

    def test_foreign_risks_rejected_on_create_and_edit(self):
        self.incident.risks.add(self.risk)
        for url in (self.incident_url('create'), self.incident_url('edit')):
            response = self.client.post(url, self.incident_payload(url, risks=[self.risk.pk, self.other_risk.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertIn('risks', response.context['form'].errors)
            self.assertNotContains(response, self.other_risk.title)
        self.assertEqual(Incident.objects.count(), 2)
        self.assertEqual(list(self.incident.risks.all()), [self.risk])

    def test_active_second_membership_does_not_allow_foreign_risk(self):
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.ADMIN)
        self.select_organization(self.organization)
        self.test_foreign_risks_rejected_on_create_and_edit()
        self.test_foreign_detail_and_edit_blocked()

    def test_foreign_inactive_disabled_responsible_user_rejected(self):
        for action in ('create', 'edit'):
            url = self.incident_url(action)
            response = self.client.post(url, self.incident_payload(url, responsible_user=self.other_user.pk))
            self.assertIn('responsible_user', response.context['form'].errors)
        membership = Membership.objects.create(user=self.other_user, organization=self.organization, is_active=False)
        response = self.client.post(self.incident_url('create'), self.incident_payload(responsible_user=self.other_user.pk))
        self.assertIn('responsible_user', response.context['form'].errors)
        membership.is_active = True
        membership.save()
        self.other_user.is_active = False
        self.other_user.save()
        response = self.client.post(self.incident_url('create'), self.incident_payload(responsible_user=self.other_user.pk))
        self.assertIn('responsible_user', response.context['form'].errors)

    def test_invalid_datetime_and_enum_values(self):
        for values in ({'detected_at': '2000-01-01T00:00'}, {'severity': 6}, {'status': 'INVALID'},
                       {'reporting_status': 'INVALID'}, {'occurred_at': ''}, {'incident_type': 'INVALID'}):
            response = self.client.post(self.incident_url('create'), self.incident_payload(**values))
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(Incident.objects.count(), 2)

    def test_stale_or_forged_organization_context(self):
        data = self.incident_payload()
        response = self.client.post(self.incident_url('create'), {**data, 'organization_context': 'forged'})
        self.assertIn('organization_context', response.context['form'].errors)
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.ADMIN)
        self.select_organization(self.other_organization)
        response = self.client.post(self.incident_url('create'), data)
        self.assertIn('organization_context', response.context['form'].errors)
        self.assertEqual(Incident.objects.count(), 2)

    def test_role_and_membership_revocation_rechecked_on_submit(self):
        data = self.incident_payload()
        self.set_role(Membership.Role.VIEWER)
        self.assertEqual(self.client.post(self.incident_url('create'), data).status_code, 403)
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.client.post(self.incident_url('create'), data, follow=True).status_code, 403)

    def test_anonymous_internal_pages_redirect(self):
        self.client.logout()
        urls = [self.incident_url(action) for action in ('list', 'create', 'detail', 'edit')]
        urls += [self.child_url(action) for action in ('event-create', 'action-create', 'action-edit')]
        for url in urls:
            for method in ('get', 'post'):
                self.assertRedirects(getattr(self.client, method)(url), f'/login/?next={url}', fetch_redirect_response=False)

    def test_mutations_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        urls = [self.incident_url('create'), self.incident_url('edit')]
        urls += [self.child_url(action) for action in ('event-create', 'action-create', 'action-edit')]
        for url in urls:
            self.assertEqual(client.post(url, {}).status_code, 403)

    def test_content_is_escaped(self):
        self.incident.description = '<script>alert(1)</script>'
        self.incident.save()
        response = self.client.get(self.incident_url())
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;')

    def test_admin_is_superuser_read_only(self):
        self.user.is_staff = True
        self.user.save()
        for model in ('incident', 'incidentevent', 'incidentaction'):
            self.assertEqual(self.client.get(reverse(f'admin:incidents_{model}_changelist')).status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        for model, obj in (('incident', self.incident), ('incidentevent', self.event), ('incidentaction', self.action)):
            self.assertEqual(self.client.get(reverse(f'admin:incidents_{model}_changelist')).status_code, 200)
            self.assertEqual(self.client.get(reverse(f'admin:incidents_{model}_change', args=[obj.pk])).status_code, 200)
            self.assertEqual(self.client.post(reverse(f'admin:incidents_{model}_add'), {}).status_code, 403)
            self.assertEqual(self.client.post(reverse(f'admin:incidents_{model}_change', args=[obj.pk]), {}).status_code, 403)


class IncidentChildTests(IncidentTestCase):
    def test_event_creation_sets_parent_organization_creator(self):
        data = self.event_payload(organization=self.other_organization.pk, incident=self.foreign.pk,
                                  created_by=self.other_user.pk, id=self.foreign_event.pk)
        response = self.client.post(self.child_url('event-create'), data)
        self.assertRedirects(response, self.incident_url())
        event = IncidentEvent.objects.latest('pk')
        self.assertEqual(event.incident, self.incident)
        self.assertEqual(event.organization, self.organization)
        self.assertEqual(event.created_by, self.user)
        self.assertEqual(event.event_time, self.occurred)

    def test_foreign_incident_event_and_action_create_blocked(self):
        for action, data in (('event-create', self.event_payload()), ('action-create', self.action_payload())):
            url = self.child_url(action, self.foreign)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, data).status_code, 404)

    def test_action_create_and_edit_ignore_parent_manipulation(self):
        for action in ('action-create', 'action-edit'):
            data = self.action_payload(organization=self.other_organization.pk, incident=self.foreign.pk,
                                       id=self.foreign_action.pk, responsible_user=self.user.pk)
            response = self.client.post(self.child_url(action), data)
            self.assertEqual(response.status_code, 302)
            obj = IncidentAction.objects.latest('pk') if action == 'action-create' else IncidentAction.objects.get(pk=self.action.pk)
            self.assertEqual(obj.incident, self.incident)
            self.assertEqual(obj.organization, self.organization)
            self.assertEqual(obj.responsible_user, self.user)
        self.foreign_action.refresh_from_db()
        self.assertEqual(self.foreign_action.title, 'Fremde Sofortmassnahme')

    def test_foreign_action_edit_and_wrong_parent_blocked(self):
        for incident in (self.incident, self.foreign):
            url = self.child_url('action-edit', incident, self.foreign_action)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, self.action_payload()).status_code, 404)

    def test_wrong_parent_in_same_organization_blocked(self):
        another = Incident.objects.create(organization=self.organization, created_by=self.user, title='Anderer Vorfall',
            description='Text', impact_description='Text', occurred_at=self.occurred, detected_at=self.occurred)
        self.assertEqual(self.client.post(self.child_url('action-edit', another), self.action_payload()).status_code, 404)

    def test_viewer_cannot_write_events_or_actions(self):
        self.set_role(Membership.Role.VIEWER)
        for action, data in (('event-create', self.event_payload()), ('action-create', self.action_payload()),
                             ('action-edit', self.action_payload())):
            self.assertEqual(self.client.get(self.child_url(action)).status_code, 403)
            self.assertEqual(self.client.post(self.child_url(action), data).status_code, 403)
        self.assertEqual(IncidentEvent.objects.count(), 2)
        self.assertEqual(IncidentAction.objects.count(), 2)

    def test_all_write_roles_can_create_events_and_manage_actions(self):
        for role in (Membership.Role.ADMIN, Membership.Role.RESILIENCE_MANAGER,
                     Membership.Role.RISK_MANAGER, Membership.Role.EDITOR):
            self.set_role(role)
            for action, data in (('event-create', self.event_payload()), ('action-create', self.action_payload()),
                                 ('action-edit', self.action_payload(status=IncidentAction.Status.DONE,
                                  completed_at=timezone.localtime(self.occurred).strftime('%Y-%m-%dT%H:%M')))):
                self.assertEqual(self.client.get(self.child_url(action)).status_code, 200)
                self.assertEqual(self.client.post(self.child_url(action), data).status_code, 302)
            self.action.refresh_from_db()
            self.assertEqual(self.action.status, IncidentAction.Status.DONE)
            self.assertEqual(self.action.completed_at, self.occurred)

    def test_action_foreign_responsible_user_rejected(self):
        for action in ('action-create', 'action-edit'):
            response = self.client.post(self.child_url(action), self.action_payload(responsible_user=self.other_user.pk))
            self.assertIn('responsible_user', response.context['form'].errors)

    def test_action_inactive_membership_and_user_rejected(self):
        membership = Membership.objects.create(user=self.other_user, organization=self.organization, is_active=False)
        response = self.client.post(self.child_url('action-create'), self.action_payload(responsible_user=self.other_user.pk))
        self.assertIn('responsible_user', response.context['form'].errors)
        membership.is_active = True
        membership.save()
        self.other_user.is_active = False
        self.other_user.save()
        response = self.client.post(self.child_url('action-create'), self.action_payload(responsible_user=self.other_user.pk))
        self.assertIn('responsible_user', response.context['form'].errors)

    def test_chronology_sorted_by_event_time_not_creation(self):
        later = IncidentEvent.objects.create(incident=self.incident, event_time=self.occurred + timedelta(hours=2),
                                            description='Spaeter', created_by=self.user)
        earlier = IncidentEvent.objects.create(incident=self.incident, event_time=self.occurred - timedelta(hours=2),
                                              description='Frueher', created_by=self.user)
        response = self.client.get(self.incident_url())
        self.assertEqual(list(response.context['events']), [earlier, self.event, later])

    def test_organization_switch_rejects_stale_child_urls(self):
        Membership.objects.create(user=self.user, organization=self.other_organization, role=Membership.Role.ADMIN)
        self.select_organization(self.other_organization)
        for action, data in (('event-create', self.event_payload()), ('action-create', self.action_payload()),
                             ('action-edit', self.action_payload())):
            self.assertEqual(self.client.post(self.child_url(action), data).status_code, 404)

    def test_invalid_event_and_action_fields(self):
        response = self.client.post(self.child_url('event-create'), self.event_payload(event_type='INVALID'))
        self.assertIn('event_type', response.context['form'].errors)
        response = self.client.post(self.child_url('event-create'), self.event_payload(event_time='invalid'))
        self.assertIn('event_time', response.context['form'].errors)
        response = self.client.post(self.child_url('action-create'), self.action_payload(status='INVALID'))
        self.assertIn('status', response.context['form'].errors)
        response = self.client.post(self.child_url('action-create'), self.action_payload(completed_at='2026-01-01T12:00'))
        self.assertIn('completed_at', response.context['form'].errors)


class IncidentDashboardAndFilterTests(IncidentTestCase):
    def results(self, **params):
        response = self.client.get('/incidents/', params)
        self.assertEqual(response.status_code, 200)
        return list(response.context['incidents'])

    def test_search_title(self):
        self.assertEqual(self.results(q='STROM'), [self.incident])

    def test_search_description(self):
        self.assertEqual(self.results(q='Rechenzentrum'), [self.incident])

    def test_search_impact(self):
        self.assertEqual(self.results(q='Pumpen'), [self.incident])

    def test_search_foreign_data_returns_nothing(self):
        for text in (self.foreign.title, self.foreign.description, self.foreign.impact_description):
            self.assertEqual(self.results(q=text), [])

    def test_status_filter(self):
        self.assertEqual(self.results(status='new'), [self.incident])
        self.assertEqual(self.results(status='CLOSED'), [])

    def test_severity_filter(self):
        self.assertEqual(self.results(severity=2), [self.incident])
        self.assertEqual(self.results(severity=5), [])

    def test_reporting_status_filter(self):
        self.assertEqual(self.results(reporting_status='NOT_ASSESSED'), [self.incident])
        self.assertEqual(self.results(reporting_status='UNDER_REVIEW'), [])

    def test_type_and_combined_filters(self):
        self.assertEqual(self.results(incident_type='TECHNICAL'), [self.incident])
        self.assertEqual(self.results(q='Strom', status='NEW', severity=2, incident_type='TECHNICAL',
                                     reporting_status='NOT_ASSESSED'), [self.incident])
        self.assertEqual(self.results(status='CLOSED', severity=2), [])

    def test_invalid_filters_and_sorting_are_safe(self):
        self.assertEqual(self.results(status='NEW', severity='not-a-number', sort='created_by__password'), [self.incident])
        self.assertEqual(self.results(organization=self.other_organization.pk), [self.incident])

    def test_sorting(self):
        second = Incident.objects.create(organization=self.organization, created_by=self.user, title='Alpha',
            description='Text', impact_description='Text', occurred_at=self.occurred + timedelta(hours=1),
            detected_at=self.occurred + timedelta(hours=1), severity=5)
        for sort in ('title', 'severity_desc', 'newest', 'updated', 'occurred'):
            self.assertEqual(self.results(sort=sort), [second, self.incident])
        self.assertEqual(self.results(sort='severity_asc'), [self.incident, second])

    def test_pagination_preserves_get_filters(self):
        Incident.objects.bulk_create([
            Incident(organization=self.organization, created_by=self.user, title=f'Strom {i}',
                     description='Text', impact_description='Text', occurred_at=self.occurred, detected_at=self.occurred)
            for i in range(26)
        ])
        response = self.client.get('/incidents/?q=Strom&status=NEW&sort=title')
        self.assertContains(response, '?q=Strom&amp;status=NEW&amp;sort=title&amp;page=2')
        response = self.client.get('/incidents/?q=Strom&status=NEW&sort=title&page=2')
        self.assertEqual(len(response.context['incidents']), 2)
        self.assertNotContains(response, self.foreign.title)

    def test_register_query_survives_edit(self):
        query = urlencode({'q': 'Strom', 'sort': 'title'})
        url = self.incident_url('edit') + '?' + urlencode({'register': query})
        response = self.client.post(url, self.incident_payload(url))
        self.assertRedirects(response, self.incident_url() + '?' + urlencode({'register': query}))

    def test_dashboard_only_counts_active_organization(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.context['incident_counts'], {'open': 1, 'critical': 0, 'under_review': 0})
        self.assertContains(response, self.incident.title)
        self.assertNotContains(response, self.foreign.title)

    def test_dashboard_status_definitions_and_latest_five(self):
        created = []
        for status in Incident.Status:
            created.append(Incident.objects.create(organization=self.organization, created_by=self.user,
                title=status, description='Text', impact_description='Text', occurred_at=self.occurred,
                detected_at=self.occurred, severity=5, status=status,
                reporting_status=Incident.ReportingStatus.UNDER_REVIEW))
        response = self.client.get('/dashboard/')
        self.assertEqual(response.context['incident_counts'], {'open': 4, 'critical': 5, 'under_review': 5})
        self.assertEqual(list(response.context['recent_incidents']), list(reversed(created)))

    def test_dashboard_and_list_switch_to_selected_organization(self):
        Membership.objects.create(user=self.user, organization=self.other_organization)
        self.select_organization(self.other_organization)
        self.assertEqual(self.results(), [self.foreign])
        response = self.client.get('/dashboard/')
        self.assertEqual(response.context['incident_counts'], {'open': 1, 'critical': 1, 'under_review': 1})
        self.assertNotContains(response, self.incident.title)

    def test_search_html_is_escaped(self):
        response = self.client.get('/incidents/', {'q': '<script>alert(1)</script>'})
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;')
