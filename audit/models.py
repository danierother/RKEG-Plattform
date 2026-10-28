from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        CREATE = 'CREATE', 'Angelegt'
        UPDATE = 'UPDATE', 'Geaendert'
        DELETE = 'DELETE', 'Geloescht'
        STATUS_CHANGE = 'STATUS_CHANGE', 'Status geaendert'
        ASSESSMENT = 'ASSESSMENT', 'Bewertung'
        MANUAL_OVERRIDE = 'MANUAL_OVERRIDE', 'Manuelle Uebersteuerung'
        REPORT_CREATED = 'REPORT_CREATED', 'Meldungsentwurf angelegt'
        REPORT_MARKED_SUBMITTED = 'REPORT_MARKED_SUBMITTED', 'Externe Uebermittlung dokumentiert'
        OTHER = 'OTHER', 'Sonstige'

    class Source(models.TextChoices):
        WEB = 'WEB', 'Web'
        ADMIN = 'ADMIN', 'Admin'
        SYSTEM = 'SYSTEM', 'System'
        MIGRATION = 'MIGRATION', 'Migration'
        OTHER = 'OTHER', 'Sonstige'

    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='audit_events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    timestamp = models.DateTimeField(default=timezone.now, editable=False)
    action = models.CharField(max_length=32, choices=Action.choices)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    object_repr = models.CharField(max_length=500)
    field_name = models.CharField(max_length=100, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    change_summary = models.TextField(blank=True)
    source = models.CharField(max_length=16, choices=Source.choices)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('-timestamp', '-pk')
        indexes = [models.Index(fields=['organization', '-timestamp'], name='audit_org_time'),
                   models.Index(fields=['organization', 'object_type', 'object_id'], name='audit_org_object')]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Audit-Eintraege sind unveraenderlich.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Audit-Eintraege duerfen nicht geloescht werden.')

    def __str__(self):
        return f'{self.object_repr}: {self.get_action_display()}'
