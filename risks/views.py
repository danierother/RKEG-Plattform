from django.contrib import messages
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from organizations.mixins import OrganizationQuerysetMixin, RiskWritePermissionMixin
from .forms import RiskForm
from .models import Risk


class RiskListView(OrganizationQuerysetMixin, ListView):
    model = Risk
    template_name = 'risks/list.html'
    context_object_name = 'risks'
    paginate_by = 25
    ordering = ('-created_at', '-pk')

    def get_queryset(self):
        return super().get_queryset().select_related('created_by')


class RiskDetailView(OrganizationQuerysetMixin, DetailView):
    model = Risk
    template_name = 'risks/detail.html'
    context_object_name = 'risk'

    def get_queryset(self):
        return super().get_queryset().select_related('organization', 'created_by')


class RiskFormMixin:
    model = Risk
    form_class = RiskForm
    template_name = 'risks/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(organization=self.organization, user=self.request.user)
        return kwargs

    def get_success_url(self):
        return reverse('risks:detail', kwargs={'pk': self.object.pk})


class RiskCreateView(OrganizationQuerysetMixin, RiskWritePermissionMixin, RiskFormMixin, CreateView):
    def form_valid(self, form):
        form.instance.organization = self.organization
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Risiko wurde angelegt.')
        return response


class RiskUpdateView(OrganizationQuerysetMixin, RiskWritePermissionMixin, RiskFormMixin, UpdateView):
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Risiko wurde gespeichert.')
        return response
