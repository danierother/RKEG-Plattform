from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def validate_responsible_user(instance):
    if instance.responsible_user_id and not instance.responsible_user.memberships.filter(
        organization_id=instance.organization_id, is_active=True, user__is_active=True,
    ).exists():
        raise ValidationError({'responsible_user': 'Bitte waehlen Sie ein aktives Mitglied der Organisation.'})


class RKEGFacts(models.Model):
    class DisruptionStatus(models.TextChoices):
        OUTAGE = 'OUTAGE', 'Ausfall'
        RESTRICTED_AVAILABILITY = 'RESTRICTED_AVAILABILITY', 'Eingeschraenkte Verfuegbarkeit'

    class CrossBorder(models.TextChoices):
        UNKNOWN = 'UNKNOWN', 'Unbekannt'
        NO = 'NO', 'Nein'
        YES = 'YES', 'Ja'

    disruption_started_at = models.DateTimeField('Beginn der Stoerung', null=True, blank=True)
    disruption_ended_at = models.DateTimeField('Ende der Stoerung', null=True, blank=True)
    disruption_status = models.CharField('Stoerungsart', max_length=32, choices=DisruptionStatus.choices, blank=True)
    unplanned_confirmed = models.BooleanField('Ungeplante Stoerung bestaetigt', null=True, blank=True)
    significant_impairment_confirmed = models.BooleanField('Erhebliche Beeintraechtigung nach RKEV § 2 Z 2 bestaetigt', null=True, blank=True)
    affected_users = models.PositiveBigIntegerField('Betroffene Nutzer', null=True, blank=True)
    affected_metering_points = models.PositiveBigIntegerField('Betroffene Zaehlpunkte', null=True, blank=True)
    affected_geographic_area = models.TextField('Betroffenes geografisches Gebiet', blank=True)
    cross_border_impact = models.CharField('Grenzueberschreitende Auswirkungen', max_length=8,
                                          choices=CrossBorder.choices, default=CrossBorder.UNKNOWN, blank=True)
    special_threshold_condition_met = models.BooleanField('Kein Handelsergebnis fuer physische Stromprodukte', null=True, blank=True)
    special_threshold_description = models.TextField('Dokumentation des Sonderkriteriums', blank=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.disruption_ended_at and not self.disruption_started_at:
            raise ValidationError({'disruption_started_at': 'Bitte auch den Beginn dokumentieren.'})
        if self.disruption_started_at and self.disruption_ended_at and self.disruption_ended_at < self.disruption_started_at:
            raise ValidationError({'disruption_ended_at': 'Das Ende darf nicht vor dem Beginn liegen.'})
        for field in ('disruption_started_at', 'disruption_ended_at'):
            value = getattr(self, field)
            if value and value > timezone.now():
                raise ValidationError({field: 'Tatsaechliche Zeitpunkte duerfen nicht in der Zukunft liegen.'})


class Incident(RKEGFacts):
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

    rkeg_awareness_at = models.DateTimeField('Kenntnis vom meldepflichtigen Sicherheitsvorfall', null=True, blank=True)

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
    affected_services = models.ManyToManyField('services.CriticalService', blank=True, related_name='incidents',
                                               verbose_name='Betroffene Dienstleistungen')
    affected_locations = models.ManyToManyField('services.Location', blank=True, related_name='incidents',
                                                verbose_name='Betroffene Standorte')
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
        if self.rkeg_awareness_at and self.rkeg_awareness_at > timezone.now():
            raise ValidationError({'rkeg_awareness_at': 'Die Kenntniszeit darf nicht in der Zukunft liegen.'})
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


class IncidentServiceImpact(IncidentChildMixin, RKEGFacts):
    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='service_impacts')
    service = models.ForeignKey('services.CriticalService', on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('incident', 'service'), name='unique_incident_service_impact')]

    def clean(self):
        super().clean()
        if self.service_id and self.incident_id:
            if self.service.organization_id != self.organization_id or not self.incident.affected_services.filter(pk=self.service_id).exists():
                raise ValidationError({'service': 'Nur ein zugeordneter Dienst derselben Organisation ist erlaubt.'})


