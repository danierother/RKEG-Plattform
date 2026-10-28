from .services import audited_change, object_history


class AuditFormMixin:
    def form_valid(self, form):
        with audited_change(form.instance, organization=self.organization, actor=self.request.user, source='WEB'):
            return super().form_valid(form)


class AuditHistoryMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['object_audit_events'] = object_history(self.object, self.organization)
        return context
