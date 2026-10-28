from django.contrib import messages
from django.db import transaction
from urllib.parse import urlencode
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from organizations.mixins import OrganizationQuerysetMixin, RiskWritePermissionMixin
from .forms import RiskForm, RiskMeasureForm, RiskControlForm
from .models import Risk, RiskMeasure, RiskControl
from .filters import RiskFilterForm
from .assessment import calculate_score, classify_score
from audit.mixins import AuditFormMixin, AuditHistoryMixin


class RiskListView(OrganizationQuerysetMixin, ListView):
    model = Risk
    template_name = 'risks/list.html'
    context_object_name = 'risks'
    paginate_by = 25
    ordering = ('-created_at', '-pk')

    def get_queryset(self):
        self.filter_form = RiskFilterForm(self.request.GET)
        return self.filter_form.filter_queryset(super().get_queryset().select_related('created_by'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.filter_form
        context['register_query'] = self.request.GET.urlencode()
        return context


class RiskMatrixView(OrganizationQuerysetMixin, ListView):
    model = Risk
    template_name = 'risks/matrix.html'

    def get_queryset(self):
        self.matrix_type = 'residual' if self.request.GET.get('type') == 'residual' else 'gross'
        self.field_prefix = 'residual_' if self.matrix_type == 'residual' else ''
        return super().get_queryset().only(
            'id', 'title', f'{self.field_prefix}likelihood', f'{self.field_prefix}impact',
        ).order_by('title', 'pk')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        groups = {(likelihood, impact): [] for likelihood in range(1, 6) for impact in range(1, 6)}
        for risk in self.object_list:
            groups[(getattr(risk, f'{self.field_prefix}likelihood'),
                    getattr(risk, f'{self.field_prefix}impact'))].append(risk)
        rows = []
        for likelihood, label in reversed(Risk.Likelihood.choices):
            cells = []
            for impact, _ in Risk.Impact.choices:
                score = calculate_score(likelihood, impact)
                risks = groups[(likelihood, impact)]
                cells.append({'likelihood': likelihood, 'impact': impact, 'score': score,
                              'band': classify_score(score), 'risks': risks, 'count': len(risks)})
            rows.append({'likelihood': likelihood, 'label': label, 'cells': cells})
        context.update(matrix_rows=rows, impact_choices=Risk.Impact.choices,
                       matrix_type=self.matrix_type,
                       matrix_title='Restrisikomatrix' if self.matrix_type == 'residual' else 'Bruttorisikomatrix')
        return context


class RiskDetailView(OrganizationQuerysetMixin, AuditHistoryMixin, DetailView):
    model = Risk
    template_name = 'risks/detail.html'
    context_object_name = 'risk'

    def get_queryset(self):
        return super().get_queryset().select_related('organization', 'created_by')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['register_query'] = self.request.GET.get('register', '')
        context['measures'] = self.object.measures.filter(
            organization=self.organization,
        ).select_related('responsible_user').order_by('-created_at', '-pk')
        context['controls'] = self.object.controls.filter(
            organization=self.organization,
        ).select_related('responsible_user').order_by('-created_at', '-pk')
        context['critical_services'] = self.object.critical_services.filter(organization=self.organization).order_by('name', 'pk')
        return context


class RiskFormMixin(AuditFormMixin):
    model = Risk
    form_class = RiskForm
    template_name = 'risks/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(organization=self.organization, user=self.request.user)
        return kwargs

    def get_success_url(self):
        url = reverse('risks:detail', kwargs={'pk': self.object.pk})
        query = self.request.GET.get('register')
        return url + '?' + urlencode({'register': query}) if query else url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['register_query'] = self.request.GET.get('register', '')
        return context

    def form_valid(self, form):
        if self.request.POST.get('action') == 'preview':
            return self.render_to_response(self.get_context_data(form=form))
        with transaction.atomic():
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


class RiskMeasureFormMixin(AuditFormMixin):
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


class RiskControlFormMixin(RiskMeasureFormMixin):
    model = RiskControl
    form_class = RiskControlForm
    template_name = 'risks/control_form.html'


class RiskControlCreateView(RiskMeasureParentMixin, RiskWritePermissionMixin, RiskControlFormMixin, CreateView):
    pass


class RiskControlUpdateView(RiskMeasureParentMixin, RiskWritePermissionMixin, RiskControlFormMixin, UpdateView):
    pass


class RiskControlDetailView(RiskMeasureParentMixin, DetailView):
    model = RiskControl
    template_name = 'risks/control_detail.html'
    context_object_name = 'control'
