from django.contrib import admin

from core.admin import SuperuserOnlyAdminMixin
from .models import Incident, IncidentAction, IncidentEvent


class IncidentReadOnlyAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """Use the tenant-aware application forms for writes, including M2M changes."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Incident)
class IncidentAdmin(IncidentReadOnlyAdmin):
    list_display = ('title', 'organization', 'status', 'severity', 'reporting_status', 'updated_at')
    list_filter = ('organization', 'status', 'severity', 'reporting_status')
    search_fields = ('title', 'description', 'impact_description')
    list_select_related = ('organization',)


@admin.register(IncidentEvent)
class IncidentEventAdmin(IncidentReadOnlyAdmin):
    list_display = ('incident', 'event_type', 'event_time', 'created_by')
    list_select_related = ('incident', 'created_by')


@admin.register(IncidentAction)
class IncidentActionAdmin(IncidentReadOnlyAdmin):
    list_display = ('title', 'incident', 'status', 'responsible_user', 'due_date')
    list_select_related = ('incident', 'responsible_user')
