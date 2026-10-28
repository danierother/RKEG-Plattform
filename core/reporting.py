"""Shared read-only datasets for HTML, CSV and print reports."""
from dataclasses import dataclass

from django.db.models import Prefetch
from django.urls import reverse
from django.utils import timezone

from incidents.models import Incident, IncidentAction
from incidents.rkeg_reporting import Result, current_manual_assessment, deadlines, evaluate_incident, reporting_queryset
from risks.assessment import DEFAULT_RISK_BANDS, score_expression
from risks.models import Risk, RiskMeasure
from services.models import CriticalService, Location, ServiceDependency


@dataclass
class Row:
    cells: tuple
    url: str = ''


@dataclass
class Table:
    title: str
    headings: tuple
    rows: list


def display(value):
    if value is None or value == '':
        return 'Nicht hinterlegt'
    if hasattr(value, 'hour'):
        return timezone.localtime(value).strftime('%d.%m.%Y %H:%M')
    if hasattr(value, 'strftime'):
        return value.strftime('%d.%m.%Y')
    return str(value)


def user_name(user):
    return user.get_full_name() or user.username if user else 'Nicht zugewiesen'


def names(objects):
    return ', '.join(obj.name for obj in objects) or 'Keine'


def period(queryset, filters, field):
    for name, suffix in (('date_from', 'gte'), ('date_to', 'lte')):
        if filters.get(name):
            queryset = queryset.filter(**{f'{field}__{suffix}': filters[name]})
    return queryset


def risk_queryset(organization):
    return Risk.objects.filter(organization=organization).select_related('created_by').annotate(
        gross_score=score_expression(), residual_score=score_expression(residual=True)).prefetch_related(
        Prefetch('critical_services', queryset=CriticalService.objects.filter(organization=organization).order_by('name', 'pk'), to_attr='report_services'),
        Prefetch('measures', queryset=RiskMeasure.objects.filter(organization=organization, risk__organization=organization).select_related('responsible_user'), to_attr='report_measures'))


def risk_table(organization, filters):
    queryset = period(risk_queryset(organization), filters, 'updated_at__date')
    if filters.get('status'):
        queryset = queryset.filter(status=filters['status'])
    if filters.get('service'):
        queryset = queryset.filter(critical_services=filters['service'])
    for field, score in (('risk_class', 'gross_score'), ('residual_risk_class', 'residual_score')):
        band = next((band for band in DEFAULT_RISK_BANDS if band.code == filters.get(field)), None)
        if band:
            queryset = queryset.filter(**{score+'__gte': band.minimum, score+'__lte': band.maximum})
    rows = []
    for risk in queryset.order_by('-residual_score', 'title', 'pk'):
        open_measures = [item for item in risk.report_measures if item.status != RiskMeasure.Status.IMPLEMENTED]
        owners = sorted({user_name(item.responsible_user) for item in open_measures if item.responsible_user})
        rows.append(Row((risk.title, names(risk.report_services), f'{risk.risk_score} / {risk.risk_class}',
            f'{risk.residual_risk_score} / {risk.residual_risk_class}', risk.get_treatment_strategy_display() or 'Nicht festgelegt',
            len(open_measures), ', '.join(owners) or 'Nicht zugewiesen', display(risk.updated_at)), reverse('risks:detail', args=[risk.pk])))
    return Table('Risikobericht', ('Titel', 'Dienstleistungen', 'Bruttowert / Klasse', 'Restrisikowert / Klasse',
                                 'Behandlungsstrategie', 'Offene Massnahmen', 'Massnahmenverantwortliche', 'Geaendert am'), rows)


def action_records(organization, filters, today):
    output = []
    for kind, model, relation, closed in (
        ('risk', RiskMeasure, 'risk', (RiskMeasure.Status.IMPLEMENTED,)),
        ('incident', IncidentAction, 'incident', (IncidentAction.Status.DONE, IncidentAction.Status.CANCELLED)),
    ):
        if filters.get('type') and filters['type'] != kind:
            continue
        queryset = model.objects.filter(organization=organization, **{relation+'__organization': organization}).select_related(relation, 'responsible_user')
        queryset = period(queryset, filters, 'due_date')
        for key in ('status', 'responsible_user'):
            if filters.get(key):
                queryset = queryset.filter(**{key: filters[key]})
        for item in queryset:
            overdue = item.status not in closed and (bool(item.due_date and item.due_date < today) or (kind == 'risk' and item.status == 'OVERDUE'))
            if filters.get('overdue') and overdue != (filters['overdue'] == 'yes'):
                continue
            parent = getattr(item, relation)
            output.append(dict(kind=kind, obj=item, parent=parent, overdue=overdue))
    output.sort(key=lambda row: (not row['overdue'], row['obj'].due_date is None, row['obj'].due_date or today, row['kind'], row['obj'].pk))
    return output


