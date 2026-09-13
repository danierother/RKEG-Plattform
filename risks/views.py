from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from organizations.mixins import OrganizationQuerysetMixin, RiskWritePermissionMixin
from .forms import RiskForm, RiskMeasureForm
from .models import Risk, RiskMeasure


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['measures'] = self.object.measures.filter(
            organization=self.organization,
        ).select_related('responsible_user').order_by('-created_at', '-pk')
        return context


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

    def form_valid(self, form):
        if self.request.POST.get('action') == 'preview':
            return self.render_to_response(self.get_context_data(form=form))
        response = super().form_valid(form)
        messages.success(self.request, 'Risiko wurde gespeichert.')
        return response


class RiskCreateView(OrganizationQuerysetMixin, RiskWritePermissionMixin, RiskFormMixin, CreateView):
    def form_valid(self, form):
        form.instance.organization = self.organization
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class RiskUpdateView(OrganizationQuerysetMixin, RiskWritePermissionMixin, RiskFormMixin, UpdateView):
    pass


class RiskMeasureParentMixin(OrganizationQuerysetMixin):
    def get_risk(self):
        if not hasattr(self, 'risk'):
            self.risk = get_object_or_404(
                Risk.objects.filter(organization=self.organization), pk=self.kwargs['risk_pk'],
            )
        return self.risk

    def get_queryset(self):
        return super().get_queryset().filter(risk=self.get_risk())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['risk'] = self.get_risk()
        return context


class RiskMeasureFormMixin:
    model = RiskMeasure
    form_class = RiskMeasureForm
    template_name = 'risks/measure_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['risk'] = self.get_risk()
        return kwargs

    def get_success_url(self):
        return reverse('risks:detail', kwargs={'pk': self.get_risk().pk})


class RiskMeasureCreateView(RiskMeasureParentMixin, RiskWritePermissionMixin, RiskMeasureFormMixin, CreateView):
    pass


class RiskMeasureUpdateView(RiskMeasureParentMixin, RiskWritePermissionMixin, RiskMeasureFormMixin, UpdateView):
    pass


class RiskMeasureDetailView(RiskMeasureParentMixin, DetailView):
    model = RiskMeasure
    template_name = 'risks/measure_detail.html'
    context_object_name = 'measure'
