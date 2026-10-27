from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from organizations.mixins import OrganizationQuerysetMixin, OrganizationWritePermissionMixin
from .filters import IncidentFilterForm
from .forms import IncidentActionForm, IncidentEventForm, IncidentForm
from .models import Incident, IncidentAction, IncidentEvent


class IncidentListView(OrganizationQuerysetMixin, ListView):
    model = Incident
    template_name = 'incidents/list.html'
    context_object_name = 'incidents'
    paginate_by = 25

    def get_queryset(self):
        self.filter_form = IncidentFilterForm(self.request.GET)
        return self.filter_form.filter_queryset(super().get_queryset().select_related('responsible_user'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(filter_form=self.filter_form, incident_query=self.request.GET.urlencode())
        return context


class IncidentDetailView(OrganizationQuerysetMixin, DetailView):
    model = Incident
    template_name = 'incidents/detail.html'
    context_object_name = 'incident'

    def get_queryset(self):
        return super().get_queryset().select_related('organization', 'responsible_user', 'created_by')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            incident_query=self.request.GET.get('register', ''),
            affected_services=self.object.affected_services.filter(organization=self.organization).order_by('name', 'pk'),
            affected_locations=self.object.affected_locations.filter(organization=self.organization).order_by('name', 'pk'),
            linked_risks=self.object.risks.filter(organization=self.organization).order_by('title', 'pk'),
            events=self.object.events.filter(organization=self.organization)
                .select_related('created_by').order_by('event_time', 'pk'),
            actions=self.object.actions.filter(organization=self.organization)
                .select_related('responsible_user').order_by('-created_at', '-pk'),
        )
        from .rkeg_reporting import current_manual_assessment, deadlines, evaluate_incident
        evaluation = evaluate_incident(self.object)
        context.update(rkeg_evaluation=evaluation, rkeg_deadlines=deadlines(self.object, evaluation),
            rkeg_manual=current_manual_assessment(self.object, evaluation),
            rkeg_history=self.object.rkeg_assessments.filter(organization=self.organization).select_related('assessed_by').order_by('-assessed_at', '-pk'),
            incident_reports=self.object.reports.filter(organization=self.organization).order_by('-created_at', '-pk'))
        return context


class IncidentFormMixin:
    model = Incident
    form_class = IncidentForm
    template_name = 'incidents/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(organization=self.organization, user=self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['incident_query'] = self.request.GET.get('register', '')
        return context

    def get_success_url(self):
        url = reverse('incidents:detail', args=[self.object.pk])
        query = self.request.GET.get('register')
        return url + '?' + urlencode({'register': query}) if query else url

    def form_valid(self, form):
        # Save the incident and its risk associations as one operation.
        with transaction.atomic():
            response = super().form_valid(form)
        messages.success(self.request, 'Vorfall wurde gespeichert.')
        return response


class IncidentCreateView(OrganizationQuerysetMixin, OrganizationWritePermissionMixin, IncidentFormMixin, CreateView):
    pass


class IncidentUpdateView(OrganizationQuerysetMixin, OrganizationWritePermissionMixin, IncidentFormMixin, UpdateView):
    pass


class IncidentChildMixin(OrganizationQuerysetMixin):
    def get_incident(self):
        if not hasattr(self, 'incident'):
            self.incident = get_object_or_404(Incident.objects.filter(organization=self.organization),
                                            pk=self.kwargs['incident_pk'])
        return self.incident

    def get_queryset(self):
        return super().get_queryset().filter(incident=self.get_incident())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(incident=self.get_incident(), user=self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['incident'] = self.get_incident()
        return context

    def get_success_url(self):
        return reverse('incidents:detail', args=[self.get_incident().pk])


class IncidentEventCreateView(IncidentChildMixin, OrganizationWritePermissionMixin, CreateView):
    model = IncidentEvent
    form_class = IncidentEventForm
    template_name = 'incidents/event_form.html'


class IncidentActionCreateView(IncidentChildMixin, OrganizationWritePermissionMixin, CreateView):
    model = IncidentAction
    form_class = IncidentActionForm
    template_name = 'incidents/action_form.html'


class IncidentActionUpdateView(IncidentChildMixin, OrganizationWritePermissionMixin, UpdateView):
    model = IncidentAction
    form_class = IncidentActionForm
    template_name = 'incidents/action_form.html'
