from datetime import date, datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, SimpleTestCase, TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from django.utils import timezone

from core.test_helpers import TenantTestCase
from organizations.models import Membership, Organization
from services.models import CriticalService
from .models import Incident, IncidentReport, IncidentRKEGAssessment, IncidentServiceImpact
from .rkeg_reporting import (FACT_FIELDS, Result, add_calendar_month, deadlines, evaluate_incident,
    evaluate_service, record_assessment, reporting_dashboard, current_manual_assessment)
from .rkeg_rules import RULE_BY_CODE

NOW = datetime(2026, 10, 20, 12, tzinfo=dt_timezone.utc)


def organization(**kwargs):
    data = dict(pk=1, rkeg_classified=True, rkeg_classification_reference='Bescheid 123',
                rkeg_reporting_obligation_start_date=date(2026, 4, 15))
    return SimpleNamespace(**(data | kwargs))


def service(code='E_TRANSMISSION', **kwargs):
    rule = RULE_BY_CODE[code]
    data = dict(pk=1, organization_id=1, name='Dienst', rkeg_sector=rule.sector, rkeg_subsector=rule.subsector,
                rkeg_service_code=code, rkeg_service_reference='Bescheid / Dienst 1')
    return SimpleNamespace(**(data | kwargs))


def facts(duration=timedelta(hours=3), **kwargs):
    data = dict.fromkeys(FACT_FIELDS)
    data.update(disruption_started_at=NOW-duration, disruption_ended_at=NOW, disruption_status='OUTAGE',
                unplanned_confirmed=True, special_threshold_description='', affected_geographic_area='', cross_border_impact='UNKNOWN')
    return SimpleNamespace(**(data | kwargs))


