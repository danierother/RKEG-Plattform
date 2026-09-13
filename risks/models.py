from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .assessment import calculate_score, classify_score


class Risk(models.Model):
    class Likelihood(models.IntegerChoices):
        VERY_UNLIKELY = 1, 'Sehr unwahrscheinlich'
        UNLIKELY = 2, 'Unwahrscheinlich'
        POSSIBLE = 3, 'M\u00f6glich'
        LIKELY = 4, 'Wahrscheinlich'
        VERY_LIKELY = 5, 'Sehr wahrscheinlich'

    class Impact(models.IntegerChoices):
        INSIGNIFICANT = 1, 'Unbedeutend'
        MINOR = 2, 'Gering'
        MODERATE = 3, 'Mittel'
        MAJOR = 4, 'Hoch'
        CRITICAL = 5, 'Kritisch'

    class TreatmentStrategy(models.TextChoices):
        AVOID = 'AVOID', 'Vermeiden'
        REDUCE = 'REDUCE', 'Reduzieren'
        TRANSFER = 'TRANSFER', '\u00dcbertragen'
        ACCEPT = 'ACCEPT', 'Akzeptieren'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        IN_PROGRESS = 'IN_PROGRESS', 'In progress'
        CLOSED = 'CLOSED', 'Closed'

    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.PROTECT, related_name='risks'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.OPEN)
    likelihood = models.PositiveSmallIntegerField(
        choices=Likelihood.choices, default=Likelihood.POSSIBLE,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    impact = models.PositiveSmallIntegerField(
        choices=Impact.choices, default=Impact.MODERATE,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    treatment_strategy = models.CharField(max_length=16, choices=TreatmentStrategy.choices, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_risks'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(likelihood__gte=1, likelihood__lte=5),
                                   name='risk_likelihood_1_to_5'),
            models.CheckConstraint(condition=models.Q(impact__gte=1, impact__lte=5),
                                   name='risk_impact_1_to_5'),
        ]

    @property
    def risk_score(self):
        return calculate_score(self.likelihood, self.impact)

    @property
    def risk_class(self):
        return classify_score(self.risk_score)

    def clean(self):
        super().clean()
        if self.pk and self.measures.exclude(organization_id=self.organization_id).exists():
            raise ValidationError({'organization': 'Risiken mit Massnahmen koennen die Organisation nicht wechseln.'})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class RiskMeasure(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Geplant'
        IN_PROGRESS = 'IN_PROGRESS', 'In Bearbeitung'
        IMPLEMENTED = 'IMPLEMENTED', 'Umgesetzt'
        OVERDUE = 'OVERDUE', '\u00dcberf\u00e4llig / nicht umgesetzt'

    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT,
                                     related_name='risk_measures')
    risk = models.ForeignKey(Risk, on_delete=models.CASCADE, related_name='measures')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PLANNED)
    responsible_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                         related_name='risk_measures', null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.risk_id:
            organization_id = self.risk.organization_id
            if self.organization_id and self.organization_id != organization_id:
                raise ValidationError({'organization': 'Massnahme und Risiko muessen derselben Organisation angehoeren.'})
            self.organization_id = organization_id
        if self.responsible_user_id and not self.responsible_user.memberships.filter(
            organization_id=self.organization_id, is_active=True, user__is_active=True,
        ).exists():
            raise ValidationError({'responsible_user': 'Bitte waehlen Sie ein aktives Mitglied der Organisation.'})

    def save(self, *args, **kwargs):
        if self.risk_id and not self.organization_id:
            self.organization_id = self.risk.organization_id
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title
