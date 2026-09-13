class SuperuserOnlyAdminMixin:
    """Reserve the central admin for system administrators, across tenants."""

    def _is_system_admin(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_module_permission(self, request):
        return self._is_system_admin(request)

    def has_view_permission(self, request, obj=None):
        return self._is_system_admin(request)

    def has_add_permission(self, request):
        return self._is_system_admin(request)

    def has_change_permission(self, request, obj=None):
        return self._is_system_admin(request)

    def has_delete_permission(self, request, obj=None):
        return self._is_system_admin(request)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset if self._is_system_admin(request) else queryset.none()
