from django.contrib import admin
from core.admin import SuperuserOnlyAdminMixin
from .models import CriticalService, Location, ServiceDependency


class ReadOnlyServiceAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Location)
class LocationAdmin(ReadOnlyServiceAdmin):
    list_display = ('name', 'organization', 'location_type', 'city', 'is_active', 'updated_at')
    search_fields = ('name', 'city', 'description')
    list_filter = ('organization', 'location_type', 'is_active')
    list_select_related = ('organization',)


@admin.register(CriticalService)
class CriticalServiceAdmin(ReadOnlyServiceAdmin):
    list_display = ('name', 'organization', 'status', 'criticality', 'recovery_priority', 'service_owner')
    search_fields = ('name', 'description')
    list_filter = ('organization', 'status', 'criticality', 'recovery_priority')
    list_select_related = ('organization', 'service_owner')


@admin.register(ServiceDependency)
class ServiceDependencyAdmin(ReadOnlyServiceAdmin):
    list_display = ('name', 'service', 'organization', 'dependency_type', 'criticality', 'single_point_of_failure')
    search_fields = ('name', 'description', 'supplier_name')
    list_filter = ('organization', 'dependency_type', 'criticality', 'internal_external', 'single_point_of_failure')
    list_select_related = ('organization', 'service')
