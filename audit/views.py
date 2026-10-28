from django.db.models import Q
from django.views.generic import ListView
from organizations.mixins import OrganizationQuerysetMixin
from .forms import AuditFilterForm
from .models import AuditEvent


class AuditListView(OrganizationQuerysetMixin, ListView):
    model = AuditEvent
    template_name = 'audit/list.html'
    context_object_name = 'events'
    paginate_by = 50

    def get_queryset(self):
        queryset = super().get_queryset().select_related('actor')
        self.filter_form = AuditFilterForm(self.request.GET, organization=self.organization)
        if not self.filter_form.is_valid():
            return queryset.none()
        data = self.filter_form.cleaned_data
        for field in ('actor', 'object_type', 'action'):
            if data.get(field):
                queryset = queryset.filter(**{field: data[field]})
        for field, lookup in (('date_from', 'timestamp__date__gte'), ('date_to', 'timestamp__date__lte')):
            if data.get(field):
                queryset = queryset.filter(**{lookup: data[field]})
        if data.get('q'):
            queryset = queryset.filter(Q(object_repr__icontains=data['q']) | Q(change_summary__icontains=data['q']))
        return queryset

    def get_context_data(self, **kwargs):
        return dict(super().get_context_data(**kwargs), filter_form=self.filter_form)
