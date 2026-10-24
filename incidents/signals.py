from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from risks.models import Risk
from .models import Incident


@receiver(m2m_changed, sender=Incident.risks.through)
def validate_incident_risks(sender, instance, action, reverse, pk_set, using, **kwargs):
    if action != 'pre_add' or not pk_set:
        return
    model = Incident if reverse else Risk
    if model.objects.using(using).filter(pk__in=pk_set).exclude(organization_id=instance.organization_id).exists():
        raise ValidationError('Vorfall und verknuepfte Risiken muessen derselben Organisation angehoeren.')