def actions_table(organization, filters, now):
    rows = []
    for record in action_records(organization, filters, timezone.localdate(now)):
        item, parent = record['obj'], record['parent']
        url = reverse('risks:detail' if record['kind'] == 'risk' else 'incidents:detail', args=[parent.pk])
        rows.append(Row(('Risikomassnahme' if record['kind'] == 'risk' else 'Vorfallmassnahme', parent.title,
            item.title, item.get_status_display(), user_name(item.responsible_user), display(item.due_date),
            'Ja' if record['overdue'] else 'Nein'), url))
    return Table('Massnahmenbericht', ('Typ', 'Bezug', 'Titel', 'Status', 'Verantwortlich', 'Faelligkeit', 'Ueberfaellig'), rows)


def services_queryset(organization):
    return CriticalService.objects.filter(organization=organization).select_related('service_owner').prefetch_related(
        Prefetch('locations', queryset=Location.objects.filter(organization=organization).order_by('name'), to_attr='report_locations'),
        Prefetch('risks', queryset=Risk.objects.filter(organization=organization).only('pk'), to_attr='report_risks'),
        Prefetch('incidents', queryset=Incident.objects.filter(organization=organization).only('pk'), to_attr='report_incidents'),
        Prefetch('dependencies', queryset=ServiceDependency.objects.filter(organization=organization, service__organization=organization).order_by('name'), to_attr='report_dependencies'))


def services_table(organization, filters):
    rows = []
    for service in period(services_queryset(organization), filters, 'updated_at__date').order_by('-criticality', 'recovery_priority', 'name', 'pk'):
        dependencies = '; '.join(f'{item.name}: {item.get_dependency_type_display()}, {item.criticality}, '
            f'{item.get_internal_external_display()}, Ausweichloesung: {"Ja" if item.contingency_available else "Nein"}' for item in service.report_dependencies) or 'Keine'
        rows.append(Row((service.name, service.criticality, service.recovery_priority, service.mtd_display, service.rto_display,
            names(service.report_locations), len(service.report_risks), len(service.report_incidents), len(service.report_dependencies),
            sum(item.single_point_of_failure for item in service.report_dependencies), dependencies), reverse('services:detail', args=[service.pk])))
    return Table('Kritische Dienstleistungen / Abhaengigkeiten', ('Dienstleistung', 'Kritikalitaet', 'Recovery Priority',
        'MTD', 'RTO', 'Standorte', 'Risiken', 'Vorfaelle', 'Abhaengigkeiten', 'SPOFs', 'Abhaengigkeitsdetails'), rows)


def incident_records(organization, filters, now):
    queryset = period(reporting_queryset(organization), filters, 'occurred_at__date')
    for key in ('status', 'severity', 'incident_type'):
        if filters.get(key):
            queryset = queryset.filter(**{key: filters[key]})
    for incident in queryset.order_by('-occurred_at', '-pk'):
        evaluation = evaluate_incident(incident, now=now)
        if filters.get('rkeg_result') and filters['rkeg_result'] != evaluation.result:
            continue
        yield dict(incident=incident, evaluation=evaluation, timing=deadlines(incident, evaluation, now=now),
                   manual=current_manual_assessment(incident, evaluation))


def incidents_table(records):
    rows = []
    for record in records:
        item, evaluation = record['incident'], record['evaluation']
        rows.append(Row((item.title, item.get_status_display(), f'{item.severity} / {item.get_severity_display()}',
            item.get_incident_type_display(), names(item.reporting_services), display(item.occurred_at), user_name(item.responsible_user),
            evaluation.label, item.get_reporting_status_display()), reverse('incidents:detail', args=[item.pk])))
    return Table('Vorfallsbericht', ('Titel', 'Status', 'Schweregrad', 'Vorfallart', 'Betroffene Dienste', 'Ereigniszeit',
                                    'Verantwortlich', 'RKEG-Ergebnis (automatisch)', 'Manueller Reportingstatus'), rows)