class RuleTests(SimpleTestCase):
    def evaluate(self, code='E_TRANSMISSION', org=None, data=None, **service_overrides):
        return evaluate_service(org or organization(), service(code, **service_overrides), data or facts(), NOW)

    def test_classification_unknown_and_explicit_no(self):
        self.assertEqual(self.evaluate(org=organization(rkeg_classified=None))['result'], Result.MANUAL_REVIEW)
        self.assertEqual(self.evaluate(org=organization(rkeg_classified=False))['result'], Result.NOT_APPLICABLE)

    def test_missing_classification_reference(self):
        self.assertEqual(self.evaluate(org=organization(rkeg_classification_reference=''))['result'], Result.MANUAL_REVIEW)

    def test_obligation_date_missing_or_future(self):
        for value, result in ((None, Result.MANUAL_REVIEW), (date(2026, 10, 21), Result.NOT_APPLICABLE)):
            self.assertEqual(self.evaluate(org=organization(rkeg_reporting_obligation_start_date=value))['result'], result)

    def test_pre_effective_and_overlapping_start_never_reportable(self):
        self.assertEqual(self.evaluate(data=facts(disruption_started_at=datetime(2026, 4, 14, tzinfo=dt_timezone.utc)))['result'], Result.MANUAL_REVIEW)
        self.assertEqual(self.evaluate(org=organization(rkeg_reporting_obligation_start_date=date(2026, 10, 20)), data=facts(timedelta(hours=24)))['result'], Result.MANUAL_REVIEW)

    def test_all_exempt_sectors(self):
        for sector in ('BANKING', 'FINANCIAL', 'DIGITAL'):
            with self.subTest(sector=sector):
                row = self.evaluate(rkeg_sector=sector, rkeg_service_code='')
                self.assertEqual(row['result'], Result.EXEMPT_SECTOR)
                self.assertIn('gesondert', row['explanation'])

    def test_missing_mismatched_unknown_classification(self):
        for kwargs in ({'rkeg_service_reference': ''}, {'rkeg_sector': ''}, {'rkeg_service_code': 'unknown'},
                       {'rkeg_sector': 'HEALTH'}, {'rkeg_subsector': 'Unknown'}):
            self.assertIn(self.evaluate(**kwargs)['result'], (Result.MANUAL_REVIEW, Result.INSUFFICIENT_DATA))

    def test_foreign_service_rejected(self):
        with self.assertRaises(PermissionDenied):
            self.evaluate(organization_id=2)

    def test_missing_facts(self):
        self.assertEqual(evaluate_service(organization(), service(), None, NOW)['result'], Result.INSUFFICIENT_DATA)
        for kwargs in ({'disruption_started_at': None}, {'disruption_status': ''}):
            self.assertEqual(self.evaluate(data=facts(**kwargs))['result'], Result.INSUFFICIENT_DATA)

    def test_missing_counts_never_estimated(self):
        for code in ('E_SUPPLY', 'GAS_DISTRIBUTION', 'HEAT', 'DRINKING_WATER'):
            self.assertEqual(self.evaluate(code, data=facts(timedelta(days=20)))['result'], Result.INSUFFICIENT_DATA)

    def test_zero_counts_not_missing(self):
        self.assertEqual(self.evaluate('DRINKING_WATER', data=facts(affected_users=0))['result'], Result.BELOW_THRESHOLD)

    def test_qualitative_prerequisites(self):
        for kwargs in ({'unplanned_confirmed': None}, {'unplanned_confirmed': False},
                       {'disruption_status': 'RESTRICTED_AVAILABILITY', 'significant_impairment_confirmed': None}):
            self.assertEqual(self.evaluate(data=facts(**kwargs))['result'], Result.MANUAL_REVIEW)
        self.assertEqual(self.evaluate(data=facts(disruption_status='RESTRICTED_AVAILABILITY', significant_impairment_confirmed=True))['result'], Result.REPORTABLE)

    def test_future_invalid_times(self):
        for kwargs in ({'disruption_started_at': NOW+timedelta(seconds=1)},
                       {'disruption_ended_at': NOW+timedelta(seconds=1)}, {'disruption_ended_at': NOW-timedelta(days=3)}):
            self.assertEqual(self.evaluate(data=facts(**kwargs))['result'], Result.MANUAL_REVIEW)

    def test_running_below_equal_and_above(self):
        for duration, result in ((1, Result.MANUAL_REVIEW), (2, Result.MANUAL_REVIEW), (3, Result.REPORTABLE)):
            self.assertEqual(self.evaluate(data=facts(timedelta(hours=duration), disruption_ended_at=None))['result'], result)

    def test_special_condition_not_inferred_from_duration(self):
        for value, description, expected in ((None, '', Result.INSUFFICIENT_DATA), (True, '', Result.INSUFFICIENT_DATA),
                (True, 'Kein Ergebnis', Result.REPORTABLE), (False, 'Ergebnis liegt vor', Result.BELOW_THRESHOLD)):
            self.assertEqual(self.evaluate('E_MARKET', data=facts(special_threshold_condition_met=value,
                special_threshold_description=description))['result'], expected)

    def test_calendar_month_not_thirty_days(self):
        for value, expected in ((datetime(2026, 1, 31, 10, tzinfo=ZoneInfo('Europe/Vienna')), (2026, 2, 28)),
                                (datetime(2028, 1, 31, 10, tzinfo=ZoneInfo('Europe/Vienna')), (2028, 2, 29)),
                                (datetime(2026, 12, 31, 10, tzinfo=ZoneInfo('Europe/Vienna')), (2027, 1, 31))):
            result = add_calendar_month(value)
            self.assertEqual((result.year, result.month, result.day), expected)
            self.assertEqual(result.hour, 10)


