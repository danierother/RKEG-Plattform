import io
import json
import logging
import os
import secrets
import subprocess
import sys
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings

from config.checks import production_configuration
from config.environment import load_environment
from config.logging import RedactingFormatter
from organizations.models import Membership, Organization


class EnvironmentTests(SimpleTestCase):
    def production(self, **overrides):
        return {'DJANGO_DEBUG': 'false', 'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
                'DJANGO_ALLOWED_HOSTS': 'test.example.org', **overrides}

    def test_local_defaults(self):
        config = load_environment({})
        self.assertTrue(config['DEBUG'])
        self.assertEqual(config['ALLOWED_HOSTS'], ['127.0.0.1', 'localhost'])
        self.assertEqual(config['CSRF_TRUSTED_ORIGINS'], [])
        self.assertFalse(config['SECRET_KEY_FROM_ENV'])
        self.assertGreaterEqual(len(config['SECRET_KEY']), 50)

    def test_true_values(self):
        for value in ('true', '1', 'yes', 'on', ' TRUE '):
            self.assertTrue(load_environment({'DJANGO_DEBUG': value})['DEBUG'])

    def test_false_values(self):
        for value in ('false', '0', 'no', 'off', ' FALSE '):
            self.assertFalse(load_environment(self.production(DJANGO_DEBUG=value))['DEBUG'])

    def test_invalid_booleans_fail_closed(self):
        for name in ('DJANGO_DEBUG', 'DJANGO_SECURE_SSL', 'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', 'DJANGO_SECURE_HSTS_PRELOAD'):
            for value in ('', 'maybe', '2'):
                with self.subTest(name=name, value=value), self.assertRaisesMessage(ImproperlyConfigured, name):
                    load_environment({name: value})

    def test_hosts_are_trimmed_deduplicated(self):
        config = load_environment({'DJANGO_ALLOWED_HOSTS': ' localhost,127.0.0.1,, localhost, test.example.org '})
        self.assertEqual(config['ALLOWED_HOSTS'], ['localhost', '127.0.0.1', 'test.example.org'])

    def test_production_requires_hosts_without_wildcard(self):
        for hosts in ('', ' , ', '*', 'example.org,*'):
            with self.assertRaisesMessage(ImproperlyConfigured, 'DJANGO_ALLOWED_HOSTS'):
                load_environment(self.production(DJANGO_ALLOWED_HOSTS=hosts))

    def test_hosts_reject_urls(self):
        for host in ('https://example.org', 'example.org/path', 'bad host'):
            with self.assertRaises(ImproperlyConfigured):
                load_environment({'DJANGO_ALLOWED_HOSTS': host})

    def test_origins_are_trimmed_deduplicated(self):
        config = load_environment({'DJANGO_CSRF_TRUSTED_ORIGINS': ' https://test.example.org, ,http://localhost:8000,https://test.example.org '})
        self.assertEqual(config['CSRF_TRUSTED_ORIGINS'], ['https://test.example.org', 'http://localhost:8000'])

    def test_invalid_origins_rejected(self):
        for origin in ('example.org', 'https://example.org/path', 'https://user:pass@example.org',
                       'https://example.org?key=value', 'ftp://example.org', 'https://localhost:bad', 'https://['):
            with self.subTest(origin=origin), self.assertRaisesMessage(ImproperlyConfigured, 'DJANGO_CSRF_TRUSTED_ORIGINS'):
                load_environment({'DJANGO_CSRF_TRUSTED_ORIGINS': origin})

    def test_https_configuration_rejects_http_origin(self):
        with self.assertRaises(ImproperlyConfigured):
            load_environment({'DJANGO_SECURE_SSL': 'true', 'DJANGO_CSRF_TRUSTED_ORIGINS': 'http://example.org'})

    def test_production_requires_secret(self):
        for secret in ('', '   '):
            with self.assertRaisesMessage(ImproperlyConfigured, 'DJANGO_SECRET_KEY'):
                load_environment(self.production(DJANGO_SECRET_KEY=secret))
        with self.assertRaisesMessage(ImproperlyConfigured, 'DJANGO_SECRET_KEY'):
            load_environment({'DJANGO_DEBUG': 'false'})

    def test_placeholder_and_weak_keys_rejected_without_disclosure(self):
        for key in ('replace-me', 'short', 'a'*64):
            with self.assertRaises(ImproperlyConfigured) as error:
                load_environment(self.production(DJANGO_SECRET_KEY=key))
            self.assertNotIn(key, str(error.exception))

    def test_fixed_secret_is_reused(self):
        env = self.production()
        with patch('config.environment.get_random_secret_key', side_effect=AssertionError('No random production key')):
            first, second = load_environment(env), load_environment(env)
        self.assertEqual(first['SECRET_KEY'], second['SECRET_KEY'])
        self.assertEqual(first['SECRET_KEY'], env['DJANGO_SECRET_KEY'])
        self.assertTrue(first['SECRET_KEY_FROM_ENV'])

    def test_local_fallback_is_explicitly_ephemeral(self):
        self.assertNotEqual(load_environment({})['SECRET_KEY'], load_environment({})['SECRET_KEY'])

    def test_secure_switch_controls_redirect_and_cookies(self):
        for value, expected in (('true', True), ('false', False)):
            config = load_environment({'DJANGO_SECURE_SSL': value})
            for name in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE'):
                self.assertEqual(config[name], expected)
            self.assertEqual(config['SECURE_HSTS_SECONDS'], 0)
            self.assertFalse(config['SECURE_HSTS_PRELOAD'])

    def test_local_http_has_no_hsts_or_secure_cookies(self):
        config = load_environment({})
        for name in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE',
                     'SECURE_HSTS_SECONDS', 'SECURE_HSTS_INCLUDE_SUBDOMAINS', 'SECURE_HSTS_PRELOAD'):
            self.assertFalse(config[name])

    def test_hsts_explicit_configuration(self):
        config = load_environment({'DJANGO_SECURE_SSL': 'true', 'DJANGO_SECURE_HSTS_SECONDS': '31536000',
                                  'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS': 'true', 'DJANGO_SECURE_HSTS_PRELOAD': 'true'})
        self.assertEqual(config['SECURE_HSTS_SECONDS'], 31536000)
        self.assertTrue(config['SECURE_HSTS_INCLUDE_SUBDOMAINS'])
        self.assertTrue(config['SECURE_HSTS_PRELOAD'])

    def test_unsafe_hsts_combinations_rejected(self):
        for env in ({'DJANGO_SECURE_HSTS_SECONDS': '300'}, {'DJANGO_SECURE_HSTS_SECONDS': '-1'},
                    {'DJANGO_SECURE_HSTS_SECONDS': 'no'}, {'DJANGO_SECURE_HSTS_SECONDS': '1.5'},
                    {'DJANGO_SECURE_SSL': 'true', 'DJANGO_SECURE_HSTS_PRELOAD': 'true'},
                    {'DJANGO_SECURE_SSL': 'true', 'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS': 'true'}):
            with self.assertRaises(ImproperlyConfigured):
                load_environment(env)

    def test_example_contains_only_placeholders(self):
        example = (settings.BASE_DIR / '.env.example').read_text()
        values = dict(line.split('=', 1) for line in example.splitlines() if line and not line.startswith('#'))
        self.assertEqual(values['DJANGO_SECRET_KEY'], 'replace-me')
        self.assertEqual(values['DJANGO_DEBUG'], 'true')
        self.assertEqual(values['DJANGO_SECURE_SSL'], 'false')
        self.assertNotIn(settings.SECRET_KEY, example)
        self.assertIn('.env', (settings.BASE_DIR / '.gitignore').read_text().splitlines())

    def test_staticfiles_found_and_collection_dry_run(self):
        from django.contrib.staticfiles import finders
        self.assertEqual(settings.STATIC_URL, '/static/')
        self.assertEqual(settings.STATIC_ROOT, settings.BASE_DIR / 'staticfiles')
        self.assertIsNotNone(finders.find('core/app.css'))
        output = io.StringIO()
        call_command('collectstatic', dry_run=True, interactive=False, verbosity=0, stdout=output)

    def test_no_upload_infrastructure_enabled(self):
        from django.apps import apps
        from django.db.models import FileField
        self.assertFalse(any(isinstance(field, FileField) for model in apps.get_models() for field in model._meta.fields))
        self.assertFalse(settings.MEDIA_ROOT)

    def test_custom_deploy_checks(self):
        with override_settings(DEBUG=True, SECRET_KEY_FROM_ENV=False):
            self.assertEqual([issue.id for issue in production_configuration(None)], ['rkeg.W001'])
        with override_settings(DEBUG=False, SECRET_KEY_FROM_ENV=False, ALLOWED_HOSTS=['*']):
            self.assertEqual({issue.id for issue in production_configuration(None)}, {'rkeg.E001', 'rkeg.E002'})
        with override_settings(DEBUG=False, SECRET_KEY_FROM_ENV=True, ALLOWED_HOSTS=['test.example.org']):
            self.assertEqual(production_configuration(None), [])

    def test_separate_processes_share_signed_session_with_fixed_key(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith('DJANGO_')}
        env.update(self.production(), DJANGO_SETTINGS_MODULE='config.settings')
        prefix = 'import django; django.setup(); from django.contrib.sessions.backends.db import SessionStore; '
        encoded = subprocess.run([sys.executable, '-c', prefix+'print(SessionStore().encode({"restart_test": True}))'],
                                 env=env, cwd=settings.BASE_DIR, capture_output=True, text=True, check=True, timeout=20).stdout.strip()
        decoded = subprocess.run([sys.executable, '-c', prefix+'import json, sys; print(json.dumps(SessionStore().decode(sys.stdin.read())))'],
                                 input=encoded, env=env, cwd=settings.BASE_DIR, capture_output=True, text=True, check=True, timeout=20)
        self.assertEqual(json.loads(decoded.stdout), {'restart_test': True})


