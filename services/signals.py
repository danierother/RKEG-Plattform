from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from incidents.models import Incident
from risks.models import Risk
from .models import CriticalService


@receiver(m2m_changed, sender=CriticalService.locations.through)
@receiver(m2m_changed, sender=Risk.critical_services.through)
@receiver(m2m_changed, sender=Incident.affected_services.through)
@receiver(m2m_changed, sender=Incident.affected_locations.through)
def validate_organization_links(sender, instance, action, model, pk_set, using, **kwargs):
    if action == 'pre_add' and pk_set:
        if model.objects.using(using).filter(pk__in=pk_set).exclude(organization_id=instance.organization_id).exists():
            raise ValidationError('Verknuepfungen sind nur innerhalb derselben Organisation erlaubt.')