# Independent expectations ensure every published service mapping is tested.
HOUR_GROUPS = {
    2: ('E_TRANSMISSION', 'SPACE_GROUND'),
    3: ('AIR_CONTROL',),
    4: ('E_GENERATION', 'RAIL_PASSENGER', 'RAIL_INFRA', 'RAIL_CONTROL', 'ROAD_CONTROL', 'ROAD_ITS', 'PUBLIC_TRANSPORT'),
    6: ('EMERGENCY_DISPATCH',), 8: ('HOSPITAL',),
    12: ('E_STORAGE', 'GAS_SUPPLY', 'GAS_STORAGE', 'AIR_COMMERCIAL', 'AIRPORT'),
    24: ('E_DEMAND', 'E_AGGREGATION', 'OIL_PIPELINE', 'OIL_PRODUCTION', 'OIL_REFINING', 'OIL_STORAGE', 'OIL_RESERVES',
         'GAS_PIPELINE', 'GAS_LNG', 'GAS_EXTRACTION', 'GAS_PURCHASE', 'GAS_REFINING', 'H2_PRODUCTION', 'H2_STORAGE',
         'H2_PIPELINE', 'RAIL_FREIGHT', 'RAIL_SERVICE', 'SHIPPING', 'PORT', 'VESSEL_TRAFFIC', 'PHARMA_PRODUCTION',
         'MEDICAL_DEVICES', 'PHARMA_DISTRIBUTION', 'WASTEWATER', 'PUBLIC_ADMIN', 'FOOD_LOGISTICS', 'FOOD_WHOLESALE'),
    48: ('PHARMA_RESEARCH',), 72: ('REFERENCE_LAB', 'FOOD_PRODUCTION'),
}


def boundary_test(code, threshold, count_field=None):
    def test(self):
        counts = {count_field: threshold} if count_field else {}
        duration = timedelta(hours=1 if count_field else threshold)
        for delta, expected in ((-1, Result.BELOW_THRESHOLD), (0, Result.BELOW_THRESHOLD), (1, Result.REPORTABLE)):
            row = self.evaluate(code, data=facts(duration+timedelta(microseconds=delta), **counts))
            self.assertEqual(row['result'], expected)
            self.assertEqual(row['threshold_value'], threshold)
            self.assertIn('RKEV', row['rule']['legal_reference'])
            self.assertEqual(row['rule']['effective_from'], '2026-04-15')
    return test


for threshold, codes in HOUR_GROUPS.items():
    for code in codes:
        setattr(RuleTests, f'test_boundary_{code.lower()}', boundary_test(code, threshold))
for code, threshold, field in (('E_SUPPLY', 250000, 'affected_metering_points'),
        ('E_DISTRIBUTION', 250000, 'affected_metering_points'), ('GAS_DISTRIBUTION', 100000, 'affected_metering_points'),
        ('HEAT', 250000, 'affected_users'), ('DRINKING_WATER', 600000, 'affected_users')):
    setattr(RuleTests, f'test_boundary_{code.lower()}', boundary_test(code, threshold, field))


