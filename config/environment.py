"""Environment-only configuration; deliberately does not load .env files."""
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key


def boolean(env, name, default=False):
    value = env.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {'true', '1', 'yes', 'on'}:
        return True
    if normalized in {'false', '0', 'no', 'off'}:
        return False
    raise ImproperlyConfigured(f'{name}: true/false oder 1/0 angeben.')


def comma_list(env, name, default=''):
    return list(dict.fromkeys(part.strip() for part in env.get(name, default).split(',') if part.strip()))


def load_environment(env):
    debug = boolean(env, 'DJANGO_DEBUG', default=True)
    secret = env.get('DJANGO_SECRET_KEY', '')
    configured = bool(secret.strip())
    if not debug and not configured:
        raise ImproperlyConfigured('DJANGO_SECRET_KEY muss bei DJANGO_DEBUG=false dauerhaft in der Umgebung gesetzt sein.')
    if configured and (secret.strip().lower() == 'replace-me' or len(secret) < 50 or len(set(secret)) < 5):
        raise ImproperlyConfigured('DJANGO_SECRET_KEY: einen eigenen starken Schluessel mit mindestens 50 Zeichen verwenden, keinen Platzhalter.')
    hosts = comma_list(env, 'DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost' if debug else '')
    if not debug and (not hosts or any('*' in host for host in hosts)):
        raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS: bei DJANGO_DEBUG=false konkrete Hosts ohne * angeben.')
    if any('://' in host or '/' in host or any(char.isspace() for char in host) for host in hosts):
        raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS enthaelt keine URLs, Pfade oder Leerzeichen innerhalb eines Hosts.')
    secure = boolean(env, 'DJANGO_SECURE_SSL')
    origins = comma_list(env, 'DJANGO_CSRF_TRUSTED_ORIGINS')
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            valid = (parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username
                     and not parsed.password and not parsed.path and not parsed.query and not parsed.fragment
                     and not any(char.isspace() for char in origin))
            parsed.port  # Validate the optional port without guessing a default.
        except ValueError:
            valid = False
        if not valid or (secure and parsed.scheme != 'https'):
            raise ImproperlyConfigured('DJANGO_CSRF_TRUSTED_ORIGINS: Origins mit Schema und ohne Pfad angeben; bei DJANGO_SECURE_SSL=true nur HTTPS.')
    try:
        hsts = int(env.get('DJANGO_SECURE_HSTS_SECONDS', '0'))
    except ValueError as exc:
        raise ImproperlyConfigured('DJANGO_SECURE_HSTS_SECONDS muss eine nichtnegative ganze Zahl sein.') from exc
    include_subdomains = boolean(env, 'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS')
    preload = boolean(env, 'DJANGO_SECURE_HSTS_PRELOAD')
    if hsts < 0 or (not secure and (hsts or include_subdomains or preload)):
        raise ImproperlyConfigured('HSTS benoetigt DJANGO_SECURE_SSL=true und eine nichtnegative Laufzeit.')
    if include_subdomains and not hsts:
        raise ImproperlyConfigured('HSTS fuer Subdomains benoetigt eine positive Laufzeit.')
    if preload and (not include_subdomains or hsts < 31536000):
        raise ImproperlyConfigured('HSTS-Preload benoetigt Subdomains und mindestens 31536000 Sekunden; erst nach Domain-Pruefung aktivieren.')
    return {
        'DEBUG': debug,
        'SECRET_KEY': secret if configured else get_random_secret_key(),
        'SECRET_KEY_FROM_ENV': configured,
        'ALLOWED_HOSTS': hosts,
        'CSRF_TRUSTED_ORIGINS': origins,
        'SECURE_SSL_REDIRECT': secure,
        'SESSION_COOKIE_SECURE': secure,
        'CSRF_COOKIE_SECURE': secure,
        'SECURE_HSTS_SECONDS': hsts,
        'SECURE_HSTS_INCLUDE_SUBDOMAINS': include_subdomains,
        'SECURE_HSTS_PRELOAD': preload,
    }
