from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import Client
from django.urls import reverse
from secrets import token_urlsafe

from core.test_helpers import TenantTestCase


class UserTests(TestCase):
    def test_create_user(self):
        user = get_user_model().objects.create_user('alice', password='test-password')
        self.assertEqual(user._meta.label, 'accounts.User')
        self.assertEqual(str(user), 'alice')
        self.assertTrue(user.check_password('test-password'))
        self.assertFalse(user.is_staff)

    def test_create_superuser(self):
        user = get_user_model().objects.create_superuser('admin', password='test-password')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)


class AuthenticationViewTests(TenantTestCase):
    def test_anonymous_internal_pages_redirect_to_login(self):
        self.client.logout()
        urls = [
            '/', '/dashboard/', '/risks/', '/risks/new/',
            reverse('risks:detail', args=[self.risk.pk]),
            reverse('risks:edit', args=[self.risk.pk]),
            '/organizations/', '/organizations/select/',
        ]
        for url in urls:
            for method in ('get', 'post'):
                with self.subTest(url=url, method=method):
                    self.assertRedirects(
                        getattr(self.client, method)(url), f'/login/?next={url}',
                        fetch_redirect_response=False,
                    )

    def test_login_with_custom_user(self):
        self.client.logout()
        password = token_urlsafe(24)
        self.user.set_password(password)
        self.user.save()
        self.assertContains(self.client.get('/login/'), 'Anmelden')
        response = self.client.post('/login/', {'username': self.user.username, 'password': password})
        self.assertRedirects(response, '/dashboard/')

    def test_login_failure_and_inactive_user(self):
        self.client.logout()
        password = token_urlsafe(24)
        self.user.set_password(password)
        self.user.is_active = False
        self.user.save()
        for submitted_password in (token_urlsafe(24), password):
            response = self.client.post('/login/', {
                'username': self.user.username, 'password': submitted_password,
            })
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
            self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_rejects_external_next(self):
        self.client.logout()
        password = token_urlsafe(24)
        self.user.set_password(password)
        self.user.save()
        response = self.client.post('/login/', {
            'username': self.user.username, 'password': password, 'next': 'https://example.com/',
        })
        self.assertRedirects(response, '/dashboard/')

    def test_login_preserves_internal_next(self):
        self.client.logout()
        password = token_urlsafe(24)
        self.user.set_password(password)
        self.user.save()
        response = self.client.post('/login/?next=/risks/', {
            'username': self.user.username, 'password': password, 'next': '/risks/',
        })
        self.assertRedirects(response, '/risks/')

    def test_logout_requires_post_and_clears_session(self):
        self.select_organization(self.organization)
        self.assertEqual(self.client.get('/logout/').status_code, 405)
        self.assertRedirects(self.client.post('/logout/'), '/login/')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertNotIn('active_organization_id', self.client.session)
        self.assertRedirects(self.client.get('/risks/'), '/login/?next=/risks/')

    def test_authentication_endpoints_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/login/', {}).status_code, 403)
        client.force_login(self.user)
        self.assertEqual(client.post('/logout/').status_code, 403)