class ReportingIntegrationTests(TenantTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.organization.rkeg_classified = True
        cls.organization.rkeg_classification_reference = 'Bescheid'
        cls.organization.rkeg_reporting_obligation_start_date = date(2026, 4, 15)
        cls.organization.save()
        cls.service = CriticalService.objects.create(organization=cls.organization, name='Stromnetz', description='Netz',
            rkeg_sector='ENERGY', rkeg_subsector='Strom', rkeg_service_code='E_TRANSMISSION', rkeg_service_reference='Bescheid')
        cls.foreign_service = CriticalService.objects.create(organization=cls.other_organization, name='Fremder Dienst', description='Geheim')
        cls.incident = Incident.objects.create(organization=cls.organization, created_by=cls.user, title='Eigener Vorfall',
            description='Beschreibung', impact_description='Auswirkung', occurred_at=NOW-timedelta(hours=4),
            detected_at=NOW-timedelta(hours=3), disruption_started_at=NOW-timedelta(hours=3), disruption_ended_at=NOW,
            disruption_status='OUTAGE', unplanned_confirmed=True, rkeg_awareness_at=NOW-timedelta(hours=1),
            affected_service='Freitext', affected_location='Ort')
        cls.incident.affected_services.add(cls.service)
        cls.foreign_incident = Incident.objects.create(organization=cls.other_organization, created_by=cls.other_user,
            title='Fremder Vorfall', description='Geheim', impact_description='Geheim', occurred_at=NOW, detected_at=NOW)

    def url(self, name, incident=None, pk=None):
        args = [(incident or self.incident).pk]
        if pk is not None:
            args.append(pk)
        return reverse('incidents:' + name, args=args)

    def report(self, **kwargs):
        data = dict(incident=self.incident, organization=self.organization, created_by=self.user, report_type='INITIAL')
        return IncidentReport.objects.create(**(data | kwargs))

    def test_assessment_persists_snapshot_and_does_not_touch_legacy_status(self):
        row = record_assessment(self.incident, self.user)
        self.assertEqual(row.result, Result.REPORTABLE)
        self.assertEqual(row.calculated_duration, timedelta(hours=3))
        self.assertEqual(row.threshold_value, 2)
        self.assertEqual(row.applied_rule[0]['service_name'], 'Stromnetz')
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.reporting_status, 'NOT_ASSESSED')
        self.assertEqual(self.incident.affected_service, 'Freitext')

    def test_snapshot_survives_service_and_incident_edits(self):
        row = record_assessment(self.incident, self.user)
        self.service.name = 'Geaendert'
        self.service.save()
        self.incident.disruption_started_at = NOW-timedelta(hours=1)
        self.incident.save()
        row.refresh_from_db()
        self.assertEqual(row.applied_rule[0]['service_name'], 'Stromnetz')
        self.assertEqual(row.result, Result.REPORTABLE)
        self.assertEqual(evaluate_incident(self.incident).result, Result.BELOW_THRESHOLD)
        self.assertTrue(deadlines(self.incident, evaluate_incident(self.incident))['required'])

    def test_override_requires_reason_and_preserves_original(self):
        with self.assertRaises(ValidationError):
            record_assessment(self.incident, self.user, Result.MANUAL_REVIEW, '  ')
        self.assertEqual(IncidentRKEGAssessment.objects.count(), 0)
        row = record_assessment(self.incident, self.user, Result.MANUAL_REVIEW, 'Sachverhalt unklar')
        self.assertTrue(row.manual_override)
        self.assertEqual(row.based_on.result, Result.REPORTABLE)
        self.assertEqual(IncidentRKEGAssessment.objects.count(), 2)
        with self.assertRaises(ValidationError):
            row.based_on.save()
        with self.assertRaises(ValidationError):
            row.delete()

    def test_foreign_override_parent_blocked(self):
        base = record_assessment(self.incident, self.user)
        with self.assertRaises(ValidationError):
            IncidentRKEGAssessment.objects.create(incident=self.foreign_incident, assessed_by=self.user,
                result=Result.MANUAL_REVIEW, based_on=base, manual_override=True, manual_override_reason='Test',
                legal_reference='Test', explanation='Test', rule_version='Test')

    def test_multi_services_need_separate_facts(self):
        second = CriticalService.objects.create(organization=self.organization, name='Wasser', description='Wasser',
            rkeg_sector='WATER', rkeg_service_code='DRINKING_WATER', rkeg_service_reference='Bescheid')
        self.incident.affected_services.add(second)
        self.assertEqual(evaluate_incident(self.incident).result, Result.INSUFFICIENT_DATA)
        IncidentServiceImpact.objects.create(incident=self.incident, service=self.service,
            disruption_started_at=NOW-timedelta(hours=3), disruption_ended_at=NOW, disruption_status='OUTAGE', unplanned_confirmed=True)
        evaluation = evaluate_incident(self.incident)
        self.assertEqual(evaluation.result, Result.REPORTABLE)
        self.assertEqual(evaluation.details[1]['result'], Result.INSUFFICIENT_DATA)

    def test_exemption_cannot_cancel_reportable_other_service(self):
        second = CriticalService.objects.create(organization=self.organization, name='Bank', description='Bank',
            rkeg_sector='BANKING', rkeg_service_reference='Bescheid')
        self.incident.affected_services.add(second)
        IncidentServiceImpact.objects.create(incident=self.incident, service=self.service,
            disruption_started_at=NOW-timedelta(hours=3), disruption_ended_at=NOW, disruption_status='OUTAGE', unplanned_confirmed=True)
        evaluation = evaluate_incident(self.incident)
        self.assertEqual(evaluation.result, Result.REPORTABLE)
        self.assertEqual(evaluation.details[1]['result'], Result.EXEMPT_SECTOR)

    def test_report_organization_and_author_derived(self):
        response = self.client.post(self.url('report-create'), {'report_type': 'INITIAL', 'status': 'DRAFT',
            'organization': self.other_organization.pk, 'incident': self.foreign_incident.pk, 'created_by': self.other_user.pk})
        self.assertEqual(response.status_code, 302)
        report = IncidentReport.objects.get()
        self.assertEqual((report.organization_id, report.incident_id, report.created_by_id),
                         (self.organization.pk, self.incident.pk, self.user.pk))

    def test_model_rejects_cross_tenant_report_and_impact(self):
        with self.assertRaises(ValidationError):
            self.report(organization=self.other_organization)
        with self.assertRaises(ValidationError):
            IncidentServiceImpact.objects.create(incident=self.incident, service=self.foreign_service)

    def test_submitted_time_required_not_future_and_immutable(self):
        for kwargs in ({'status': 'MARKED_AS_SUBMITTED'}, {'submitted_at': NOW},
                       {'status': 'MARKED_AS_SUBMITTED', 'submitted_at': timezone.now()+timedelta(days=1)}):
            with self.assertRaises(ValidationError):
                self.report(**kwargs)
        report = self.report(status='MARKED_AS_SUBMITTED', submitted_at=NOW)
        with self.assertRaises(ValidationError):
            report.save()
        self.assertEqual(self.client.get(self.url('report-edit', pk=report.pk)).status_code, 403)

    def test_followup_requires_initial_and_correct_order(self):
        with self.assertRaises(ValidationError):
            self.report(report_type='FOLLOW_UP', status='MARKED_AS_SUBMITTED', submitted_at=NOW)
        self.report(status='MARKED_AS_SUBMITTED', submitted_at=NOW)
        with self.assertRaises(ValidationError):
            self.report(report_type='FOLLOW_UP', status='MARKED_AS_SUBMITTED', submitted_at=NOW-timedelta(hours=1))

    def test_deadlines_use_awareness_and_actual_submission(self):
        timing = deadlines(self.incident, evaluate_incident(self.incident), now=NOW)
        self.assertEqual(timing['initial_due_at'], NOW+timedelta(hours=23))
        self.assertIsNone(timing['follow_up_due_at'])
        self.assertTrue(timing['end_notification_required'])
        self.report(status='MARKED_AS_SUBMITTED', submitted_at=NOW)
        timing = deadlines(self.incident, evaluate_incident(self.incident), now=NOW)
        self.assertEqual(timing['follow_up_due_at'], add_calendar_month(NOW))
        self.assertFalse(timing['initial_overdue'])
        self.report(report_type='END_NOTIFICATION', status='MARKED_AS_SUBMITTED', submitted_at=NOW)
        self.assertFalse(deadlines(self.incident, evaluate_incident(self.incident))['end_notification_required'])

    def test_missing_awareness_not_replaced_by_detection(self):
        self.incident.rkeg_awareness_at = None
        timing = deadlines(self.incident, evaluate_incident(self.incident), now=NOW)
        self.assertIsNone(timing['initial_due_at'])
        self.assertTrue(timing['missing_awareness'])

    def test_24_elapsed_hours_over_dst(self):
        self.incident.rkeg_awareness_at = datetime(2026, 10, 24, 12, tzinfo=ZoneInfo('Europe/Vienna'))
        due = deadlines(self.incident, evaluate_incident(self.incident))['initial_due_at']
        self.assertEqual(due, datetime(2026, 10, 25, 10, tzinfo=dt_timezone.utc))

    def test_foreign_urls_blocked(self):
        report = self.report(incident=self.foreign_incident, organization=self.other_organization)
        for name, pk in (('report-create', None), ('reporting-data', None), ('assessment-create', None),
                         ('report-detail', report.pk), ('report-edit', report.pk), ('service-impact', self.service.pk)):
            url = self.url(name, self.foreign_incident, pk)
            self.assertEqual(self.client.get(url).status_code, 404, name)
            self.assertEqual(self.client.post(url, {}).status_code, 405 if name == 'report-detail' else 404, name)

    def test_foreign_assessment_and_wrong_parent_blocked(self):
        row = record_assessment(self.incident, self.user)
        self.assertEqual(self.client.get(self.url('assessment-detail', self.foreign_incident, row.pk)).status_code, 404)
        IncidentRKEGAssessment.objects.filter(pk=row.pk).update(organization=self.other_organization)
        self.assertEqual(self.client.get(self.url('assessment-detail', pk=row.pk)).status_code, 404)
        self.assertNotContains(self.client.get(self.url('detail')), 'Urspruengliches automatisches Ergebnis')

    def test_viewer_read_only_all_reporting_views(self):
        row = record_assessment(self.incident, self.user)
        report = self.report()
        self.set_role(Membership.Role.VIEWER)
        for name, pk in (('detail', None), ('assessment-detail', row.pk), ('report-detail', report.pk)):
            self.assertEqual(self.client.get(self.url(name, pk=pk)).status_code, 200)
        for name, pk in (('reporting-data', None), ('assessment-create', None), ('report-create', None),
                         ('report-edit', report.pk), ('service-impact', self.service.pk)):
            for method in (self.client.get, self.client.post):
                self.assertEqual(method(self.url(name, pk=pk)).status_code, 403)
        with self.assertRaises(PermissionDenied):
            record_assessment(self.incident, self.user)
        self.assertEqual(self.client.post(reverse('organizations:rkeg-edit')).status_code, 403)

    def test_all_writer_roles_can_record(self):
        for role in ('ADMIN', 'RESILIENCE_MANAGER', 'RISK_MANAGER', 'EDITOR'):
            self.set_role(role)
            self.assertEqual(self.client.post(self.url('assessment-create'), {}).status_code, 302)
        self.assertEqual(IncidentRKEGAssessment.objects.count(), 4)

    def test_anonymous_redirect_and_csrf(self):
        self.client.logout()
        for name in ('reporting-data', 'assessment-create', 'report-create'):
            response = self.client.get(self.url(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login/', response.url)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url('assessment-create')).status_code, 403)

    def test_get_does_not_create_audit_rows(self):
        self.assertEqual(self.client.get(self.url('detail')).status_code, 200)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        self.assertFalse(IncidentRKEGAssessment.objects.exists())

    def test_data_edit_cannot_change_organization_author_or_relations(self):
        response = self.client.post(self.url('reporting-data'), {'organization': self.other_organization.pk,
            'created_by': self.other_user.pk, 'affected_services': [self.foreign_service.pk], 'cross_border_impact': 'UNKNOWN'})
        self.assertEqual(response.status_code, 302)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.organization_id, self.organization.pk)
        self.assertEqual(self.incident.created_by_id, self.user.pk)
        self.assertEqual(list(self.incident.affected_services.all()), [self.service])
        self.assertEqual(self.incident.affected_service, 'Freitext')

    def test_service_impact_create_edit_and_foreign_ids(self):
        url = self.url('service-impact', pk=self.service.pk)
        response = self.client.post(url, {'cross_border_impact': 'UNKNOWN', 'service': self.foreign_service.pk,
                                         'organization': self.other_organization.pk, 'incident': self.foreign_incident.pk})
        self.assertEqual(response.status_code, 302)
        row = IncidentServiceImpact.objects.get()
        self.assertEqual((row.incident_id, row.service_id, row.organization_id),
                         (self.incident.pk, self.service.pk, self.organization.pk))
        self.assertEqual(self.client.post(url, {'affected_users': 50, 'cross_border_impact': 'NO'}).status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.affected_users, 50)
        self.assertEqual(self.client.post(self.url('service-impact', pk=self.foreign_service.pk), {}).status_code, 404)

    def test_dashboard_tenant_and_due_counts(self):
        with patch('incidents.rkeg_reporting.timezone.now', return_value=NOW):
            counts = reporting_dashboard(self.organization)
        self.assertEqual(counts, dict(reportable_open=1, initial_due=1, initial_overdue=0, follow_up_due=0, manual_review=0))
        self.incident.rkeg_awareness_at = NOW-timedelta(hours=25)
        self.incident.save()
        with patch('incidents.rkeg_reporting.timezone.now', return_value=NOW):
            counts = reporting_dashboard(self.organization)
        self.assertEqual(counts['initial_overdue'], 1)
        self.assertEqual(counts['manual_review'], 0)

    def test_dashboard_followup_and_unknown_awareness(self):
        self.report(status='MARKED_AS_SUBMITTED', submitted_at=NOW-timedelta(days=40))
        counts = reporting_dashboard(self.organization)
        self.assertEqual(counts['follow_up_due'], 1)
        self.incident.rkeg_awareness_at = None
        self.incident.save()
        self.assertEqual(reporting_dashboard(self.organization)['manual_review'], 1)

    def test_organization_form_and_stale_context(self):
        url = reverse('organizations:rkeg-edit')
        response = self.client.get(url)
        token = response.context['form']['organization_context'].value()
        response = self.client.post(url, {'rkeg_classified': 'true', 'rkeg_classification_reference': 'Neu',
            'rkeg_reporting_obligation_start_date': '2026-04-15', 'organization_context': token})
        self.assertEqual(response.status_code, 302)
        Membership.objects.create(user=self.user, organization=self.other_organization, role='ADMIN')
        self.select_organization(self.other_organization)
        self.assertEqual(self.client.post(url, {'organization_context': token}).status_code, 200)
        self.other_organization.refresh_from_db()
        self.assertIsNone(self.other_organization.rkeg_classified)

    def test_invalid_override_form_does_not_write(self):
        response = self.client.post(self.url('assessment-create'), {'override_result': 'REPORTABLE', 'override_reason': ' '})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(IncidentRKEGAssessment.objects.exists())

    def test_all_new_forms_and_detail_templates_render(self):
        row = record_assessment(self.incident, self.user, Result.MANUAL_REVIEW, '<script>Text</script>')
        report = self.report(consequences='<script>Text</script>')
        for name, pk in (('reporting-data', None), ('assessment-create', None), ('report-create', None),
                         ('report-edit', report.pk), ('service-impact', self.service.pk),
                         ('assessment-detail', row.pk), ('report-detail', report.pk)):
            response = self.client.get(self.url(name, pk=pk))
            self.assertEqual(response.status_code, 200, name)
            self.assertNotContains(response, '<script>')

    def test_manual_override_current_only_while_inputs_match(self):
        row = record_assessment(self.incident, self.user, Result.MANUAL_REVIEW, 'Ursache pruefen')
        self.assertEqual(current_manual_assessment(self.incident, evaluate_incident(self.incident)), row)
        self.incident.affected_geographic_area = 'Neue Information'
        self.assertIsNone(current_manual_assessment(self.incident, evaluate_incident(self.incident)))

    def test_positive_manual_assessment_keeps_deadlines(self):
        self.incident.disruption_started_at = NOW-timedelta(hours=1)
        self.incident.save()
        row = record_assessment(self.incident, self.user, Result.REPORTABLE, 'Potenzielle Stoerung fachlich bewertet')
        self.assertEqual(row.based_on.result, Result.BELOW_THRESHOLD)
        self.assertTrue(deadlines(self.incident, evaluate_incident(self.incident))['required'])

    def test_forged_assessment_result_is_ignored(self):
        response = self.client.post(self.url('assessment-create'), {'result': 'BELOW_THRESHOLD',
            'organization': self.other_organization.pk, 'incident': self.foreign_incident.pk,
            'assessed_by': self.other_user.pk, 'applied_rule': 'fake', 'rule_version': 'fake'})
        self.assertEqual(response.status_code, 302)
        row = IncidentRKEGAssessment.objects.get()
        self.assertEqual(row.result, Result.REPORTABLE)
        self.assertEqual(row.assessed_by_id, self.user.pk)
        self.assertEqual(row.organization_id, self.organization.pk)

    def test_invalid_fact_times_and_negative_counts_rejected(self):
        for data in ({'affected_users': -1}, {'affected_metering_points': -1},
                     {'disruption_started_at': '2026-10-20T12:00', 'disruption_ended_at': '2026-10-19T12:00'},
                     {'disruption_started_at': '2099-01-01T12:00'}):
            self.assertEqual(self.client.post(self.url('reporting-data'), data).status_code, 200)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.disruption_started_at, NOW-timedelta(hours=3))

    def test_revoked_membership_cannot_record(self):
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.client.post(self.url('assessment-create')).status_code, 302)
        self.assertFalse(IncidentRKEGAssessment.objects.exists())
        with self.assertRaises(PermissionDenied):
            record_assessment(self.incident, self.user)

    def test_foreign_through_relation_not_read_by_engine(self):
        Incident.affected_services.through.objects.create(incident=self.incident, criticalservice=self.foreign_service)
        evaluation = evaluate_incident(self.incident)
        self.assertEqual(len(evaluation.details), 1)
        self.assertEqual(evaluation.result, Result.REPORTABLE)
        self.assertNotContains(self.client.get(self.url('detail')), self.foreign_service.name)


