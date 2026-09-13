from django.contrib import admin

from core.admin import SuperuserOnlyAdminMixin
from .models import Risk, RiskMeasure


@admin.register(Risk)
class RiskAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'organization', 'status', 'created_by', 'updated_at')
    list_filter = ('status', 'organization')
    search_fields = ('title', 'description', 'organization__name')
    autocomplete_fields = ('organization', 'created_by')
    list_select_related = ('organization', 'created_by')
    readonly_fields = ('risk_score', 'risk_class', 'created_at', 'updated_at')


@admin.register(RiskMeasure)
class RiskMeasureAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'risk', 'organization', 'status', 'responsible_user', 'due_date')
    list_filter = ('status', 'organization')
    search_fields = ('title', 'risk__title')
    readonly_fields = ('organization', 'created_at', 'updated_at')
    list_select_related = ('risk', 'organization', 'responsible_user')

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (('risk',) if obj else ())
