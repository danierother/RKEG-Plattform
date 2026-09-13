from django.shortcuts import redirect
from django.views.generic import FormView, TemplateView

from .forms import OrganizationSelectionForm
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