class LoggingConfigurationTests(SimpleTestCase):
    def format_message(self, message, args=(), exc_info=None):
        return RedactingFormatter('%(levelname)s %(name)s: %(message)s').format(
            logging.LogRecord('rkeg.test', logging.ERROR, __file__, 1, message, args, exc_info))

    def test_known_environment_secrets_redacted(self):
        secret, password = secrets.token_urlsafe(64), secrets.token_urlsafe(24)
        with override_settings(SECRET_KEY=secret), patch.dict(os.environ, {'DEMO_PASSWORD': password}):
            output = self.format_message('Values: %s %s', (secret, password))
        self.assertNotIn(secret, output)
        self.assertNotIn(password, output)
        self.assertIn('[REDACTED]', output)

    def test_sensitive_fields_authorization_and_query_redacted(self):
        secret = secrets.token_urlsafe(24)
        for message in (f'password={secret}', f'{{"token": "{secret}"}}', f'Authorization: Bearer {secret}',
                        f'GET /login/?arbitrary_name={secret} HTTP/1.1', f'https://test.example.org/?arbitrary={secret}'):
            self.assertNotIn(secret, self.format_message(message))

    def test_traceback_redacts_secret_and_preserves_error_type(self):
        secret = secrets.token_urlsafe(64)
        with override_settings(SECRET_KEY=secret):
            try:
                raise RuntimeError(secret)
            except RuntimeError:
                text = self.format_message('Application failure', exc_info=sys.exc_info())
        self.assertIn('RuntimeError', text)
        self.assertNotIn(secret, text)

    def test_all_requested_loggers_use_console_without_email(self):
        for name in ('django', 'django.security', 'rkeg', 'incidents'):
            config = settings.LOGGING['loggers'][name]
            self.assertEqual(config['handlers'], ['console'])
            self.assertFalse(config['propagate'])
        self.assertEqual(settings.LOGGING['handlers']['console']['class'], 'logging.StreamHandler')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SessionConfigurationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = secrets.token_urlsafe(24)
        cls.user = get_user_model().objects.create_user('configuration-test', password=cls.password)
        cls.organization = Organization.objects.create(name='Konfigurationstest')
        Membership.objects.create(user=cls.user, organization=cls.organization, role='VIEWER')

    def setUp(self):
        self.client = Client(HTTP_HOST='localhost')

    def login(self, client=None, secure=False):
        client = client or self.client
        response = client.post('/login/', {'username': self.user.username, 'password': self.password}, secure=secure)
        self.assertEqual(response.status_code, 302)
        return response

    def test_normal_http_login_still_works(self):
        config = load_environment({})
        with override_settings(**config):
            response = self.login()
            self.assertFalse(response.cookies[settings.SESSION_COOKIE_NAME]['secure'])
            self.assertEqual(self.client.get('/dashboard/').status_code, 200)

    def test_login_session_survives_settings_reload_with_same_key(self):
        env = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(64)}
        with override_settings(**load_environment(env)):
            self.login()
            cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        restarted = Client(HTTP_HOST='localhost')
        restarted.cookies[settings.SESSION_COOKIE_NAME] = cookie
        with override_settings(**load_environment(env)):
            response = restarted.get('/dashboard/')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.wsgi_request.user.pk, self.user.pk)

    def test_changed_key_does_not_bypass_session_signature(self):
        with override_settings(SECRET_KEY=secrets.token_urlsafe(64), SECRET_KEY_FALLBACKS=[]):
            self.login()
        with override_settings(SECRET_KEY=secrets.token_urlsafe(64), SECRET_KEY_FALLBACKS=[]):
            with self.assertLogs('django.security.SuspiciousSession', level='WARNING'):
                response = self.client.get('/dashboard/')
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login/', response.url)

    def test_https_sets_cookies_redirect_and_hsts(self):
        config = load_environment({'DJANGO_SECURE_SSL': 'true', 'DJANGO_SECURE_HSTS_SECONDS': '300'})
        with override_settings(**config):
            self.assertEqual(self.client.get('/login/').status_code, 301)
            page = self.client.get('/login/', secure=True)
            self.assertTrue(page.cookies['csrftoken']['secure'])
            self.assertIn('max-age=300', page['Strict-Transport-Security'])
            response = self.login(secure=True)
            self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]['secure'])
            self.assertEqual(self.client.get('/dashboard/', secure=True).status_code, 200)

    def test_demo_marker_on_pages_and_print_but_not_real_organization(self):
        self.login()
        self.assertNotContains(self.client.get('/dashboard/'), 'class="demo-banner"')
        self.organization.legal_name = 'DEMO / TESTDATEN [seed_demo_data:v1] Konfigurationstest'
        self.organization.save()
        for path in ('/dashboard/', '/reports/management/print/'):
            self.assertContains(self.client.get(path), 'class="demo-banner"')
        self.assertContains(self.client.get('/dashboard/'), 'Abmelden')
