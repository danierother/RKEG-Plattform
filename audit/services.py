"""Explicit audit boundaries, without request globals or signal cascades."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.deletion import Collector

from organizations.mixins import WRITE_ROLES
from .models import AuditEvent

# Explicit allowlist: no credentials, arbitrary request payloads or user snapshots.
FIELDS = {
    'risks.risk': 'title description risk_source potential_impact status likelihood impact residual_likelihood residual_impact treatment_strategy created_by_id',
    'risks.riskcontrol': 'risk_id title description control_type effectiveness responsible_user_id',
    'risks.riskmeasure': 'risk_id title description status responsible_user_id due_date',
    'services.location': 'name description address_line postal_code city country location_type is_active',
    'services.criticalservice': 'name description service_owner_id status criticality recovery_priority maximum_tolerable_downtime recovery_time_objective notes rkeg_sector rkeg_subsector rkeg_service_code rkeg_service_reference',
    'services.servicedependency': 'service_id name description dependency_type criticality supplier_name internal_external single_point_of_failure contingency_available notes',
    'incidents.incident': 'title description occurred_at detected_at created_by_id responsible_user_id status severity incident_type affected_service affected_location impact_description immediate_actions suspected_reportable reporting_status rkeg_awareness_at',
    'incidents.incidentevent': 'incident_id event_time event_type description created_by_id',
    'incidents.incidentaction': 'incident_id title description status responsible_user_id due_date completed_at',
    'incidents.incidentreport': 'incident_id report_type status submitted_at created_by_id incident_type_description suspected_cause confirmed_cause consequences measures_taken affected_critical_infrastructure cross_border_information additional_information',
    'incidents.incidentrkegassessment': 'incident_id result assessed_at assessed_by_id legal_reference applied_rule input_snapshot calculated_duration calculated_user_hours calculated_metering_point_hours threshold_value explanation manual_override manual_override_reason based_on_id rule_version',
    'incidents.incidentserviceimpact': 'incident_id service_id',
    'organizations.organization': 'rkeg_classified rkeg_classification_reference rkeg_reporting_obligation_start_date',
}
FACT_FIELDS = 'disruption_started_at disruption_ended_at disruption_status unplanned_confirmed significant_impairment_confirmed affected_users affected_metering_points affected_geographic_area cross_border_impact special_threshold_condition_met special_threshold_description'
FIELDS['incidents.incident'] += ' ' + FACT_FIELDS
FIELDS['incidents.incidentserviceimpact'] += ' ' + FACT_FIELDS
RELATIONS = {'risks.risk': ('critical_services',), 'services.criticalservice': ('locations',),
             'incidents.incident': ('risks', 'affected_services', 'affected_locations')}


def value(raw):
    if isinstance(raw, (datetime, date)):
        return raw.isoformat()
    if isinstance(raw, (Decimal, timedelta)):
        return str(raw)
    return raw


def organization_id(obj):
    return obj.pk if obj._meta.label_lower == 'organizations.organization' else obj.organization_id


def snapshot(obj):
    kind = obj._meta.label_lower
    fields = FIELDS[kind].split()
    data = {name: value(getattr(obj, name)) for name in fields}
    for name in RELATIONS.get(kind, ()):
        data[name] = list(getattr(obj, name).filter(organization_id=organization_id(obj)).order_by('pk').values_list('pk', flat=True))
    if kind == 'risks.risk':
        data.update(risk_score=obj.risk_score, risk_class=obj.risk_class.code,
                    residual_risk_score=obj.residual_risk_score, residual_risk_class=obj.residual_risk_class.code)
    return data


def authorize(organization, actor, source):
    if source == AuditEvent.Source.WEB:
        if not actor or not actor.is_active or not actor.memberships.filter(organization=organization, is_active=True, role__in=WRITE_ROLES).exists():
            raise PermissionDenied
    if source == AuditEvent.Source.ADMIN and (not actor or not actor.is_active or not actor.is_superuser):
        raise PermissionDenied


@transaction.atomic
def record_change(obj, before, *, organization, actor=None, source=AuditEvent.Source.SYSTEM, deleted=False):
    if organization_id(obj) != organization.pk:
        raise PermissionDenied('Audit-Organisation stimmt nicht mit dem Objekt ueberein.')
    authorize(organization, actor, source)
    after = None if deleted else snapshot(obj)
    kind = obj._meta.label_lower
    action = AuditEvent.Action
    base = action.DELETE if deleted else action.CREATE if before is None else action.UPDATE
    if before is None and kind == 'incidents.incidentrkegassessment':
        base = action.MANUAL_OVERRIDE if obj.manual_override else action.ASSESSMENT
    elif before is None and kind == 'incidents.incidentreport':
        base = action.REPORT_CREATED
    batch = str(uuid4())
    common = dict(organization=organization, actor=actor, source=source, object_type=kind,
                  object_id=str(obj.pk), object_repr=str(obj)[:500], metadata={'change_id': batch})
    if before is None or deleted:
        AuditEvent.objects.create(**common, action=base, old_value=before, new_value=after,
                                  change_summary=f'{obj._meta.object_name}: {action(base).label}')
    else:
        for field, new in after.items():
            old = before.get(field)
            if old == new:
                continue
            event_action = action.STATUS_CHANGE if field in ('status', 'reporting_status') else action.UPDATE
            AuditEvent.objects.create(**common, action=event_action, field_name=field, old_value=old, new_value=new,
                change_summary=f'{field}: {old} -> {new}')
    if not deleted and kind == 'incidents.incidentreport' and obj.status == 'MARKED_AS_SUBMITTED' and (before or {}).get('status') != obj.status:
        AuditEvent.objects.create(**common, action=action.REPORT_MARKED_SUBMITTED, field_name='submitted_at',
            old_value=(before or {}).get('submitted_at'), new_value=value(obj.submitted_at),
            change_summary='Externe Uebermittlung dokumentiert; keine Uebermittlung durch die Plattform.')


@contextmanager
def audited_change(obj, *, organization, actor=None, source=AuditEvent.Source.SYSTEM):
    """Wrap save + save_m2m. Audit failure rolls back the business change too."""
    with transaction.atomic():
        old = type(obj).objects.select_for_update().filter(pk=obj.pk).first() if obj.pk else None
        if old and organization_id(old) != organization.pk:
            raise PermissionDenied('Organisationswechsel wird nicht auditiert und ist hier unzulaessig.')
        before = snapshot(old) if old else None
        authorize(organization, actor, source)
        yield
        obj.refresh_from_db()
        record_change(obj, before, organization=organization, actor=actor, source=source)


def object_history(obj, organization, limit=20):
    return AuditEvent.objects.filter(organization=organization, object_type=obj._meta.label_lower,
                                    object_id=str(obj.pk)).select_related('actor')[:limit]


@transaction.atomic
def audited_delete(obj, *, organization, actor=None, source=AuditEvent.Source.SYSTEM):
    if organization_id(obj) != organization.pk or obj._meta.label_lower in ('organizations.organization', 'incidents.incidentrkegassessment'):
        raise PermissionDenied('Organisationen und Bewertungshistorien werden nicht geloescht.')
    if obj._meta.label_lower == 'incidents.incidentreport' and obj.status == 'MARKED_AS_SUBMITTED':
        raise PermissionDenied('Dokumentierte Uebermittlungen werden nicht geloescht.')
    authorize(organization, actor, source)
    collector = Collector(using=obj._state.db or 'default')
    collector.collect([obj])
    objects = [item for model, items in collector.data.items() if model._meta.label_lower in FIELDS for item in items]
    objects += [item for queryset in collector.fast_deletes if queryset.model._meta.label_lower in FIELDS for item in queryset]
    for item in objects:
        record_change(item, snapshot(item), organization=organization, actor=actor, source=source, deleted=True)
    return collector.delete()
