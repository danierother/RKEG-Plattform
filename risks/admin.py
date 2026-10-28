from django.contrib import admin

from core.admin import SuperuserOnlyAdminMixin
from .models import Risk, RiskMeasure, RiskControl
from audit.admin import AuditedAdminMixin


@admin.register(Risk)
class RiskAdmin(AuditedAdminMixin, SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'organization', 'status', 'created_by', 'updated_at')
    list_filter = ('status', 'organization')
    search_fields = ('title', 'description', 'organization__name')
    autocomplete_fields = ('organization', 'created_by')
    list_select_related = ('organization', 'created_by')
    readonly_fields = ('risk_score', 'risk_class', 'residual_risk_score', 'residual_risk_class',
                       'created_at', 'updated_at', 'critical_services')


@admin.register(RiskMeasure)
class RiskMeasureAdmin(AuditedAdminMixin, SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'risk', 'organization', 'status', 'responsible_user', 'due_date')
    list_filter = ('status', 'organization')
    search_fields = ('title', 'risk__title')
    readonly_fields = ('organization', 'created_at', 'updated_at')
    list_select_related = ('risk', 'organization', 'responsible_user')

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (('risk',) if obj else ())


@admin.register(RiskControl)
class RiskControlAdmin(RiskMeasureAdmin):
    list_display = ('title', 'risk', 'organization', 'control_type', 'effectiveness', 'responsible_user')
    list_filter = ('control_type', 'effectiveness', 'organization')
