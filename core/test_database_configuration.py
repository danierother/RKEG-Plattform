"""Database settings tests never initialize a PostgreSQL backend or connection."""
import io
import logging
import os
import secrets
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.environment import load_database
from config.logging import RedactingFormatter


class DatabaseConfigurationTests(SimpleTestCase):
    def postgres(self, **overrides):
        return {'DJANGO_DB_ENGINE': 'postgresql', 'POSTGRES_DB': 'rkeg',
                'POSTGRES_USER': 'rkeg_app', 'POSTGRES_PASSWORD': secrets.token_urlsafe(24),
                'POSTGRES_HOST': '127.0.0.1', **overrides}

    def test_default_is_unchanged_sqlite(self):
        self.assertEqual(load_database({}, settings.BASE_DIR), {'default': {
            'ENGINE': 'django.db.backends.sqlite3', 'NAME': settings.BASE_DIR / 'db.sqlite3'}})

    def test_explicit_sqlite(self):
        self.assertEqual(load_database({'DJANGO_DB_ENGINE': 'sqlite'}, settings.BASE_DIR),
                         load_database({}, settings.BASE_DIR))

    def test_sqlite_ignores_postgres_variables(self):
        self.assertEqual(load_database({'POSTGRES_PORT': 'invalid', 'POSTGRES_PASSWORD': ''}, settings.BASE_DIR),
                         load_database({}, settings.BASE_DIR))

    def test_postgres_settings_without_connection(self):
        env = self.postgres(POSTGRES_PORT='5433')
        with patch('socket.socket', side_effect=AssertionError('No network allowed')):
            database = load_database(env, settings.BASE_DIR)
        self.assertEqual(database, {'default': {
            'ENGINE': 'django.db.backends.postgresql', 'NAME': 'rkeg', 'USER': 'rkeg_app',
            'PASSWORD': env['POSTGRES_PASSWORD'], 'HOST': '127.0.0.1', 'PORT': '5433'}})

    def test_default_postgres_port(self):
        self.assertEqual(load_database(self.postgres(), settings.BASE_DIR)['default']['PORT'], '5432')

    def test_each_required_postgres_variable(self):
        for name in ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_HOST'):
            for value in (None, '', '   '):
                env = self.postgres()
                if value is None:
                    env.pop(name)
                else:
                    env[name] = value
                with self.subTest(name=name, value=value), self.assertRaisesMessage(ImproperlyConfigured, name):
                    load_database(env, settings.BASE_DIR)

    def test_unknown_engine_rejected(self):
        for engine in ('mysql', 'postgres', '', '   '):
            with self.assertRaisesMessage(ImproperlyConfigured, 'DJANGO_DB_ENGINE'):
                load_database({'DJANGO_DB_ENGINE': engine}, settings.BASE_DIR)

    def test_invalid_ports_rejected_without_value_disclosure(self):
        for port in ('', 'invalid', '0', '-1', '65536', '54.32'):
            with self.assertRaisesMessage(ImproperlyConfigured, 'POSTGRES_PORT'):
                load_database(self.postgres(POSTGRES_PORT=port), settings.BASE_DIR)

    def test_normalization_preserves_password(self):
        password = ' ' + secrets.token_urlsafe(24) + ' '
        result = load_database(self.postgres(DJANGO_DB_ENGINE=' PostgreSQL ', POSTGRES_DB=' rkeg ',
                                            POSTGRES_PASSWORD=password), settings.BASE_DIR)['default']
        self.assertEqual(result['NAME'], 'rkeg')
        self.assertEqual(result['PASSWORD'], password)

    def test_configuration_errors_do_not_log_password(self):
        env = self.postgres(POSTGRES_PORT='invalid')
        with self.assertNoLogs(level='DEBUG'):
            with self.assertRaises(ImproperlyConfigured) as raised:
                load_database(env, settings.BASE_DIR)
        self.assertNotIn(env['POSTGRES_PASSWORD'], str(raised.exception))

    def test_database_password_redacted_by_console_handler(self):
        password = secrets.token_urlsafe(24)
        for source in ('environment', 'settings'):
            output = io.StringIO()
            handler = logging.StreamHandler(output)
            handler.setFormatter(RedactingFormatter('%(message)s'))
            logger = logging.Logger('rkeg.database-test')
            logger.addHandler(handler)
            config = SimpleNamespace(SECRET_KEY=settings.SECRET_KEY, SECRET_KEY_FALLBACKS=[],
                                     DATABASES={'default': {'PASSWORD': password if source == 'settings' else ''}})
            with patch('config.logging.settings', config), patch.dict(os.environ, {'POSTGRES_PASSWORD': password if source == 'environment' else ''}):
                logger.error('Database credential: %s', password)
                try:
                    raise RuntimeError(password)
                except RuntimeError:
                    logger.exception('Database failure')
            self.assertNotIn(password, output.getvalue())
            self.assertIn('[REDACTED]', output.getvalue())
            self.assertIn('RuntimeError', output.getvalue())

    def test_env_example_has_placeholder_and_local_default(self):
        lines = (settings.BASE_DIR / '.env.example').read_text().splitlines()
        values = dict(line.split('=', 1) for line in lines if line and not line.startswith('#'))
        self.assertEqual(values['DJANGO_DB_ENGINE'], 'sqlite')
        self.assertEqual(values['POSTGRES_PASSWORD'], 'replace-me')
        self.assertEqual(values['POSTGRES_PORT'], '5432')

    def test_actual_settings_import_with_postgres_without_driver_or_network(self):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('DJANGO_', 'POSTGRES_'))}
        env.update(self.postgres(), DJANGO_DEBUG='true')
        code = '''
import os
import sys
from unittest.mock import patch
with patch('socket.socket', side_effect=AssertionError('No network allowed')):
    from config import settings
    database = settings.DATABASES['default']
    assert database['ENGINE'] == 'django.db.backends.postgresql'
    assert database['NAME'] == 'rkeg'
    assert database['PASSWORD'] == os.environ['POSTGRES_PASSWORD']
    assert database['PORT'] == '5432'
    assert 'psycopg' not in sys.modules
    assert 'psycopg2' not in sys.modules
print('PostgreSQL settings verified without connection')
'''
        result = subprocess.run([sys.executable, '-c', code], env=env, cwd=settings.BASE_DIR,
                                capture_output=True, text=True, timeout=20, check=True)
        self.assertIn('verified without connection', result.stdout)
        self.assertNotIn(env['POSTGRES_PASSWORD'], result.stdout + result.stderr)
