from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, FormView, UpdateView

from organizations.mixins import OrganizationQuerysetMixin, OrganizationWritePermissionMixin
from .models import Incident, IncidentReport, IncidentRKEGAssessment, IncidentServiceImpact
from .reporting_forms import AssessmentForm, IncidentReportForm, ReportingFactsForm, ServiceImpactForm
from .rkeg_reporting import record_assessment
from .views import IncidentChildMixin
from audit.mixins import AuditFormMixin


class ReportingPageMixin(AuditFormMixin):
    template_name = 'incidents/reporting_form.html'
    page_title = 'RKEG-Meldepruefung'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.page_title
        return context


class ReportingFactsUpdateView(OrganizationQuerysetMixin, OrganizationWritePermissionMixin, ReportingPageMixin, UpdateView):
    model = Incident
    form_class = ReportingFactsForm
    page_title = 'RKEG-Pruefdaten'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['incident'] = self.object
        return context

    def get_success_url(self):
        return reverse('incidents:detail', args=[self.object.pk])


class ServiceImpactUpdateView(IncidentChildMixin, OrganizationWritePermissionMixin, ReportingPageMixin, UpdateView):
    model = IncidentServiceImpact
    form_class = ServiceImpactForm
    page_title = 'Dienstbezogene RKEG-Pruefdaten'

    def get_object(self, queryset=None):
        incident = self.get_incident()
        self.service = get_object_or_404(incident.affected_services.filter(organization=self.organization), pk=self.kwargs['service_pk'])
        return IncidentServiceImpact.objects.filter(incident=incident, organization=self.organization, service=self.service).first()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop('user')
        kwargs['service'] = self.service
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['service'] = self.service
        return context


class AssessmentCreateView(IncidentChildMixin, OrganizationWritePermissionMixin, ReportingPageMixin, FormView):
    form_class = AssessmentForm
    page_title = 'RKEG-Bewertung dokumentieren'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop('incident')
        kwargs.pop('user')
        return kwargs

    def form_valid(self, form):
        assessment = record_assessment(self.get_incident(), self.request.user, source='WEB', **form.cleaned_data)
        return redirect('incidents:assessment-detail', incident_pk=self.get_incident().pk, pk=assessment.pk)


class AssessmentDetailView(IncidentChildMixin, DetailView):
    model = IncidentRKEGAssessment
    template_name = 'incidents/assessment_detail.html'
    context_object_name = 'assessment'


class ReportCreateView(IncidentChildMixin, OrganizationWritePermissionMixin, ReportingPageMixin, CreateView):
    model = IncidentReport
    form_class = IncidentReportForm
    page_title = 'Interner Meldungsentwurf'


class ReportUpdateView(IncidentChildMixin, OrganizationWritePermissionMixin, ReportingPageMixin, UpdateView):
    model = IncidentReport
    form_class = IncidentReportForm
    page_title = 'Meldungsentwurf bearbeiten'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.status != IncidentReport.Status.DRAFT:
            raise PermissionDenied('Dokumentierte Uebermittlungen sind unveraenderlich.')
        return obj


class ReportDetailView(IncidentChildMixin, DetailView):
    model = IncidentReport
    template_name = 'incidents/report_detail.html'
    context_object_name = 'report'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report_fields'] = [(self.object._meta.get_field(name).verbose_name, getattr(self.object, name))
            for name in IncidentReportForm.Meta.fields[3:]]
        return context
