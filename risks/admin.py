from django.contrib import admin

from core.admin import SuperuserOnlyAdminMixin
from .models import Risk


@admin.register(Risk)
class RiskAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'organization', 'status', 'created_by', 'updated_at')
    list_filter = ('status', 'organization')
    search_fields = ('title', 'description', 'organization__name')
    autocomplete_fields = ('organization', 'created_by')
    list_select_related = ('organization', 'created_by')
    readonly_fields = ('created_at', 'updated_at')
