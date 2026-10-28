"""Pure evaluations plus explicit, append-only persistence. GET never writes."""
import calendar
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, localcontext

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from organizations.mixins import WRITE_ROLES
from .models import Incident, IncidentRKEGAssessment, IncidentReport, RKEGFacts
from .rkeg_rules import EFFECTIVE_FROM, EXEMPT_SECTORS, RULE_BY_CODE, RULE_VERSION, SECTORS
from audit.services import record_change
from services.models import CriticalService
from .models import IncidentServiceImpact

Result = IncidentRKEGAssessment.Result
LEGAL_REFERENCE = 'RKEG BGBl. I 60/2025 § 17, § 18 Abs. 3; RKEV BGBl. II 91/2026 §§ 2-14'
FACT_FIELDS = tuple(field.name for field in RKEGFacts._meta.fields)


def serialized(value):
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, timedelta):
        return str(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def facts_snapshot(facts):
    return {name: serialized(getattr(facts, name)) for name in FACT_FIELDS}


def duration_microseconds(duration):
    return (duration.days * 86400 + duration.seconds) * 1000000 + duration.microseconds


def hours(duration, count=1):
    with localcontext() as context:
        context.prec = 50
        return (Decimal(duration_microseconds(duration)) * count / Decimal(3600000000)).quantize(Decimal('0.00000001'))


@dataclass
class Evaluation:
    result: str
    explanation: str
    details: list
    snapshot: dict
    evaluated_at: datetime

    @property
    def label(self):
        return Result(self.result).label


def evaluate_service(organization, service, facts, now):
    rule = RULE_BY_CODE.get(service.rkeg_service_code)
    detail = dict(service_id=service.pk, service_name=service.name, sector=service.rkeg_sector,
                  sector_label=dict(SECTORS).get(service.rkeg_sector, 'Nicht zugeordnet'),
                  subsector=service.rkeg_subsector, service_code=service.rkeg_service_code,
                  service_reference=service.rkeg_service_reference, rule=None, duration=None,
                  user_hours=None, metering_point_hours=None, threshold_value=None, unit='', facts=None)

    def finish(result, explanation):
        return dict(detail, result=result, label=Result(result).label, explanation=explanation)

    if service.organization_id != organization.pk:
        raise PermissionDenied('Fremder Dienst.')
    if organization.rkeg_classified is False:
        return finish(Result.NOT_APPLICABLE, 'Keine behoerdliche Einstufung dokumentiert; keine Aussage zu anderen Meldepflichten.')
    if organization.rkeg_classified is not True or not organization.rkeg_classification_reference.strip():
        return finish(Result.MANUAL_REVIEW, 'Behoerdliche Einstufung / Referenz unvollstaendig.')
    if not service.rkeg_sector or not service.rkeg_service_reference.strip():
        return finish(Result.INSUFFICIENT_DATA, 'Bescheidzuordnung des wesentlichen Dienstes fehlt.')
    if service.rkeg_sector in EXEMPT_SECTORS:
        return finish(Result.EXEMPT_SECTOR, '§ 17 RKEG ist fuer diesen Sektor nicht anwendbar. Die einschlaegigen sektorspezifischen Meldepflichten sind gesondert zu pruefen.')
    obligation_start = organization.rkeg_reporting_obligation_start_date
    if obligation_start is None:
        return finish(Result.MANUAL_REVIEW, 'Beginn der Meldepflicht nicht dokumentiert.')
    if timezone.localdate(now) < obligation_start:
        return finish(Result.NOT_APPLICABLE, 'Der dokumentierte Beginn der Meldepflicht liegt noch in der Zukunft.')
    if not rule or rule.sector != service.rkeg_sector or rule.subsector != service.rkeg_subsector:
        return finish(Result.MANUAL_REVIEW, 'Keine eindeutig passende versionierte Regel fuer diese Dienstzuordnung.')
    detail.update(rule={key: serialized(value) for key, value in asdict(rule).items()},
                  threshold_value=rule.threshold_value, unit=rule.unit)
    if facts is None:
        return finish(Result.INSUFFICIENT_DATA, 'Bei mehreren Diensten sind dienstbezogene Stoerungsdaten erforderlich.')
    detail['facts'] = facts_snapshot(facts)
    detail['disruption_label'] = dict(RKEGFacts.DisruptionStatus.choices).get(facts.disruption_status, 'Nicht hinterlegt')
    start, end = facts.disruption_started_at, facts.disruption_ended_at
    if not start or not facts.disruption_status:
        return finish(Result.INSUFFICIENT_DATA, 'Beginn oder Art der Stoerung fehlt.')
    if start > now or (end and (end < start or end > now)):
        return finish(Result.MANUAL_REVIEW, 'Zeitangaben widerspruechlich oder in der Zukunft.')
    if timezone.localdate(start) < max(EFFECTIVE_FROM, obligation_start):
        return finish(Result.MANUAL_REVIEW, 'Stoerungsbeginn liegt vor der dokumentierten Anwendbarkeit dieser Regel. Zeitliche Abgrenzung pruefen.')
    duration = (end or now).astimezone(dt_timezone.utc) - start.astimezone(dt_timezone.utc)
    detail['duration'] = str(duration)
    detail['duration_microseconds'] = duration_microseconds(duration)
    if facts.unplanned_confirmed is not True:
        return finish(Result.MANUAL_REVIEW, 'Ungeplante Stoerung nach RKEV § 2 nicht bestaetigt.')
    if facts.disruption_status == 'RESTRICTED_AVAILABILITY' and facts.significant_impairment_confirmed is not True:
        return finish(Result.MANUAL_REVIEW, 'Qualitative Voraussetzungen der eingeschraenkten Verfuegbarkeit nach RKEV § 2 Z 2 sind nicht bestaetigt.')
    if facts.disruption_status not in ('OUTAGE', 'RESTRICTED_AVAILABILITY'):
        return finish(Result.MANUAL_REVIEW, 'Unbekannte Stoerungsart.')
    if rule.threshold_type == 'SPECIAL':
        if facts.special_threshold_condition_met is None or not facts.special_threshold_description.strip():
            return finish(Result.INSUFFICIENT_DATA, 'Sonderkriterium und dessen Dokumentation fehlen.')
        exceeded = facts.special_threshold_condition_met is True
    else:
        count = 1
        if rule.threshold_type in ('USER_HOURS', 'METER_HOURS'):
            count = facts.affected_users if rule.threshold_type == 'USER_HOURS' else facts.affected_metering_points
            if count is None:
                return finish(Result.INSUFFICIENT_DATA, 'Betroffene Nutzer- bzw. Zaehlpunktzahl fehlt; keine Schaetzung.')
            if count < 0:
                return finish(Result.MANUAL_REVIEW, 'Ungueltige Betroffenenzahl.')
            key = 'user_hours' if rule.threshold_type == 'USER_HOURS' else 'metering_point_hours'
            detail[key] = str(hours(duration, count))
        # Integer comparison avoids rounding at strict statutory boundaries.
        exceeded = duration_microseconds(duration) * count > rule.threshold_value * 3600000000
    if exceeded:
        return finish(Result.REPORTABLE, 'Die hinterlegte RKEV-Schwelle ist auf Basis der dokumentierten Tatsachen eindeutig erfuellt.')
    if end is None:
        return finish(Result.MANUAL_REVIEW, 'Laufende Stoerung: bisherige Schwelle nicht ueberschritten; weitere Entwicklung und potenzielle Stoerung pruefen.')
    return finish(Result.BELOW_THRESHOLD, 'Beendete Stoerung: hinterlegte Schwelle nicht ueberschritten. Keine allgemeine rechtliche Entwarnung; potenzielle Stoerungen und parallele Pflichten gesondert pruefen.')


def evaluate_incident(incident, now=None):
    now = now or timezone.now()
    org = incident.organization
    services = incident.reporting_services if hasattr(incident, 'reporting_services') else list(incident.affected_services.filter(organization=org).order_by('pk'))
    impact_rows = incident.reporting_impacts if hasattr(incident, 'reporting_impacts') else incident.service_impacts.filter(organization=org, service__organization=org)
    impacts = {row.service_id: row for row in impact_rows}
    snapshot = {'organization_id': org.pk, 'rkeg_classified': org.rkeg_classified,
                'classification_reference': org.rkeg_classification_reference,
                'obligation_start': serialized(org.rkeg_reporting_obligation_start_date),
                'rkeg_awareness_at': serialized(incident.rkeg_awareness_at), 'incident_facts': facts_snapshot(incident)}
    details = [evaluate_service(org, service, impacts.get(service.pk, incident if len(services) == 1 else None), now)
               for service in services]
    results = {item['result'] for item in details}
    if not details:
        result = Result.NOT_APPLICABLE if org.rkeg_classified is False else Result.INSUFFICIENT_DATA
        explanation = 'Keine behoerdliche Einstufung dokumentiert.' if result == Result.NOT_APPLICABLE else 'Kein wesentlicher Dienst zugeordnet. Manuelle Pruefung erforderlich.'
    else:
        result = next((value for value in (Result.REPORTABLE, Result.INSUFFICIENT_DATA, Result.MANUAL_REVIEW,
                      Result.BELOW_THRESHOLD, Result.NOT_APPLICABLE, Result.EXEMPT_SECTOR) if value in results), Result.NOT_ASSESSED)
        explanation = 'Einzelergebnisse je Dienst; eine eindeutig erfuellte Regel hat Vorrang. ' + Result(result).label
    return Evaluation(result, explanation, details, snapshot, now)


def require_writer(incident, user):
    if not user.is_active or not user.memberships.filter(organization_id=incident.organization_id,
            is_active=True, role__in=WRITE_ROLES).exists():
        raise PermissionDenied


@transaction.atomic
def record_assessment(incident, user, override_result='', override_reason='', *, source='SYSTEM'):
    require_writer(incident, user)
    evaluation = evaluate_incident(incident)
    single = evaluation.details[0] if len(evaluation.details) == 1 else {}
    automatic = IncidentRKEGAssessment.objects.create(incident=incident, organization=incident.organization,
        assessed_by=user, assessed_at=evaluation.evaluated_at, result=evaluation.result,
        applied_rule=evaluation.details, input_snapshot=evaluation.snapshot, legal_reference=LEGAL_REFERENCE,
        calculated_duration=timedelta(microseconds=single['duration_microseconds']) if 'duration_microseconds' in single else None,
        calculated_user_hours=single.get('user_hours'), calculated_metering_point_hours=single.get('metering_point_hours'),
        threshold_value=single.get('threshold_value'), explanation=evaluation.explanation, rule_version=RULE_VERSION)
    record_change(automatic, None, organization=incident.organization, actor=user, source=source)
    if override_result:
        manual = IncidentRKEGAssessment.objects.create(incident=incident, organization=incident.organization,
            assessed_by=user, result=override_result, based_on=automatic, manual_override=True,
            manual_override_reason=override_reason, applied_rule=evaluation.details, input_snapshot=evaluation.snapshot,
            legal_reference=LEGAL_REFERENCE, explanation='Manuelle fachliche Bewertung; automatisches Ergebnis bleibt erhalten.',
            rule_version=RULE_VERSION)
        record_change(manual, None, organization=incident.organization, actor=user, source=source)
        return manual
    return automatic


def add_calendar_month(value):
    local = timezone.localtime(value)
    year = local.year + (local.month == 12)
    month = local.month % 12 + 1
    return local.replace(year=year, month=month, day=min(local.day, calendar.monthrange(year, month)[1]))


def current_manual_assessment(incident, evaluation):
    latest = next(iter(incident.reporting_assessments), None) if hasattr(incident, 'reporting_assessments') else incident.rkeg_assessments.filter(organization_id=incident.organization_id).order_by('-assessed_at', '-pk').first()
    if not latest or not latest.manual_override or latest.rule_version != RULE_VERSION or latest.input_snapshot != evaluation.snapshot:
        return None
    keys = ('service_id', 'sector', 'subsector', 'service_code', 'service_reference', 'facts')
    signature = lambda rows: [{key: row.get(key) for key in keys} for row in rows]
    if signature(latest.applied_rule) != signature(evaluation.details):
        return None
    # A previously subthreshold running incident can cross the boundary later.
    if [row['result'] for row in latest.applied_rule] != [row['result'] for row in evaluation.details]:
        return None
    return latest


def deadlines(incident, evaluation, now=None):
    now = now or timezone.now()
    reports = [row for row in incident.reporting_reports if row.status == IncidentReport.Status.MARKED_AS_SUBMITTED] if hasattr(incident, 'reporting_reports') else list(incident.reports.filter(organization_id=incident.organization_id,
        status=IncidentReport.Status.MARKED_AS_SUBMITTED).order_by('submitted_at', 'pk'))
    first = next((row for row in reports if row.report_type == 'INITIAL'), None)
    follow = any(row.report_type == 'FOLLOW_UP' and first and row.submitted_at >= first.submitted_at for row in reports)
    end_reported = any(row.report_type == 'END_NOTIFICATION' for row in reports)
    reportable = evaluation.result == Result.REPORTABLE
    # Already documented reportable snapshots keep reporting work visible after edits.
    recorded_reportable = any(row.result == Result.REPORTABLE for row in incident.reporting_assessments) if hasattr(incident, 'reporting_assessments') else incident.rkeg_assessments.filter(organization_id=incident.organization_id, result=Result.REPORTABLE).exists()
    required = reportable or recorded_reportable or first is not None
    initial_due = (incident.rkeg_awareness_at.astimezone(dt_timezone.utc) + timedelta(hours=24)) if required and incident.rkeg_awareness_at else None
    follow_due = add_calendar_month(first.submitted_at) if first else None
    ended = incident.disruption_ended_at is not None or (
        bool(evaluation.details) and all(row.get('facts') and row['facts']['disruption_ended_at'] for row in evaluation.details))
    return dict(required=required, initial_report=first, initial_due_at=initial_due,
        initial_overdue=bool(required and not first and initial_due and initial_due < now),
        initial_due_24h=bool(required and not first and initial_due and now <= initial_due <= now + timedelta(hours=24)),
        missing_awareness=bool(required and not incident.rkeg_awareness_at),
        follow_up_due_at=follow_due, follow_up_reported=follow,
        follow_up_due=bool(follow_due and not follow and follow_due <= now + timedelta(hours=24)),
        end_notification_required=bool(required and ended and not end_reported))


def reporting_dashboard(organization):
    counts = dict(reportable_open=0, initial_due=0, initial_overdue=0, follow_up_due=0, manual_review=0)
    for incident in reporting_queryset(organization):
        evaluation = evaluate_incident(incident)
        timing = deadlines(incident, evaluation)
        manual = current_manual_assessment(incident, evaluation)
        if timing['required'] and incident.status in Incident.OPEN_STATUSES:
            counts['reportable_open'] += 1
        counts['initial_due'] += timing['initial_due_24h']
        counts['initial_overdue'] += timing['initial_overdue']
        counts['follow_up_due'] += timing['follow_up_due']
        effective_result = manual.result if manual else evaluation.result
        counts['manual_review'] += (effective_result in (Result.INSUFFICIENT_DATA, Result.MANUAL_REVIEW, Result.NOT_ASSESSED)
                                    or timing['missing_awareness'])
    return counts


def reporting_queryset(organization):
    """Bounded query count for reports; every prefetched relation is tenant-scoped."""
    return Incident.objects.filter(organization=organization).select_related('organization', 'responsible_user').prefetch_related(
        Prefetch('affected_services', queryset=CriticalService.objects.filter(organization=organization).order_by('pk'), to_attr='reporting_services'),
        Prefetch('service_impacts', queryset=IncidentServiceImpact.objects.filter(organization=organization, service__organization=organization), to_attr='reporting_impacts'),
        Prefetch('reports', queryset=IncidentReport.objects.filter(organization=organization).order_by('submitted_at', 'pk'), to_attr='reporting_reports'),
        Prefetch('rkeg_assessments', queryset=IncidentRKEGAssessment.objects.filter(organization=organization).order_by('-assessed_at', '-pk'), to_attr='reporting_assessments'),
    )
