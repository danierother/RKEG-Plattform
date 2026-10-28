from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from incidents.models import Incident, IncidentReport, IncidentRKEGAssessment
from incidents.rkeg_reporting import record_assessment
from organizations.models import Membership
from risks.models import Risk, RiskControl, RiskMeasure
from services.tests import ServicesTestCase
from .models import AuditEvent
from .services import audited_change, audited_delete, record_change


class AuditTests(ServicesTestCase):
    def risk_events(self, risk=None):
        return AuditEvent.objects.filter(object_type='risks.risk', object_id=str((risk or self.risk).pk))

    def test_risk_create_actor_organization_source_and_m2m(self):
        url = reverse('risks:create')
        data = self.risk_payload(url, title='Auditrisiko', critical_services=[self.service.pk],
            actor=self.other_user.pk, organization=self.other_organization.pk, source='ADMIN', password='DO-NOT-LOG')
        self.assertEqual(self.client.post(url, data).status_code, 302)
        event = AuditEvent.objects.get(object_repr='Auditrisiko')
        self.assertEqual(event.action, 'CREATE')
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.organization_id, self.organization.pk)
        self.assertEqual(event.source, 'WEB')
        self.assertEqual(event.new_value['critical_services'], [self.service.pk])
        self.assertNotIn('DO-NOT-LOG', str(event.new_value))
        self.assertNotIn('password', event.new_value)

    def test_risk_update_old_new_and_derived_classes(self):
        url = reverse('risks:edit', args=[self.risk.pk])
        response = self.client.post(url, self.risk_payload(url, likelihood=5, impact=5,
            residual_likelihood=1, residual_impact=1, treatment_strategy='REDUCE'))
        self.assertEqual(response.status_code, 302)
        event = self.risk_events().get(field_name='likelihood')
        self.assertEqual((event.old_value, event.new_value), (3, 5))
        self.assertEqual(self.risk_events().get(field_name='risk_class').new_value, 'critical')
        self.assertEqual(self.risk_events().get(field_name='residual_risk_class').new_value, 'low')
        self.assertEqual(self.risk_events().get(field_name='residual_risk_score').new_value, 1)
        self.assertEqual(self.risk_events().get(field_name='treatment_strategy').new_value, 'REDUCE')

    def test_preview_and_invalid_forms_have_no_audit_side_effect(self):
        url = reverse('risks:edit', args=[self.risk.pk])
        self.assertEqual(self.client.post(url, self.risk_payload(url, action='preview')).status_code, 200)
        self.assertEqual(self.client.post(url, self.risk_payload(url, likelihood=99)).status_code, 200)
        self.assertFalse(AuditEvent.objects.exists())

    def test_noop_save_does_not_produce_event(self):
        with audited_change(self.risk, organization=self.organization, actor=self.user, source='WEB'):
            self.risk.save()
        self.assertFalse(AuditEvent.objects.exists())

    def test_audit_failure_rolls_back_risk_and_m2m(self):
        old_title = self.risk.title
        with patch('audit.services.record_change', side_effect=RuntimeError('Unavailable')):
            with self.assertRaises(RuntimeError):
                with audited_change(self.risk, organization=self.organization, actor=self.user, source='WEB'):
                    self.risk.title = 'Do not save'
                    self.risk.save()
                    self.risk.critical_services.add(self.service)
        self.risk.refresh_from_db()
        self.assertEqual(self.risk.title, old_title)
        self.assertFalse(self.risk.critical_services.exists())

    def test_m2m_update_records_removed_and_added_ids(self):
        self.risk.critical_services.add(self.service)
        url = reverse('risks:edit', args=[self.risk.pk])
        self.client.post(url, self.risk_payload(url))
        event = self.risk_events().get(field_name='critical_services')
        self.assertEqual(event.old_value, [self.service.pk])
        self.assertEqual(event.new_value, [])

    def test_risk_control_create_and_update(self):
        url = reverse('risks:control-create', args=[self.risk.pk])
        self.assertEqual(self.client.post(url, {'title': 'Kontrolle', 'effectiveness': 2}).status_code, 302)
        control = RiskControl.objects.get()
        self.assertEqual(AuditEvent.objects.get(object_type='risks.riskcontrol').action, 'CREATE')
        self.client.post(reverse('risks:control-edit', args=[self.risk.pk, control.pk]), {'title': 'Kontrolle', 'effectiveness': 5})
        event = AuditEvent.objects.get(object_type='risks.riskcontrol', field_name='effectiveness')
        self.assertEqual((event.old_value, event.new_value), (2, 5))

    def test_measure_status_change(self):
        measure = RiskMeasure.objects.create(risk=self.risk, title='Massnahme')
        self.client.post(reverse('risks:measure-edit', args=[self.risk.pk, measure.pk]), {'title': measure.title, 'status': 'IMPLEMENTED'})
        event = AuditEvent.objects.get(object_type='risks.riskmeasure', field_name='status')
        self.assertEqual(event.action, 'STATUS_CHANGE')
        self.assertEqual((event.old_value, event.new_value), ('PLANNED', 'IMPLEMENTED'))

    def test_services_locations_and_dependencies_audited(self):
        for view_name, kind in (('edit', 'services.criticalservice'), ('location-edit', 'services.location'),
                                 ('dependency-edit', 'services.servicedependency')):
            self.assertEqual(self.client.post(self.url(view_name), self.payload(view_name, name='Geaendert')).status_code, 302)
            self.assertTrue(AuditEvent.objects.filter(object_type=kind, field_name='name', new_value='Geaendert').exists())

    def test_incident_create_update_and_status(self):
        data = self.incident_payload(title='Neuer Incident')
        self.assertEqual(self.client.post(reverse('incidents:create'), data).status_code, 302)
        item = Incident.objects.get(title='Neuer Incident')
        self.assertTrue(AuditEvent.objects.filter(object_type='incidents.incident', object_id=str(item.pk), action='CREATE').exists())
        self.client.post(reverse('incidents:edit', args=[self.incident.pk]), self.incident_payload(status='ACTIVE', severity=5))
        event = AuditEvent.objects.get(object_type='incidents.incident', field_name='status')
        self.assertEqual((event.old_value, event.new_value, event.action), ('NEW', 'ACTIVE', 'STATUS_CHANGE'))
        self.assertTrue(AuditEvent.objects.filter(field_name='severity', new_value=5).exists())

    def test_event_and_action_created(self):
        self.assertEqual(self.client.post(reverse('incidents:event-create', args=[self.incident.pk]), {
            'event_time': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'event_type': 'ACTION', 'description': 'Erfasst'}).status_code, 302)
        self.assertEqual(self.client.post(reverse('incidents:action-create', args=[self.incident.pk]), {
            'title': 'Massnahme', 'status': 'OPEN'}).status_code, 302)
        self.assertTrue(AuditEvent.objects.filter(object_type='incidents.incidentevent', action='CREATE').exists())
        self.assertTrue(AuditEvent.objects.filter(object_type='incidents.incidentaction', action='CREATE').exists())

    def test_assessment_and_manual_override(self):
        row = record_assessment(self.incident, self.user, 'MANUAL_REVIEW', 'Unvollstaendig')
        self.assertEqual(AuditEvent.objects.filter(action='ASSESSMENT').count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action='MANUAL_OVERRIDE').count(), 1)
        event = AuditEvent.objects.get(action='MANUAL_OVERRIDE')
        self.assertEqual(event.new_value['based_on_id'], row.based_on_id)
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.new_value['manual_override_reason'], 'Unvollstaendig')

    def test_invalid_override_rolls_back_audit_too(self):
        with self.assertRaises(ValidationError):
            record_assessment(self.incident, self.user, 'MANUAL_REVIEW', '')
        self.assertFalse(AuditEvent.objects.exists())
        self.assertFalse(IncidentRKEGAssessment.objects.exists())

    def test_report_create_and_submit(self):
        self.client.post(reverse('incidents:report-create', args=[self.incident.pk]), {'report_type': 'INITIAL', 'status': 'DRAFT'})
        report = IncidentReport.objects.get()
        self.assertTrue(AuditEvent.objects.filter(action='REPORT_CREATED').exists())
        response = self.client.post(reverse('incidents:report-edit', args=[self.incident.pk, report.pk]), {
            'report_type': 'INITIAL', 'status': 'MARKED_AS_SUBMITTED',
            'submitted_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M')})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AuditEvent.objects.filter(action='REPORT_MARKED_SUBMITTED').exists())
        self.assertTrue(AuditEvent.objects.filter(field_name='submitted_at', action='UPDATE').exists())

    def test_organization_settings_audit(self):
        url = reverse('organizations:rkeg-edit')
        token = self.client.get(url).context['form']['organization_context'].value()
        self.assertEqual(self.client.post(url, {'organization_context': token, 'rkeg_classified': 'true',
            'rkeg_classification_reference': 'Bescheid', 'rkeg_reporting_obligation_start_date': '2026-04-15'}).status_code, 302)
        self.assertTrue(AuditEvent.objects.filter(object_type='organizations.organization', field_name='rkeg_classification_reference',
                                                new_value='Bescheid').exists())

    def test_model_and_admin_no_edit_delete(self):
        record_change(self.risk, None, organization=self.organization)
        event = AuditEvent.objects.get()
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        self.user.is_superuser = True
        request = RequestFactory().get('/admin/')
        request.user = self.user
        model_admin = admin.site._registry[AuditEvent]
        self.assertFalse(model_admin.has_change_permission(request, event))
        self.assertFalse(model_admin.has_delete_permission(request, event))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertEqual(self.client.post('/audit/1/edit/', {}).status_code, 404)
        self.assertEqual(self.client.post('/audit/1/delete/', {}).status_code, 404)

    def test_audit_list_filters_and_foreign_event(self):
        record_change(self.risk, None, organization=self.organization, actor=self.user)
        record_change(self.other_risk, None, organization=self.other_organization, actor=self.other_user)
        response = self.client.get('/audit/', {'organization': self.other_organization.pk})
        self.assertContains(response, self.risk.title)
        self.assertNotContains(response, self.other_risk.title)
        self.assertEqual(len(self.client.get('/audit/', {'actor': self.other_user.pk}).context['events']), 0)
        for values, expected in (({'q': self.risk.title}, 1), ({'action': 'UPDATE'}, 0),
                                  ({'object_type': 'risks.risk'}, 1), ({'date_from': '2099-01-01'}, 0)):
            self.assertEqual(len(self.client.get('/audit/', values).context['events']), expected)

    def test_viewer_read_anonymous_redirect_no_post(self):
        self.set_role(Membership.Role.VIEWER)
        self.assertEqual(self.client.get('/audit/').status_code, 200)
        self.assertEqual(self.client.post('/audit/', {}).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get('/audit/').status_code, 302)

    def test_object_histories_are_scoped(self):
        for obj, name in ((self.risk, 'risks:detail'), (self.service, 'services:detail'), (self.incident, 'incidents:detail')):
            record_change(obj, None, organization=self.organization)
            AuditEvent.objects.create(organization=self.other_organization, object_type=obj._meta.label_lower,
                object_id=str(obj.pk), object_repr='Fremde Historie', action='CREATE', source='SYSTEM')
            response = self.client.get(reverse(name, args=[obj.pk]))
            self.assertEqual(len(response.context['object_audit_events']), 1)
            self.assertNotContains(response, 'Fremde Historie')

    def test_wrong_organization_and_viewer_writes_rejected(self):
        with self.assertRaises(PermissionDenied):
            record_change(self.risk, None, organization=self.other_organization)
        self.set_role('VIEWER')
        with self.assertRaises(PermissionDenied):
            with audited_change(self.risk, organization=self.organization, actor=self.user, source='WEB'):
                self.fail('Writer authorization missing')

    def test_delete_retains_snapshots_including_cascade(self):
        measure = RiskMeasure.objects.create(risk=self.risk, title='Delete measure')
        control = RiskControl.objects.create(risk=self.risk, title='Delete control')
        risk_id = self.risk.pk
        audited_delete(self.risk, organization=self.organization)
        self.assertFalse(Risk.objects.filter(pk=risk_id).exists())
        self.assertEqual(set(AuditEvent.objects.values_list('object_type', flat=True)),
                         {'risks.risk', 'risks.riskmeasure', 'risks.riskcontrol'})
        self.assertEqual(AuditEvent.objects.filter(action='DELETE').count(), 3)
        self.assertEqual(AuditEvent.objects.get(object_type='risks.riskmeasure').old_value['title'], measure.title)

    def test_admin_save_uses_same_audit_layer(self):
        self.user.is_superuser = True
        request = RequestFactory().post('/admin/')
        request.user = self.user
        self.risk.title = 'Admin change'
        admin.site._registry[Risk].save_model(request, self.risk, None, True)
        self.assertEqual(self.risk_events().get(field_name='title').source, 'ADMIN')
