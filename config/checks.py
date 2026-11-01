from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def production_configuration(app_configs, **kwargs):
    messages = []
    if not settings.SECRET_KEY_FROM_ENV:
        issue = Warning if settings.DEBUG else Error
        messages.append(issue(
            'Kein dauerhafter DJANGO_SECRET_KEY: der Entwicklungsschluessel wechselt beim Prozessstart.',
            hint='Fuer stabile Sessions einen eigenen Schluessel dauerhaft ueber die Umgebung bereitstellen.',
            id='rkeg.W001' if settings.DEBUG else 'rkeg.E001',
        ))
    if not settings.DEBUG and (not settings.ALLOWED_HOSTS or any('*' in host for host in settings.ALLOWED_HOSTS)):
        messages.append(Error('Produktionshosts muessen explizit und ohne * konfiguriert sein.', id='rkeg.E002'))
    return messages
