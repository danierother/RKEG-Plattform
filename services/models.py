from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.duration import duration_string


class Criticality(models.IntegerChoices):
    LOW = 1, 'Gering'
    MEDIUM = 2, 'Mittel'
    HIGH = 3, 'Hoch'
    VERY_HIGH = 4, 'Sehr hoch'
    CRITICAL = 5, 'Kritisch'


class OrganizationRecord(models.Model):
    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(organization_id=self.organization_id).exists():
            raise ValidationError({'organization': 'Die Organisation eines bestehenden Datensatzes kann nicht geaendert werden.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Location(OrganizationRecord):
    class LocationType(models.TextChoices):
        HEADQUARTERS = 'HEADQUARTERS', 'Hauptstandort'
        OPERATING_SITE = 'OPERATING_SITE', 'Betriebsstandort'
        DATA_CENTER = 'DATA_CENTER', 'Rechenzentrum'
        WAREHOUSE = 'WAREHOUSE', 'Lager'
        OFFICE = 'OFFICE', 'B\u00fcro'
        OTHER = 'OTHER', 'Sonstige'

    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='locations')
    name = models.CharField('Name', max_length=255)
    description = models.TextField('Beschreibung', blank=True)
    address_line = models.CharField('Adresse', max_length=255, blank=True)
    postal_code = models.CharField('Postleitzahl', max_length=32, blank=True)
    city = models.CharField('Stadt', max_length=255, blank=True)
    country = models.CharField('Land', max_length=100, blank=True)
    location_type = models.CharField('Typ', max_length=24, choices=LocationType.choices, default=LocationType.OTHER)
    is_active = models.BooleanField('Aktiv', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CriticalService(OrganizationRecord):
    Criticality = Criticality

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Aktiv'
        INACTIVE = 'INACTIVE', 'Inaktiv'
        UNDER_REVIEW = 'UNDER_REVIEW', 'In Pr\u00fcfung'

    class RecoveryPriority(models.IntegerChoices):
        VERY_HIGH = 1, 'Sehr hoch'
        HIGH = 2, 'Hoch'
        MEDIUM = 3, 'Mittel'
        LOW = 4, 'Niedrig'
        VERY_LOW = 5, 'Sehr niedrig'

    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='critical_services')
    name = models.CharField('Name', max_length=255)
    description = models.TextField('Beschreibung')
    service_owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='owned_services', verbose_name='Service Owner')
    status = models.CharField('Status', max_length=24, choices=Status.choices, default=Status.ACTIVE)
    criticality = models.PositiveSmallIntegerField('Kritikalit\u00e4t', choices=Criticality.choices, default=Criticality.MEDIUM,
                                                   validators=[MinValueValidator(1), MaxValueValidator(5)])
    recovery_priority = models.PositiveSmallIntegerField('Recovery Priority', choices=RecoveryPriority.choices,
        default=RecoveryPriority.MEDIUM, validators=[MinValueValidator(1), MaxValueValidator(5)])
    maximum_tolerable_downtime = models.DurationField('Maximum Tolerable Downtime (MTD)', null=True, blank=True,
        validators=[MinValueValidator(timedelta(0))])
    recovery_time_objective = models.DurationField('Recovery Time Objective (RTO)', null=True, blank=True,
        validators=[MinValueValidator(timedelta(0))])
    locations = models.ManyToManyField(Location, blank=True, related_name='critical_services', verbose_name='Standorte')
    notes = models.TextField('Notizen', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(criticality__gte=1, criticality__lte=5), name='service_criticality_1_to_5'),
            models.CheckConstraint(condition=models.Q(recovery_priority__gte=1, recovery_priority__lte=5), name='service_priority_1_to_5'),
            models.CheckConstraint(condition=models.Q(maximum_tolerable_downtime__gte=timedelta(0)) | models.Q(maximum_tolerable_downtime__isnull=True), name='service_mtd_nonnegative'),
            models.CheckConstraint(condition=models.Q(recovery_time_objective__gte=timedelta(0)) | models.Q(recovery_time_objective__isnull=True), name='service_rto_nonnegative'),
            models.CheckConstraint(condition=models.Q(recovery_time_objective__isnull=True) | models.Q(maximum_tolerable_downtime__isnull=True) | models.Q(recovery_time_objective__lte=models.F('maximum_tolerable_downtime')), name='service_rto_within_mtd'),
        ]

    def clean(self):
        super().clean()
        if self.service_owner_id and not self.service_owner.memberships.filter(
            organization_id=self.organization_id, is_active=True, user__is_active=True,
        ).exists():
            raise ValidationError({'service_owner': 'Bitte waehlen Sie ein aktives Mitglied dieser Organisation.'})
        if self.recovery_time_objective is not None and self.maximum_tolerable_downtime is not None:
            if self.recovery_time_objective > self.maximum_tolerable_downtime:
                raise ValidationError({'recovery_time_objective': 'Die Wiederherstellungszeit (RTO) darf die maximal tolerierbare Ausfallzeit (MTD) nicht ueberschreiten.'})

    @property
    def mtd_display(self):
        return duration_string(self.maximum_tolerable_downtime) if self.maximum_tolerable_downtime is not None else 'Nicht festgelegt'

    @property
    def rto_display(self):
        return duration_string(self.recovery_time_objective) if self.recovery_time_objective is not None else 'Nicht festgelegt'


