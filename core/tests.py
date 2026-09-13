from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse

from organizations.models import Membership, Organization
from risks.models import Risk


class AdminAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('staff', is_staff=True)
        self.user.user_permissions.set(Permission.objects.all())
        self.own = Organization.objects.create(name='Own organization')
        self.other = Organization.objects.create(name='Other organization')
        Membership.objects.create(user=self.user, organization=self.own, role=Membership.Role.ADMIN)
        self.risk = Risk.objects.create(
            organization=self.other, title='Other organization risk', created_by=self.user,
        )
        self.models = (get_user_model(), Group, Organization, Membership, Risk)

    def test_staff_with_global_permissions_cannot_access_registered_models(self):
        request = RequestFactory().get('/admin/')
        request.user = self.user
        for model in self.models:
            model_admin = admin.site._registry[model]
            with self.subTest(model=model):
                self.assertFalse(model_admin.has_module_permission(request))
                self.assertFalse(model_admin.has_view_permission(request))
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_change_permission(request))
                self.assertFalse(model_admin.has_delete_permission(request))
                self.assertFalse(model_admin.get_queryset(request).exists())

    def test_direct_admin_urls_and_autocomplete_deny_staff(self):
        self.client.force_login(self.user)
        for model in self.models:
            name = f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist'
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        for action in ('change', 'delete'):
            url = reverse(f'admin:risks_risk_{action}', args=[self.risk.pk])
            self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.get(reverse('admin:autocomplete'), {
            'app_label': 'risks', 'model_name': 'risk', 'field_name': 'organization',
        })
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access_admin(self):
        superuser = get_user_model().objects.create_superuser('admin', password='test-password')
        self.client.force_login(superuser)
        for model in self.models:
            name = f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist'
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