class ReportingMigrationTests(TransactionTestCase):
    def test_existing_data_unchanged_and_no_inferred_classification(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [('organizations', '0001_initial'), ('services', '0001_initial'),
                    ('incidents', '0002_incident_affected_locations_and_more'), ('risks', '0004_risk_critical_services')]
        try:
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            user = apps.get_model('accounts', 'User').objects.create(username='legacy-reporting')
            org = apps.get_model('organizations', 'Organization').objects.create(name='Bestand', legal_name='Bestand GmbH')
            srv = apps.get_model('services', 'CriticalService').objects.create(organization_id=org.pk, name='Bestandsdienst', description='Text')
            incident = apps.get_model('incidents', 'Incident').objects.create(organization_id=org.pk, created_by_id=user.pk,
                title='Bestandsvorfall', description='Text', impact_description='Text', occurred_at=NOW, detected_at=NOW,
                affected_service='Freitext Dienst', affected_location='Freitext Ort', reporting_status='REPORTED')
            incident.affected_services.add(srv)
            MigrationExecutor(connection).migrate(latest)
            for old, model in ((org, Organization), (srv, CriticalService), (incident, Incident)):
                current = model.objects.get(pk=old.pk)
                for field in old._meta.concrete_fields:
                    self.assertEqual(getattr(current, field.attname), getattr(old, field.attname))
            self.assertIsNone(Organization.objects.get(pk=org.pk).rkeg_classified)
            current = Incident.objects.get(pk=incident.pk)
            self.assertIsNone(current.rkeg_awareness_at)
            self.assertIsNone(current.disruption_started_at)
            self.assertEqual(list(current.affected_services.values_list('pk', flat=True)), [srv.pk])
            self.assertFalse(IncidentRKEGAssessment.objects.exists())
            self.assertFalse(IncidentReport.objects.exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
