"""Console redaction is defence in depth, never permission to log credentials."""
import logging
import os
import re

from django.conf import settings


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        text = super().format(record)
        secrets = [settings.SECRET_KEY, os.environ.get('DEMO_PASSWORD', '')]
        secrets.extend(settings.SECRET_KEY_FALLBACKS)
        for secret in secrets:
            if secret:
                text = text.replace(secret, '[REDACTED]')
        # Request lines can carry credentials in arbitrary query parameters.
        text = re.sub(r'(https?://[^\s?]+|/[^\s?]*)\?[^\s"\']+', r'\1?[REDACTED]', text)
        text = re.sub(r'(?i)(authorization\s*[:=]\s*)(?:bearer|basic)\s+[^\s,;]+', r'\1[REDACTED]', text)
        text = re.sub(
            r'''(?ix)(["']?(?:password|passwd|secret_key|django_secret_key|token|api_key|cookie|sessionid|csrftoken)["']?\s*[:=]\s*)
            (?:"[^"]*"|'[^']*'|[^\s,;]+)''',
            r'\1[REDACTED]', text,
        )
        return text