class IncidentReport(IncidentChildMixin):
    class ReportType(models.TextChoices):
        INITIAL = 'INITIAL', 'Erstmeldung'
        FOLLOW_UP = 'FOLLOW_UP', 'Folgemeldung'
        ADDITIONAL_INFORMATION = 'ADDITIONAL_INFORMATION', 'Ergaenzende Informationen'
        END_NOTIFICATION = 'END_NOTIFICATION', 'Beendigungsmeldung'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Interner Entwurf'
        MARKED_AS_SUBMITTED = 'MARKED_AS_SUBMITTED', 'Extern uebermittelt (dokumentiert)'

    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT)
    incident = models.ForeignKey(Incident, on_delete=models.PROTECT, related_name='reports')
    report_type = models.CharField('Meldungsart', max_length=32, choices=ReportType.choices)
    status = models.CharField('Status', max_length=24, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField('Tatsaechliche externe Uebermittlung am', null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    incident_type_description = models.TextField('Art des Sicherheitsvorfalls', blank=True)
    suspected_cause = models.TextField('Vermutete Ursache', blank=True)
    confirmed_cause = models.TextField('Bestaetigte Ursache', blank=True)
    consequences = models.TextField('Folgen', blank=True)
    measures_taken = models.TextField('Ergriffene Massnahmen', blank=True)
    affected_critical_infrastructure = models.TextField('Betroffene kritische Infrastruktur', blank=True)
    cross_border_information = models.TextField('Grenzueberschreitende Auswirkungen', blank=True)
    additional_information = models.TextField('Ergaenzende Informationen', blank=True)

    def clean(self):
        super().clean()
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.status == self.Status.MARKED_AS_SUBMITTED:
                raise ValidationError('Dokumentierte Uebermittlungen sind unveraenderlich. Ergaenzung anlegen.')
            if (old.incident_id, old.organization_id, old.created_by_id) != (self.incident_id, self.organization_id, self.created_by_id):
                raise ValidationError('Vorfall, Organisation und Ersteller sind unveraenderlich.')
        if self.status == self.Status.MARKED_AS_SUBMITTED and not self.submitted_at:
            raise ValidationError({'submitted_at': 'Bitte den tatsaechlichen Uebermittlungszeitpunkt dokumentieren.'})
        if self.submitted_at and (self.status != self.Status.MARKED_AS_SUBMITTED or self.submitted_at > timezone.now()):
            raise ValidationError({'submitted_at': 'Nur bereits erfolgte externe Uebermittlungen sind zulaessig.'})
        if self.report_type == self.ReportType.FOLLOW_UP and self.submitted_at:
            first = self.incident.reports.filter(organization_id=self.organization_id, report_type=self.ReportType.INITIAL,
                status=self.Status.MARKED_AS_SUBMITTED).order_by('submitted_at').first()
            if not first or self.submitted_at < first.submitted_at:
                raise ValidationError({'submitted_at': 'Eine Folgemeldung setzt eine dokumentierte Erstmeldung voraus.'})

    def __str__(self):
        return f'{self.get_report_type_display()} - {self.incident}'


class IncidentRKEGAssessment(IncidentChildMixin):
    class Result(models.TextChoices):
        NOT_ASSESSED = 'NOT_ASSESSED', 'Noch nicht geprueft'
        NOT_APPLICABLE = 'NOT_APPLICABLE', '§ 17 RKEG nicht anwendbar'
        EXEMPT_SECTOR = 'EXEMPT_SECTOR', '§ 17 RKEG nicht anwendbar (Sektorausnahme)'
        INSUFFICIENT_DATA = 'INSUFFICIENT_DATA', 'Daten unvollstaendig - manuelle Pruefung erforderlich'
        BELOW_THRESHOLD = 'BELOW_THRESHOLD', 'Schwelle nicht ueberschritten'
        REPORTABLE = 'REPORTABLE', 'Meldepflichtig'
        MANUAL_REVIEW = 'MANUAL_REVIEW', 'Manuelle Pruefung erforderlich'

    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT)
    incident = models.ForeignKey(Incident, on_delete=models.PROTECT, related_name='rkeg_assessments')
    result = models.CharField(max_length=24, choices=Result.choices)
    assessed_at = models.DateTimeField(default=timezone.now)
    assessed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    legal_reference = models.TextField()
    applied_rule = models.JSONField(default=list, blank=True)
    input_snapshot = models.JSONField(default=dict, blank=True)
    calculated_duration = models.DurationField(null=True, blank=True)
    calculated_user_hours = models.DecimalField(max_digits=40, decimal_places=8, null=True, blank=True)
    calculated_metering_point_hours = models.DecimalField(max_digits=40, decimal_places=8, null=True, blank=True)
    threshold_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    explanation = models.TextField()
    manual_override = models.BooleanField(default=False)
    manual_override_reason = models.TextField('Begruendung', blank=True)
    based_on = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='overrides')
    rule_version = models.CharField(max_length=100)

    def clean(self):
        super().clean()
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Pruefhistorie ist unveraenderlich. Neue Bewertung anlegen.')
        if self.manual_override:
            if not self.manual_override_reason.strip() or not self.based_on_id:
                raise ValidationError('Manuelle Bewertung benoetigt Begruendung und automatische Ausgangsbewertung.')
            if self.based_on.incident_id != self.incident_id or self.based_on.organization_id != self.organization_id or self.based_on.manual_override:
                raise ValidationError('Ungueltige automatische Ausgangsbewertung.')
        elif self.based_on_id:
            raise ValidationError('Nur manuelle Bewertungen beziehen sich auf eine Ausgangsbewertung.')

    def delete(self, *args, **kwargs):
        raise ValidationError('Pruefhistorie darf nicht geloescht werden.')

    def __str__(self):
        return f'{self.incident} - {self.get_result_display()}'
