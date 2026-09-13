from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from .models import Membership

ORGANIZATION_SESSION_KEY = 'active_organization_id'
RISK_WRITE_ROLES = frozenset({
    Membership.Role.ADMIN,
    Membership.Role.RESILIENCE_MANAGER,
    Membership.Role.RISK_MANAGER,
    Membership.Role.EDITOR,
})


@method_decorator(never_cache, name='dispatch')
class OrganizationContextMixin(LoginRequiredMixin):
    require_organization = True

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        # The session is a selection hint, never evidence of authorization.
        self.memberships = list(
            request.user.memberships.filter(is_active=True)
            .select_related('organization').order_by('organization__name', 'pk')
        )
        selected_id = request.session.get(ORGANIZATION_SESSION_KEY)
        self.membership = next(
            (item for item in self.memberships if item.organization_id == selected_id), None
        )
        if len(self.memberships) == 1:
            self.membership = self.memberships[0]
        if self.membership:
            request.session[ORGANIZATION_SESSION_KEY] = self.membership.organization_id
        else:
            request.session.pop(ORGANIZATION_SESSION_KEY, None)
        self.organization = self.membership.organization if self.membership else None

        if self.require_organization and self.organization is None:
            return redirect('organizations:select')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            active_organization=self.organization,
            active_membership=self.membership,
            memberships=self.memberships,
            can_write_risks=bool(self.membership and self.membership.role in RISK_WRITE_ROLES),
        )
        return context


class OrganizationQuerysetMixin(OrganizationContextMixin):
    def get_queryset(self):
        return super().get_queryset().filter(organization=self.organization)


class RiskWritePermissionMixin:
    def dispatch(self, request, *args, **kwargs):
        if self.membership.role not in RISK_WRITE_ROLES:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
