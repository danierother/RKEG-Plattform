import csv

from django.http import HttpResponse
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.generic import TemplateView

from organizations.mixins import OrganizationContextMixin
from .report_forms import ActionReportForm, IncidentReportFilterForm, PeriodForm, RiskReportForm
from .reporting import (actions_table, display, incident_records, incidents_table, management_report,
                        risk_table, rkeg_table, services_table, user_name)

REPORTS = {
    'management': 'Managementuebersicht', 'risks': 'Risikobericht', 'actions': 'Massnahmenbericht',
    'services': 'Dienstleistungen / Abhaengigkeiten', 'incidents': 'Vorfallsbericht', 'rkeg': 'RKEG-Meldestatus',
}
FORMS = {'risks': RiskReportForm, 'actions': ActionReportForm, 'services': PeriodForm,
         'incidents': IncidentReportFilterForm, 'rkeg': IncidentReportFilterForm}


def csv_cell(raw):
    text = str(raw)
    inspected = text.lstrip().lstrip('\ufeff').lstrip()
    if (inspected and inspected[0] in '=+-@') or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


class ReportIndexView(OrganizationContextMixin, TemplateView):
    template_name = 'reports/index.html'

    def get_context_data(self, **kwargs):
        return dict(super().get_context_data(**kwargs), report_types=REPORTS.items())


class ReportView(OrganizationContextMixin, TemplateView):
    template_name = 'reports/report.html'
    report_type = 'management'
    print_view = False

    def get(self, request, *args, **kwargs):
        now = timezone.now()
        form_class = FORMS.get(self.report_type)
        form = form_class(request.GET, organization=self.organization) if form_class else None
        valid = form is None or form.is_valid()
        filters = form.cleaned_data if form and valid else {}
        metrics, tables = [], []
        if valid:
            if self.report_type == 'management':
                metrics, tables = management_report(self.organization, now)
            elif self.report_type == 'risks':
                tables = [risk_table(self.organization, filters)]
            elif self.report_type == 'actions':
                tables = [actions_table(self.organization, filters, now)]
            elif self.report_type == 'services':
                tables = [services_table(self.organization, filters)]
            else:
                records = list(incident_records(self.organization, filters, now))
                tables = [(rkeg_table if self.report_type == 'rkeg' else incidents_table)(records)]
        filter_description = '; '.join(f'{form.fields[key].label}: {value}' for key, value in filters.items() if value not in (None, '')) or 'Keine Filter'
        if request.GET.get('format') == 'csv':
            if not valid or self.report_type == 'management':
                return HttpResponse('Ungueltige Filter oder kein tabellarischer CSV-Bericht.', status=400, content_type='text/plain; charset=utf-8')
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="rkeg-{self.report_type}-{now:%Y%m%d}.csv"'
            response.write('\ufeff')
            writer = csv.writer(response, delimiter=';', lineterminator='\r\n')
            writer.writerow(['Organisation', 'Berichtstyp', 'Erstellt am', 'Erstellt von', 'Filter'] + list(tables[0].headings))
            metadata = [self.organization.name, REPORTS[self.report_type], display(now), user_name(request.user), filter_description]
            for row in tables[0].rows:
                writer.writerow([csv_cell(value) for value in metadata + list(row.cells)])
            return response
        page = None
        if tables and self.report_type != 'management' and not self.print_view:
            page = Paginator(tables[0].rows, 50).get_page(request.GET.get('page'))
            tables[0].rows = list(page)
        query = request.GET.copy()
        for key in ('format', 'page'):
            query.pop(key, None)
        context = self.get_context_data(report_title=REPORTS[self.report_type], report_type=self.report_type,
            report_created_at=now, report_actor=request.user, filter_form=form, filter_description=filter_description,
            metrics=metrics, tables=tables, print_view=self.print_view, filter_query=query.urlencode(),
            page_obj=page, paginator=page.paginator if page else None,
            is_paginated=bool(page and page.paginator.num_pages > 1))
        return self.render_to_response(context)
