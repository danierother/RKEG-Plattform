from django.contrib import admin
from django.db import transaction

from core.admin import SuperuserOnlyAdminMixin
from .models import AuditEvent
from .services import audited_change, audited_delete


class AuditedAdminMixin:
    def save_model(self, request, obj, form, change):
        organization = obj if obj._meta.label_lower == 'organizations.organization' else obj.organization
        with audited_change(obj, organization=organization, actor=request.user, source='ADMIN'):
            super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return self.model._meta.label_lower != 'organizations.organization' and super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        audited_delete(obj, organization=obj.organization, actor=request.user, source='ADMIN')

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            for obj in queryset:
                self.delete_model(request, obj)


@admin.register(AuditEvent)
class AuditEventAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('timestamp', 'organization', 'actor', 'action', 'object_type', 'object_repr', 'source')
    list_filter = ('organization', 'action', 'source', 'object_type')
    search_fields = ('object_repr', 'change_summary')
    list_select_related = ('organization', 'actor')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
