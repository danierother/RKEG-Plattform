from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group

from core.admin import SuperuserOnlyAdminMixin
from .models import User


@admin.register(User)
class CustomUserAdmin(SuperuserOnlyAdminMixin, UserAdmin):
    pass


# Groups carry global permissions and belong to the system administration too.
admin.site.unregister(Group)


@admin.register(Group)
class SystemGroupAdmin(SuperuserOnlyAdminMixin, GroupAdmin):
    pass