class ServiceDependency(OrganizationRecord):
    Criticality = Criticality

    class DependencyType(models.TextChoices):
        PERSONNEL = 'PERSONNEL', 'Personal'
        IT = 'IT', 'IT / Informationssystem'
        ENERGY = 'ENERGY', 'Energie'
        TELECOMMUNICATION = 'TELECOMMUNICATION', 'Telekommunikation'
        SUPPLIER = 'SUPPLIER', 'Lieferant'
        FACILITY = 'FACILITY', 'Geb\u00e4ude / Standort'
        TRANSPORT = 'TRANSPORT', 'Transport / Logistik'
        WATER = 'WATER', 'Wasser'
        EXTERNAL_SERVICE = 'EXTERNAL_SERVICE', 'Externe Dienstleistung'
        OTHER = 'OTHER', 'Sonstige'

    class InternalExternal(models.TextChoices):
        INTERNAL = 'INTERNAL', 'Intern'
        EXTERNAL = 'EXTERNAL', 'Extern'

    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='service_dependencies')
    service = models.ForeignKey(CriticalService, on_delete=models.CASCADE, related_name='dependencies')
    name = models.CharField('Name', max_length=255)
    description = models.TextField('Beschreibung', blank=True)
    dependency_type = models.CharField('Typ', max_length=24, choices=DependencyType.choices, default=DependencyType.OTHER)
    criticality = models.PositiveSmallIntegerField('Kritikalit\u00e4t', choices=Criticality.choices, default=Criticality.MEDIUM,
                                                   validators=[MinValueValidator(1), MaxValueValidator(5)])
    supplier_name = models.CharField('Lieferant', max_length=255, blank=True)
    internal_external = models.CharField('Intern / extern', max_length=16, choices=InternalExternal.choices,
                                         default=InternalExternal.INTERNAL)
    single_point_of_failure = models.BooleanField('Single Point of Failure', default=False)
    contingency_available = models.BooleanField('Ausweichl\u00f6sung vorhanden', default=False)
    notes = models.TextField('Notizen', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(criticality__gte=1, criticality__lte=5), name='dependency_criticality_1_to_5')]

    def clean(self):
        if self.service_id:
            organization_id = self.service.organization_id
            if self.organization_id and self.organization_id != organization_id:
                raise ValidationError({'organization': 'Abhaengigkeit und Dienstleistung muessen derselben Organisation angehoeren.'})
            self.organization_id = organization_id
        super().clean()

    def save(self, *args, **kwargs):
        if self.service_id and not self.organization_id:
            self.organization_id = self.service.organization_id
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'organization'}
        return super().save(*args, **kwargs)