def rkeg_table(records):
    rows = []
    for record in records:
        item, evaluation, timing, manual = (record[key] for key in ('incident', 'evaluation', 'timing', 'manual'))
        for detail in evaluation.details or [dict(service_name='Nicht zugeordnet', result=evaluation.result, label=evaluation.label)]:
            rule = detail.get('rule') or {}
            metric = detail.get('user_hours') or detail.get('metering_point_hours') or detail.get('duration') or 'Nicht berechenbar'
            if rule.get('threshold_type') == 'SPECIAL':
                metric = str((detail.get('facts') or {}).get('special_threshold_condition_met', 'Nicht dokumentiert'))
            rows.append(Row((item.title, detail['service_name'], evaluation.label, detail['label'],
                rule.get('legal_reference', 'Keine passende Regel'),
                f"> {rule['threshold_value']} {rule['unit']}" if rule.get('threshold_value') is not None else rule.get('unit', 'Nicht bestimmt'),
                metric, display(item.rkeg_awareness_at), display(timing['initial_due_at']),
                display(timing['initial_report'].submitted_at) if timing['initial_report'] else 'Nein',
                display(timing['follow_up_due_at']), 'Ja, unverzueglich' if timing['end_notification_required'] else 'Nein / noch nicht festgestellt',
                f'{manual.get_result_display()}: {manual.manual_override_reason}' if manual else 'Keine aktuelle Uebersteuerung'),
                reverse('incidents:detail', args=[item.pk])))
    return Table('RKEG-Meldestatus', ('Vorfall', 'Wesentlicher Dienst', 'Gesamtergebnis (automatisch)', 'Einzelergebnis',
        'Regel', 'Schwelle', 'Berechneter Wert', 'Kenntniszeit', 'Erstmeldung spaetestens', 'Erstmeldung erfolgt',
        'Folgemeldung spaetestens', 'Beendigungsmeldung erforderlich', 'Manuelle Uebersteuerung'), rows)


def management_report(organization, now):
    risks = list(risk_queryset(organization).order_by('-residual_score', 'title', 'pk'))
    services = list(services_queryset(organization))
    deps = list(ServiceDependency.objects.filter(organization=organization, service__organization=organization).select_related('service'))
    incidents = list(incident_records(organization, {}, now))
    overdue = actions_table(organization, {'overdue': 'yes'}, now)
    metrics = [('Risiken gesamt', len(risks))]
    for name, attr in (('Brutto', 'risk_class'), ('Restrisiko', 'residual_risk_class')):
        metrics.extend((f'{name}: {band.label}', sum(getattr(risk, attr).code == band.code for risk in risks)) for band in DEFAULT_RISK_BANDS)
    metrics += [('Kritische Bruttorisiken', sum(risk.risk_score >= 17 for risk in risks)),
        ('Ueberfaellige Massnahmen', len(overdue.rows)), ('Aktive Dienstleistungen', sum(item.status == 'ACTIVE' for item in services)),
        ('Dienstleistungen Kritikalitaet 4/5', sum(item.criticality >= 4 for item in services)),
        ('Kritische Abhaengigkeiten', sum(item.criticality >= 4 for item in deps)), ('Single Points of Failure', sum(item.single_point_of_failure for item in deps)),
        ('Offene Vorfaelle', sum(row['incident'].status in Incident.OPEN_STATUSES for row in incidents)),
        ('Kritische Vorfaelle', sum(row['incident'].severity == 5 for row in incidents)),
        ('Meldepflichtige Vorfaelle / dokumentierte Meldeaufgaben', sum(row['timing']['required'] for row in incidents)),
        ('Manuelle Pruefungen offen', sum((row['manual'].result if row['manual'] else row['evaluation'].result) in (Result.MANUAL_REVIEW, Result.INSUFFICIENT_DATA, Result.NOT_ASSESSED) or row['timing']['missing_awareness'] for row in incidents)),
        ('Ueberfaellige Erstmeldungen', sum(row['timing']['initial_overdue'] for row in incidents))]
    top = Table('Top 10 Restrisiken', ('Risiko', 'Restrisikowert', 'Restrisikoklasse'),
        [Row((risk.title, risk.residual_risk_score, risk.residual_risk_class.label), reverse('risks:detail', args=[risk.pk])) for risk in risks[:10]])
    critical = incidents_table([row for row in incidents if row['incident'].status in Incident.OPEN_STATUSES and row['incident'].severity == 5])
    critical.title = 'Offene kritische Vorfaelle'
    spofs = Table('Kritische Single Points of Failure', ('Abhaengigkeit', 'Dienstleistung', 'Kritikalitaet', 'Ausweichloesung'),
        [Row((item.name, item.service.name, item.criticality, 'Ja' if item.contingency_available else 'Nein'), reverse('services:dependency-detail', args=[item.service_id, item.pk]))
         for item in deps if item.single_point_of_failure and item.criticality >= 4])
    overdue.title = 'Ueberfaellige Massnahmen'
    return metrics, [top, overdue, critical, spofs]
