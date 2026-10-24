from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def validate_responsible_user(instance):
    if instance.responsible_user_id and not instance.responsible_user.memberships.filter(
        organization_id=instance.organization_id, is_active=True, user__is_active=True,
    ).exists():
        raise ValidationError({'responsible_user': 'Bitte waehlen Sie ein aktives Mitglied der Organisation.'})


class Incident(models.Model):
    class Status(models.TextChoices):
        NEW = 'NEW', 'Neu'
        ACTIVE = 'ACTIVE', 'In Bearbeitung'
        CONTAINED = 'CONTAINED', 'Einged\u00e4mmt'
        RESOLVED = 'RESOLVED', 'Behoben'
        CLOSED = 'CLOSED', 'Abgeschlossen'

    class Severity(models.IntegerChoices):
        LOW = 1, 'Gering'
        MODERATE = 2, 'Moderat'
        SIGNIFICANT = 3, 'Erheblich'
        SEVERE = 4, 'Schwer'
        CRITICAL = 5, 'Kritisch'

    class IncidentType(models.TextChoices):
        CYBER = 'CYBER', 'Cybervorfall'
        PHYSICAL = 'PHYSICAL', 'Physische Sicherheit'
        TECHNICAL = 'TECHNICAL', 'Technische St\u00f6rung'
        SUPPLY = 'SUPPLY', 'Versorgung / Lieferkette'
        PERSONNEL = 'PERSONNEL', 'Personal'
        NATURAL_HAZARD = 'NATURAL_HAZARD', 'Naturgefahr'
        OTHER = 'OTHER', 'Sonstiges'

    class ReportingStatus(models.TextChoices):
        NOT_ASSESSED = 'NOT_ASSESSED', 'Noch nicht gepr\u00fcft'
        UNDER_REVIEW = 'UNDER_REVIEW', 'In Pr\u00fcfung'
        REPORTABLE = 'REPORTABLE', 'Meldepflichtig'
        NOT_REPORTABLE = 'NOT_REPORTABLE', 'Nicht meldepflichtig'
        REPORTED = 'REPORTED', 'Gemeldet'

    OPEN_STATUSES = (Status.NEW, Status.ACTIVE, Status.CONTAINED)

    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT,
                                     related_name='incidents')
    title = models.CharField('Titel', max_length=255)
    description = models.TextField('Beschreibung')
    occurred_at = models.DateTimeField('Ereigniszeit')
    detected_at = models.DateTimeField('Erkennungszeit')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name='created_incidents')
    responsible_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='responsible_incidents', null=True, blank=True, verbose_name='Verantwortlich')
    status = models.CharField('Status', max_length=16, choices=Status.choices, default=Status.NEW)
    severity = models.PositiveSmallIntegerField('Schweregrad', choices=Severity.choices,
        default=Severity.MODERATE, validators=[MinValueValidator(1), MaxValueValidator(5)])
    incident_type = models.CharField('Vorfallart', max_length=24, choices=IncidentType.choices,
                                     default=IncidentType.OTHER)
    affected_service = models.CharField('Betroffener Dienst', max_length=255, blank=True)
    affected_location = models.CharField('Betroffener Standort', max_length=255, blank=True)
    impact_description = models.TextField('Auswirkungen')
    immediate_actions = models.TextField('Bereits eingeleitete Sofortmassnahmen', blank=True)
    suspected_reportable = models.BooleanField('Meldepflicht vermutet', default=False)
    reporting_status = models.CharField('Meldepr\u00fcfung', max_length=24,
        choices=ReportingStatus.choices, default=ReportingStatus.NOT_ASSESSED)
    risks = models.ManyToManyField('risks.Risk', blank=True, related_name='incidents',
                                  verbose_name='Verkn\u00fcpfte Risiken')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(severity__gte=1, severity__lte=5),
                                   name='incident_severity_1_to_5'),
            models.CheckConstraint(condition=models.Q(detected_at__gte=models.F('occurred_at')),
                                   name='incident_detection_after_occurrence'),
        ]

    def clean(self):
        super().clean()
        if self.occurred_at and self.detected_at and self.detected_at < self.occurred_at:
            raise ValidationError({'detected_at': 'Die Erkennungszeit darf nicht vor der Ereigniszeit liegen.'})
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(organization_id=self.organization_id).exists():
            raise ValidationError({'organization': 'Die Organisation eines Vorfalls kann nicht geaendert werden.'})
        validate_responsible_user(self)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class IncidentChildMixin(models.Model):
    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.incident_id:
            organization_id = self.incident.organization_id
            if self.organization_id and self.organization_id != organization_id:
                raise ValidationError({'organization': 'Vorfall und Eintrag muessen derselben Organisation angehoeren.'})
            self.organization_id = organization_id

    def save(self, *args, **kwargs):
        if self.incident_id and not self.organization_id:
            self.organization_id = self.incident.organization_id
        self.full_clean()
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'organization'}
        return super().save(*args, **kwargs)


class IncidentEvent(IncidentChildMixin):
    class EventType(models.TextChoices):
        DETECTION = 'DETECTION', 'Erkennung'
        ASSESSMENT = 'ASSESSMENT', 'Bewertung'
        ACTION = 'ACTION', 'Massnahme'
        ESCALATION = 'ESCALATION', 'Eskalation'
        COMMUNICATION = 'COMMUNICATION', 'Kommunikation'
        STATUS_CHANGE = 'STATUS_CHANGE', 'Status\u00e4nderung'
        OTHER = 'OTHER', 'Sonstiges'

    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT,
                                     related_name='incident_events')
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='events')
    event_time = models.DateTimeField('Zeitpunkt')
    event_type = models.CharField('Eintragsart', max_length=24, choices=EventType.choices,
                                  default=EventType.OTHER)
    description = models.TextField('Beschreibung')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name='created_incident_events')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.incident} - {self.get_event_type_display()}'


class IncidentAction(IncidentChildMixin):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Offen'
        IN_PROGRESS = 'IN_PROGRESS', 'In Bearbeitung'
        DONE = 'DONE', 'Erledigt'
        CANCELLED = 'CANCELLED', 'Abgebrochen'

    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT,
                                     related_name='incident_actions')
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='actions')
    title = models.CharField('Titel', max_length=255)
    description = models.TextField('Beschreibung', blank=True)
    status = models.CharField('Status', max_length=24, choices=Status.choices, default=Status.OPEN)
    responsible_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='incident_actions', null=True, blank=True, verbose_name='Verantwortlich')
    due_date = models.DateField('F\u00e4llig am', null=True, blank=True)
    completed_at = models.DateTimeField('Erledigt am', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        validate_responsible_user(self)
        if self.completed_at and self.status != self.Status.DONE:
            raise ValidationError({'completed_at': 'Ein Abschlusszeitpunkt ist nur bei erledigten Massnahmen zulaessig.'})

    def __str__(self):
        return self.title
