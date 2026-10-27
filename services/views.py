from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from organizations.mixins import OrganizationQuerysetMixin, OrganizationWritePermissionMixin
from .filters import LocationFilterForm, ServiceFilterForm
from .forms import CriticalServiceForm, LocationForm, ServiceDependencyForm
from .models import CriticalService, Location, ServiceDependency


class FilteredListMixin:
    paginate_by = 25

    def get_queryset(self):
        self.filter_form = self.filter_class(self.request.GET)
        return self.filter_form.filter_queryset(super().get_queryset())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        return context


class LocationListView(OrganizationQuerysetMixin, FilteredListMixin, ListView):
    model = Location
    filter_class = LocationFilterForm
    template_name = 'services/location_list.html'
    context_object_name = 'locations'


class ServiceListView(OrganizationQuerysetMixin, FilteredListMixin, ListView):
    model = CriticalService
    filter_class = ServiceFilterForm
    template_name = 'services/service_list.html'
    context_object_name = 'services'

    def get_queryset(self):
        return super().get_queryset().select_related('service_owner').annotate(
            location_count=Count('locations', distinct=True, filter=Q(locations__organization=self.organization)),
            dependency_count=Count('dependencies', distinct=True, filter=Q(dependencies__organization=self.organization)),
        )


class LocationDetailView(OrganizationQuerysetMixin, DetailView):
    model = Location
    template_name = 'services/location_detail.html'
    context_object_name = 'location'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['services'] = self.object.critical_services.filter(organization=self.organization).order_by('name', 'pk')
        return context


class ServiceDetailView(OrganizationQuerysetMixin, DetailView):
    model = CriticalService
    template_name = 'services/service_detail.html'
    context_object_name = 'service'

    def get_queryset(self):
        return super().get_queryset().select_related('service_owner')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for relation in ('locations', 'dependencies', 'risks', 'incidents'):
            context[relation] = getattr(self.object, relation).filter(organization=self.organization).order_by('pk')
        return context


class OrganizationFormMixin:
    template_name = 'services/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(organization=self.organization, user=self.request.user)
        return kwargs

    def get_success_url(self):
        return reverse(self.detail_url_name, args=[self.object.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(form_title=self.form_title, back_url=reverse(self.list_url_name))
        return context

    def form_valid(self, form):
        with transaction.atomic():
            return super().form_valid(form)


class LocationFormMixin(OrganizationFormMixin):
    model = Location
    form_class = LocationForm
    form_title = 'Standort'
    detail_url_name = 'services:location-detail'
    list_url_name = 'services:location-list'


class ServiceFormMixin(OrganizationFormMixin):
    model = CriticalService
    form_class = CriticalServiceForm
    form_title = 'Kritische Dienstleistung'
    detail_url_name = 'services:detail'
    list_url_name = 'services:list'


class LocationCreateView(OrganizationQuerysetMixin, OrganizationWritePermissionMixin, LocationFormMixin, CreateView):
    pass


class LocationUpdateView(OrganizationQuerysetMixin, OrganizationWritePermissionMixin, LocationFormMixin, UpdateView):
    pass


class ServiceCreateView(OrganizationQuerysetMixin, OrganizationWritePermissionMixin, ServiceFormMixin, CreateView):
    pass


class ServiceUpdateView(OrganizationQuerysetMixin, OrganizationWritePermissionMixin, ServiceFormMixin, UpdateView):
    pass


class DependencyParentMixin(OrganizationQuerysetMixin):
    model = ServiceDependency

    def get_service(self):
        if not hasattr(self, 'service'):
            self.service = get_object_or_404(CriticalService.objects.filter(organization=self.organization), pk=self.kwargs['service_pk'])
        return self.service

    def get_queryset(self):
        return super().get_queryset().filter(service=self.get_service())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['service'] = self.get_service()
        return context


class DependencyDetailView(DependencyParentMixin, DetailView):
    template_name = 'services/dependency_detail.html'
    context_object_name = 'dependency'


class DependencyFormMixin:
    form_class = ServiceDependencyForm
    template_name = 'services/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['service'] = self.get_service()
        return kwargs

    def get_success_url(self):
        return reverse('services:detail', args=[self.get_service().pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(form_title='Abh\u00e4ngigkeit', back_url=self.get_success_url())
        return context


class DependencyCreateView(DependencyParentMixin, OrganizationWritePermissionMixin, DependencyFormMixin, CreateView):
    pass


class DependencyUpdateView(DependencyParentMixin, OrganizationWritePermissionMixin, DependencyFormMixin, UpdateView):
    pass
