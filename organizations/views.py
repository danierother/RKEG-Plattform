from django.shortcuts import redirect
from django.views.generic import FormView, TemplateView
from django.urls import reverse
from django.core import signing
from django import forms
from audit.services import audited_change

from .forms import OrganizationSelectionForm
from .forms import OrganizationRKEGForm
from .mixins import OrganizationWritePermissionMixin
from .mixins import ORGANIZATION_SESSION_KEY, OrganizationContextMixin


class OrganizationSelectionView(OrganizationContextMixin, FormView):
    require_organization = False
    template_name = 'organizations/select.html'
    form_class = OrganizationSelectionForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(user=self.request.user)
        return kwargs

    def get_initial(self):
        return {'organization': self.organization}

    def render_to_response(self, context, **response_kwargs):
        if not self.memberships:
            response_kwargs['status'] = 403
        return super().render_to_response(context, **response_kwargs)

    def form_valid(self, form):
        self.request.session[ORGANIZATION_SESSION_KEY] = form.cleaned_data['organization'].pk
        return redirect('dashboard')


class OrganizationDetailView(OrganizationContextMixin, TemplateView):
    template_name = 'organizations/detail.html'


class OrganizationRKEGView(OrganizationContextMixin, OrganizationWritePermissionMixin, FormView):
    form_class = OrganizationRKEGForm
    template_name = 'organizations/rkeg_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.organization
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['organization_context'] = forms.CharField(widget=forms.HiddenInput,
            initial=signing.dumps({'org': self.organization.pk, 'user': self.request.user.pk}, salt='org-rkeg'))
        return form

    def form_valid(self, form):
        try:
            context = signing.loads(form.cleaned_data['organization_context'], salt='org-rkeg')
        except signing.BadSignature:
            context = None
        if context != {'org': self.organization.pk, 'user': self.request.user.pk}:
            form.add_error(None, 'Organisationskontext geaendert. Formular neu laden.')
            return self.form_invalid(form)
        with audited_change(self.organization, organization=self.organization, actor=self.request.user, source='WEB'):
            form.save()
        return redirect(reverse('organizations:detail'))
