import csv
import io
from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from incidents.models import Incident, IncidentAction
from incidents.rkeg_reporting import evaluate_incident
from risks.models import Risk, RiskMeasure
from services.tests import ServicesTestCase
from services.models import CriticalService, ServiceDependency
from .reporting import incident_records, risk_table, services_table
from .report_views import csv_cell


class ReportingTests(ServicesTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.today = timezone.localdate()
        cls.risk.likelihood = cls.risk.impact = 5
        cls.risk.residual_likelihood = cls.risk.residual_impact = 2
        cls.risk.save()
        cls.risk.critical_services.add(cls.service)
        cls.incident.affected_services.add(cls.service)
        cls.measure = RiskMeasure.objects.create(risk=cls.risk, title='Offene eigene Massnahme',
            responsible_user=cls.user, due_date=cls.today-timedelta(days=1))
        cls.action = IncidentAction.objects.create(incident=cls.incident, title='Eigene Vorfallmassnahme',
            responsible_user=cls.user, due_date=cls.today-timedelta(days=1))
        cls.other_measure = RiskMeasure.objects.create(risk=cls.other_risk, title='Fremde Massnahme',
            due_date=cls.today-timedelta(days=1))
        cls.other_action = IncidentAction.objects.create(incident=cls.foreign_incident, title='Fremde Vorfallmassnahme',
            due_date=cls.today-timedelta(days=1))

    def url(self, name, **kwargs):
        return reverse('reports:' + name)

    def csv_rows(self, kind, params=None):
        response = self.client.get(self.url(kind), {'format': 'csv', **(params or {})})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        return list(csv.reader(io.StringIO(response.content.decode('utf-8-sig')), delimiter=';'))

    def test_all_reports_print_and_metadata_render(self):
        self.assertEqual(self.client.get('/reports/').status_code, 200)
        for kind in ('management', 'risks', 'actions', 'services', 'incidents', 'rkeg'):
            for suffix in ('', '-print'):
                response = self.client.get(self.url(kind+suffix))
                self.assertEqual(response.status_code, 200, kind+suffix)
                self.assertContains(response, self.organization.name)
                self.assertContains(response, 'Alex Muster')
                self.assertContains(response, 'Prototyp / interne Dokumentation')
                self.assertNotContains(response, self.other_risk.title)
                self.assertNotContains(response, self.foreign_incident.title)
                self.assertNotContains(response, self.foreign_service.name)

    def test_management_counts_and_tables(self):
        response = self.client.get(self.url('management'))
        counts = dict(response.context['metrics'])
        self.assertEqual(counts['Risiken gesamt'], 1)
        self.assertEqual(counts['Brutto: Kritisch'], 1)
        self.assertEqual(counts['Restrisiko: Niedrig'], 1)
        self.assertEqual(counts['Ueberfaellige Massnahmen'], 2)
        self.assertEqual(counts['Aktive Dienstleistungen'], 1)
        self.assertEqual(counts['Dienstleistungen Kritikalitaet 4/5'], 1)
        self.assertEqual(counts['Kritische Abhaengigkeiten'], 1)
        self.assertEqual(counts['Single Points of Failure'], 1)
        self.assertEqual(counts['Offene Vorfaelle'], 1)
        self.assertEqual(counts['Manuelle Pruefungen offen'], 1)
        self.assertEqual(counts['Meldepflichtige Vorfaelle / dokumentierte Meldeaufgaben'], 0)
        self.assertContains(response, self.measure.title)
        self.assertNotContains(response, self.other_measure.title)

    def test_management_rkeg_and_critical_incidents(self):
        self.organization.rkeg_classified = True
        self.organization.rkeg_classification_reference = 'Bescheid'
        self.organization.rkeg_reporting_obligation_start_date = self.today-timedelta(days=10)
        self.organization.save()
        self.service.rkeg_sector, self.service.rkeg_subsector = 'ENERGY', 'Strom'
        self.service.rkeg_service_code, self.service.rkeg_service_reference = 'E_TRANSMISSION', 'Bescheid'
        self.service.save()
        self.incident.severity = 5
        self.incident.disruption_started_at = timezone.now()-timedelta(hours=30)
        self.incident.disruption_status = 'OUTAGE'
        self.incident.unplanned_confirmed = True
        self.incident.rkeg_awareness_at = timezone.now()-timedelta(hours=25)
        self.incident.save()
        response = self.client.get(self.url('management'))
        counts = dict(response.context['metrics'])
        self.assertEqual(counts['Kritische Vorfaelle'], 1)
        self.assertEqual(counts['Meldepflichtige Vorfaelle / dokumentierte Meldeaufgaben'], 1)
        self.assertEqual(counts['Ueberfaellige Erstmeldungen'], 1)
        self.assertEqual(counts['Manuelle Pruefungen offen'], 0)
        self.assertEqual(len(response.context['tables'][2].rows), 1)

    def test_top_residual_risks_order_and_limit(self):
        for number in range(12):
            Risk.objects.create(organization=self.organization, created_by=self.user, title=f'Risiko {number}',
                                residual_likelihood=5, residual_impact=5)
        rows = self.client.get(self.url('management')).context['tables'][0].rows
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(row.cells[1] == 25 for row in rows))

    def test_risk_report_fields_and_filters(self):
        rows = self.csv_rows('risks')
        self.assertEqual(len(rows), 2)
        self.assertIn('25 / Kritisch', rows[1])
        self.assertIn('4 / Niedrig', rows[1])
        self.assertIn(self.service.name, rows[1])
        self.assertIn('Alex Muster', rows[1])
        for params, expected in (({'risk_class': 'critical'}, 2), ({'risk_class': 'low'}, 1),
                ({'residual_risk_class': 'low'}, 2), ({'residual_risk_class': 'critical'}, 1),
                ({'status': 'CLOSED'}, 1), ({'service': self.service.pk}, 2)):
            self.assertEqual(len(self.csv_rows('risks', params)), expected)

    def test_action_filters_status_owner_type_and_overdue(self):
        self.assertEqual(len(self.csv_rows('actions')), 3)
        for params, expected in (({'type': 'risk'}, 2), ({'type': 'incident'}, 2),
                ({'status': 'OPEN'}, 2), ({'responsible_user': self.user.pk}, 3),
                ({'overdue': 'yes'}, 3), ({'overdue': 'no'}, 1)):
            self.assertEqual(len(self.csv_rows('actions', params)), expected)

    def test_overdue_excludes_completed_cancelled_today_and_undated(self):
        self.measure.status = 'IMPLEMENTED'
        self.measure.save()
        self.action.status = 'CANCELLED'
        self.action.save()
        RiskMeasure.objects.create(risk=self.risk, title='Heute', due_date=self.today)
        RiskMeasure.objects.create(risk=self.risk, title='Ohne Datum')
        self.assertEqual(len(self.csv_rows('actions', {'overdue': 'yes'})), 1)
        RiskMeasure.objects.create(risk=self.risk, title='Explizit ueberfaellig', status='OVERDUE')
        self.assertEqual(len(self.csv_rows('actions', {'overdue': 'yes'})), 2)

    def test_services_counts_and_dependencies(self):
        table = services_table(self.organization, {})
        row = table.rows[0].cells
        self.assertEqual(row[6:10], (1, 1, 1, 1))
        self.assertIn('Energie', row[10])
        self.assertIn('Ausweichloesung: Nein', row[10])
        self.assertIn(self.location.name, row[5])

    def test_incident_filter_matches_csv(self):
        for params, expected in (({'status': 'NEW'}, 2), ({'status': 'CLOSED'}, 1),
                ({'severity': 5}, 1), ({'severity': 2}, 2), ({'incident_type': 'OTHER'}, 2),
                ({'rkeg_result': 'MANUAL_REVIEW'}, 2), ({'rkeg_result': 'REPORTABLE'}, 1),
                ({'date_from': '2099-01-01'}, 1)):
            csv_rows = self.csv_rows('incidents', params)
            response = self.client.get(self.url('incidents'), params)
            self.assertEqual(len(csv_rows), expected)
            self.assertEqual(len(response.context['tables'][0].rows), expected-1)

    def test_rkeg_report_has_service_rows_without_writing_assessments(self):
        response = self.client.get(self.url('rkeg'))
        row = response.context['tables'][0].rows[0]
        self.assertEqual(row.cells[1], self.service.name)
        self.assertIn('Manuelle Pruefung', row.cells[2])
        self.assertFalse(self.incident.rkeg_assessments.exists())
        self.assertEqual(len(self.csv_rows('rkeg')), 2)

    def test_all_csv_exports_tenant_scoped_and_metadata(self):
        for kind in ('risks', 'actions', 'services', 'incidents', 'rkeg'):
            rows = self.csv_rows(kind, {'organization': self.other_organization.pk})
            text = str(rows)
            self.assertIn(self.organization.name, text)
            self.assertNotIn(self.other_risk.title, text)
            self.assertNotIn(self.foreign_incident.title, text)
            self.assertNotIn(self.foreign_service.name, text)
            self.assertNotIn(self.other_measure.title, text)
            self.assertNotIn(self.other_action.title, text)

    def test_foreign_filter_ids_invalid_html_empty_csv_rejected(self):
        for kind, field, pk in (('risks', 'service', self.foreign_service.pk),
                               ('actions', 'responsible_user', self.other_user.pk)):
            response = self.client.get(self.url(kind), {field: pk})
            self.assertTrue(response.context['filter_form'].errors)
            self.assertEqual(response.context['tables'], [])
            self.assertEqual(self.client.get(self.url(kind), {field: pk, 'format': 'csv'}).status_code, 400)

    def test_invalid_period_and_filter_choices_fail_closed(self):
        for params in ({'status': 'INVALID'}, {'date_from': 'garbage'}, {'date_from': '2026-10-29', 'date_to': '2026-10-01'}):
            self.assertEqual(self.client.get(self.url('incidents'), params).context['tables'], [])
            self.assertEqual(self.client.get(self.url('incidents'), dict(params, format='csv')).status_code, 400)

    def test_date_filters_inclusive_and_print_preserved(self):
        today = self.today.isoformat()
        params = {'date_from': today, 'date_to': today}
        self.assertEqual(len(self.csv_rows('incidents', params)), 2)
        response = self.client.get(self.url('incidents-print'), params)
        self.assertEqual(len(response.context['tables'][0].rows), 1)
        self.assertIn(today, response.context['filter_description'])

    def test_csv_formula_injection_and_multiline_escaping(self):
        for value in ('=1+1', '+cmd', '-cmd', '@cmd', ' \t=1', '\ttext', '\n=1', '\ufeff=1'):
            self.assertTrue(csv_cell(value).startswith("'"))
        self.risk.title = '=SUM(1,2);"Text"\nZeile'
        self.risk.save()
        rows = self.csv_rows('risks')
        self.assertEqual(rows[1][5], "'" + self.risk.title)

    def test_html_escapes_user_content(self):
        self.risk.title = '<script>alert(1)</script>'
        self.risk.save()
        response = self.client.get(self.url('risks'))
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;')

    def test_viewer_all_reports_csv_print_and_no_writes(self):
        self.set_role('VIEWER')
        for kind in ('management', 'risks', 'actions', 'services', 'incidents', 'rkeg'):
            self.assertEqual(self.client.get(self.url(kind)).status_code, 200)
            self.assertEqual(self.client.get(self.url(kind+'-print')).status_code, 200)
            self.assertEqual(self.client.post(self.url(kind)).status_code, 405)
            if kind != 'management':
                self.csv_rows(kind)

    def test_anonymous_redirects_for_html_print_csv(self):
        self.client.logout()
        for path in ('/reports/', '/reports/management/', '/reports/risks/?format=csv', '/reports/rkeg/print/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login/', response.url)

    def test_pagination_csv_and_print_include_all_filtered_rows(self):
        Risk.objects.bulk_create([Risk(organization=self.organization, created_by=self.user, title=f'Paging {i}') for i in range(51)])
        self.assertEqual(len(self.client.get(self.url('risks')).context['tables'][0].rows), 50)
        self.assertEqual(len(self.csv_rows('risks')), 53)
        self.assertEqual(len(self.client.get(self.url('risks-print')).context['tables'][0].rows), 52)

    def test_corrupt_cross_tenant_relations_do_not_leak(self):
        Risk.critical_services.through.objects.create(risk=self.risk, criticalservice=self.foreign_service)
        Incident.affected_services.through.objects.create(incident=self.foreign_incident, criticalservice=self.service)
        ServiceDependency.objects.filter(pk=self.foreign_dependency.pk).update(service=self.service)
        for kind in ('risks', 'services', 'incidents', 'rkeg'):
            text = str(self.csv_rows(kind))
            self.assertNotIn(self.foreign_service.name, text)
            self.assertNotIn(self.foreign_incident.title, text)
            self.assertNotIn(self.foreign_dependency.name, text)

    def test_incident_reports_query_count_does_not_grow_per_incident(self):
        with CaptureQueriesContext(connection) as first:
            list(incident_records(self.organization, {}, timezone.now()))
        for index in range(8):
            item = Incident.objects.create(organization=self.organization, created_by=self.user, title=f'Extra {index}',
                description='Text', impact_description='Text', occurred_at=self.when, detected_at=self.when)
            item.affected_services.add(self.service)
        with CaptureQueriesContext(connection) as second:
            list(incident_records(self.organization, {}, timezone.now()))
        self.assertEqual(len(first), len(second))
        self.assertLessEqual(len(second), 5)

    def test_risk_services_query_counts_are_bounded(self):
        for index in range(8):
            risk = Risk.objects.create(organization=self.organization, created_by=self.user, title=f'Extra {index}')
            risk.critical_services.add(self.service)
        with CaptureQueriesContext(connection) as queries:
            risk_table(self.organization, {})
            services_table(self.organization, {})
        self.assertLessEqual(len(queries), 8)
