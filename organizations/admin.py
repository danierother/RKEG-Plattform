from django.contrib import admin

from core.admin import SuperuserOnlyAdminMixin
from .models import Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'legal_name', 'created_at', 'updated_at')
    search_fields = ('name', 'legal_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Membership)
class MembershipAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('user', 'organization', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active', 'organization')
    search_fields = ('user__username', 'organization__name')
    autocomplete_fields = ('user', 'organization')
    list_select_related = ('user', 'organization')
    readonly_fields = ('created_at',)
