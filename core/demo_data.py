"""Versioned, insert-only demo fixture. No production data reconciliation."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from audit.models import AuditEvent
from audit.services import audited_change, record_change
from incidents.models import Incident, IncidentAction, IncidentEvent, IncidentReport, IncidentRKEGAssessment
from incidents.rkeg_reporting import record_assessment
from incidents.rkeg_rules import EFFECTIVE_FROM, RULE_BY_CODE
from organizations.models import Membership, Organization
from risks.models import Risk, RiskControl, RiskMeasure
from services.models import CriticalService, Location, ServiceDependency

MARKER = 'DEMO / TESTDATEN'
VERSION = 'seed_demo_data:v1'
ENERGY_NAME = 'Alpen Energie Versorgung GmbH'
LOGISTICS_NAME = 'Test Logistik GmbH'
USER_ROLES = {'demo_admin': 'ADMIN', 'demo_resilience': 'RESILIENCE_MANAGER',
              'demo_risk': 'RISK_MANAGER', 'demo_viewer': 'VIEWER', 'demo_logistics': 'ADMIN'}
SCENARIOS = {
    'A': ('Ausfall eines Umspannwerks', 'REPORTABLE'),
    'B': ('Cybervorfall: Stoerung des Leitsystems', 'BELOW_THRESHOLD'),
    'C': ('Telekommunikationsausfall', 'INSUFFICIENT_DATA'),
    'D': ('Kleine Stoerung der Fernwirktechnik', 'MANUAL_REVIEW'),
    'E': ('Kurze Unterbrechung der Ersatzversorgung', 'BELOW_THRESHOLD'),
}


def label(text):
    return f'{MARKER} | {text}'


def identity(name):
    return f'{MARKER} [{VERSION}] {name}'


def demo_summary(organizations):
    return {
        'Organisationen': len(organizations),
        'Benutzer': get_user_model().objects.filter(username__in=USER_ROLES, memberships__organization__in=organizations).distinct().count(),
        'Services': CriticalService.objects.filter(organization__in=organizations).count(),
        'Locations': Location.objects.filter(organization__in=organizations).count(),
        'Dependencies': ServiceDependency.objects.filter(organization__in=organizations).count(),
        'Risiken': Risk.objects.filter(organization__in=organizations).count(),
        'Controls': RiskControl.objects.filter(organization__in=organizations).count(),
        'RiskMeasures': RiskMeasure.objects.filter(organization__in=organizations).count(),
        'Incidents': Incident.objects.filter(organization__in=organizations).count(),
        'IncidentEvents': IncidentEvent.objects.filter(organization__in=organizations).count(),
        'IncidentActions': IncidentAction.objects.filter(organization__in=organizations).count(),
        'Assessments': IncidentRKEGAssessment.objects.filter(organization__in=organizations).count(),
        'Meldungsentwuerfe': IncidentReport.objects.filter(organization__in=organizations).count(),
        'AuditEvents': AuditEvent.objects.filter(organization__in=organizations).count(),
    }


def existing_dataset():
    organizations = list(Organization.objects.filter(name__in=(ENERGY_NAME, LOGISTICS_NAME)).order_by('pk'))
    users = list(get_user_model().objects.filter(username__in=USER_ROLES))
    if not organizations and not users:
        return None
    if len(organizations) != 2 or {obj.name for obj in organizations} != {ENERGY_NAME, LOGISTICS_NAME}:
        raise CommandError('Namens-/Benutzerkollision oder unvollstaendiger Demo-Bestand. Vorhandene Daten bleiben unveraendert.')
    if any(obj.legal_name != identity(obj.name) for obj in organizations) or len(users) != 5:
        raise CommandError('Vorhandene Organisationen/Benutzer sind nicht eindeutig dieser Demo-Version zugeordnet. Keine Aenderung.')
    for user in users:
        expected = next(obj for obj in organizations if obj.name == (LOGISTICS_NAME if user.username == 'demo_logistics' else ENERGY_NAME))
        memberships = list(user.memberships.all())
        if user.first_name != MARKER or user.last_name != VERSION or user.is_staff or user.is_superuser or len(memberships) != 1 or memberships[0].organization_id != expected.pk:
            raise CommandError('Demo-Benutzerzuordnung wurde veraendert oder ist nicht eindeutig. Keine Aenderung.')
    minimum = {'Services': 4, 'Locations': 6, 'Dependencies': 7, 'Risiken': 11, 'Controls': 8,
               'RiskMeasures': 8, 'Incidents': 6, 'IncidentEvents': 12, 'IncidentActions': 5, 'Assessments': 6, 'Meldungsentwuerfe': 2}
    counts = demo_summary(organizations)
    if any(counts[key] < count for key, count in minimum.items()):
        raise CommandError('Demo-Bestand ist unvollstaendig. Keine automatische Reparatur oder Ueberschreibung.')
    return organizations


def create_service(organization, owner, name, code, locations, criticality, priority, rto, mtd):
    rule = RULE_BY_CODE[code]
    service = CriticalService.objects.create(organization=organization, name=name, service_owner=owner,
        description=label('Fiktiver wesentlicher Dienst fuer Resilienzuebungen; keine echte Bescheidzuordnung.'),
        criticality=criticality, recovery_priority=priority,
        recovery_time_objective=timedelta(hours=rto), maximum_tolerable_downtime=timedelta(hours=mtd),
        rkeg_sector=rule.sector, rkeg_subsector=rule.subsector, rkeg_service_code=code,
        rkeg_service_reference=label(f'FIKTIVER BESCHIED / {code}'), notes=label('Ausschliesslich Prototyp-Demonstration.'))
    service.locations.set(locations)
    return service


@transaction.atomic
def seed_demo_data(password):
    if not password or not password.strip():
        raise CommandError('DEMO_PASSWORD fehlt oder ist leer.')
    existing = existing_dataset()
    if existing:
        return existing, False
    now = timezone.now().replace(microsecond=0)
    if timezone.localdate(now-timedelta(days=2)) < EFFECTIVE_FROM:
        raise CommandError('Diese Demo benoetigt einen Zeitpunkt mindestens zwei Tage nach Inkrafttreten der vorhandenen Regelversion.')
    energy = Organization.objects.create(name=ENERGY_NAME, legal_name=identity(ENERGY_NAME), rkeg_classified=True,
        rkeg_classification_reference=label('FIKTIVER BESCHIED ENERGIE / keine reale Behoerdenentscheidung'),
        rkeg_reporting_obligation_start_date=EFFECTIVE_FROM)
    logistics = Organization.objects.create(name=LOGISTICS_NAME, legal_name=identity(LOGISTICS_NAME), rkeg_classified=False,
        rkeg_classification_reference=label('Isolierter Mandant fuer Zugriffstests, keine reale Einstufung'))
    users = {}
    for username, role in USER_ROLES.items():
        user = get_user_model().objects.create_user(username=username, password=password, first_name=MARKER,
            last_name=VERSION, is_staff=False, is_superuser=False)
        Membership.objects.create(user=user, organization=logistics if username == 'demo_logistics' else energy,
                                  role=role, is_active=True)
        users[username] = user
    admin, resilience, manager = (users[key] for key in ('demo_admin', 'demo_resilience', 'demo_risk'))
    locations = []
    for name, kind, description in (
        ('Unternehmenszentrale', 'HEADQUARTERS', 'Fiktiver Verwaltungsstandort und Koordinationsraum.'),
        ('Umspannwerk Nord', 'OPERATING_SITE', 'Simulierte Schaltanlage des noerdlichen Versorgungsbereichs.'),
        ('Umspannwerk S\u00fcd', 'OPERATING_SITE', 'Simulierte Schaltanlage des suedlichen Versorgungsbereichs.'),
        ('Leitstelle', 'OFFICE', 'Fiktive zentrale Netzbetriebsfuehrung mit Schichtdienst.'),
        ('Rechenzentrum', 'DATA_CENTER', 'Simulierte Unterbringung der Leit- und Informationssysteme.'),
    ):
        locations.append(Location.objects.create(organization=energy, name=name, location_type=kind,
            description=label(description), city='Fiktiver Testort', country='AT'))
    services = [
        create_service(energy, resilience, 'Elektrizit\u00e4tsversorgung', 'E_SUPPLY', locations[:3], 5, 1, 2, 8),
        create_service(energy, manager, 'Elektrizit\u00e4tsverteilernetz', 'E_DISTRIBUTION', locations[1:4], 5, 1, 1, 4),
        create_service(energy, admin, 'Netzleitstelle / Steuerung', 'E_DISTRIBUTION', locations[3:], 4, 2, 1, 3),
    ]
    services[2].notes = label('Steuerungsfunktion des fiktiven Verteilernetzdienstes, keine eigene gesetzliche Dienstkategorie. Separate Testzuordnung zur vorhandenen Regel E_DISTRIBUTION.')
    services[2].save()
    for index, (name, kind, criticality, external, spof, contingency) in enumerate((
        ('Externe Stromversorgung', 'ENERGY', 5, True, True, False),
        ('Telekommunikation', 'TELECOMMUNICATION', 5, True, True, False),
        ('SCADA / Leitsystem', 'IT', 5, False, True, True),
        ('IT-Infrastruktur', 'IT', 4, False, False, True),
        ('Schl\u00fcsselpersonal Leitstelle', 'PERSONNEL', 4, False, True, False),
        ('Externer Netzbetreiber', 'EXTERNAL_SERVICE', 4, True, False, True),
        ('Ersatzstromversorgung', 'ENERGY', 3, False, False, True),
    )):
        ServiceDependency.objects.create(service=services[index % 3], name=name, description=label('Abhaengigkeit im fiktiven Energie-Demo-Verbund.'),
            dependency_type=kind, criticality=criticality, internal_external='EXTERNAL' if external else 'INTERNAL',
            supplier_name='Fiktiver Demo-Partner' if external else '', single_point_of_failure=spof, contingency_available=contingency,
            notes=label('Keine reale Lieferantenbeziehung.'))
    risks = []
    risk_data = (
        ('Grossfl\u00e4chiger Stromausfall', 5, 5, 4, 4, 'OPEN', 'REDUCE'),
        ('Ausfall SCADA-System', 4, 5, 3, 4, 'IN_PROGRESS', 'REDUCE'),
        ('Cyberangriff auf Leitstelle', 5, 4, 3, 4, 'OPEN', 'REDUCE'),
        ('Ausfall Telekommunikation', 4, 4, 3, 3, 'IN_PROGRESS', 'TRANSFER'),
        ('Personalausfall in Leitstelle', 3, 4, 2, 3, 'OPEN', 'REDUCE'),
        ('Brand im Umspannwerk', 2, 5, 2, 4, 'OPEN', 'TRANSFER'),
        ('Lieferantenausfall', 3, 3, 2, 2, 'CLOSED', 'AVOID'),
        ('Hochwasser', 3, 5, 3, 4, 'OPEN', 'REDUCE'),
        ('Sabotage', 2, 5, 2, 4, 'OPEN', 'ACCEPT'),
        ('Ausfall Rechenzentrum', 3, 4, 1, 3, 'IN_PROGRESS', 'REDUCE'),
    )
    for index, (title, likelihood, impact, residual_likelihood, residual_impact, status, treatment) in enumerate(risk_data):
        risk = Risk.objects.create(organization=energy, created_by=manager, title=label(title),
            description=label('Uebungsszenario zur Verfuegbarkeit der Energieversorgung und Betriebsfuehrung.'),
            risk_source='Fiktive technische, organisatorische oder externe Ursache.',
            potential_impact='Unterbrechung der Testversorgung, eingeschraenkte Steuerung und erhoehter Wiederanlaufaufwand.',
            likelihood=likelihood, impact=impact, residual_likelihood=residual_likelihood, residual_impact=residual_impact,
            status=status, treatment_strategy=treatment)
        risk.critical_services.add(services[index % 3])
        risks.append(risk)
    for index, (title, kind, effectiveness, risk_index) in enumerate((
        ('USV', 'TECHNICAL', 4, 9), ('Notstromaggregat', 'CORRECTIVE', 4, 0),
        ('Redundante Telekommunikation', 'PREVENTIVE', 3, 3), ('Netzwerksegmentierung', 'TECHNICAL', 4, 2),
        ('Zugangskontrolle', 'PREVENTIVE', 3, 8), ('Backup-Konzept', 'CORRECTIVE', 4, 1),
        ('Bereitschaftsdienst', 'ORGANIZATIONAL', 3, 4), ('Lieferantenvertrag / Ersatzlieferant', 'ORGANIZATIONAL', 2, 6),
    )):
        RiskControl.objects.create(risk=risks[risk_index], title=label(title), description='Fiktive bestehende Kontrolle, Wirksamkeit manuell beurteilt.',
            control_type=kind, effectiveness=effectiveness, responsible_user=resilience if index % 2 else manager)
    measures = []
    for index, (title, status, offset) in enumerate((
        ('Ersatzstromtest durchfuehren', 'OVERDUE', -12), ('Notfallkommunikation erproben', 'IN_PROGRESS', -3),
        ('SCADA-Wiederanlauf testen', 'PLANNED', 14), ('Segmentierung nachweisen', 'IN_PROGRESS', 7),
        ('Schichtvertretung organisieren', 'IMPLEMENTED', -5), ('Branddetektion pruefen', 'PLANNED', 30),
        ('Ersatzlieferant vertraglich absichern', 'IMPLEMENTED', -10), ('Hochwasserschutz ueberpruefen', 'PLANNED', 21),
    )):
        measures.append(RiskMeasure.objects.create(risk=risks[index], title=label(title), status=status,
            description='Fiktive Risikobehandlung fuer die Demo; kein realer Arbeitsauftrag.',
            responsible_user=resilience if index % 2 else manager, due_date=timezone.localdate(now)+timedelta(days=offset)))
    incidents = []
    # Fixed ended intervals keep exact-boundary and missing-data scenarios stable.
    for index, (key, kind, severity, status, report_status, hours, metering, ongoing) in enumerate((
        ('A', 'TECHNICAL', 5, 'CONTAINED', 'REPORTABLE', 3, 100000, False),
        ('B', 'CYBER', 4, 'RESOLVED', 'UNDER_REVIEW', 2.5, 100000, False),
        ('C', 'TECHNICAL', 3, 'ACTIVE', 'UNDER_REVIEW', 4, None, False),
        ('D', 'TECHNICAL', 2, 'ACTIVE', 'NOT_ASSESSED', 0.5, 10, True),
        ('E', 'TECHNICAL', 1, 'CLOSED', 'NOT_REPORTABLE', 0.25, 100, False),
    )):
        end = now-timedelta(hours=1)
        start = (now if ongoing else end)-timedelta(hours=hours)
        incident = Incident.objects.create(organization=energy, created_by=admin, responsible_user=resilience,
            title=label(f'{key} - {SCENARIOS[key][0]}'), description=label('Fiktiver Vorfall fuer die integrierte Demo und Meldepruefung.'),
            occurred_at=start, detected_at=start+timedelta(minutes=5), status=status, severity=severity, incident_type=kind,
            impact_description=label('Simulierte Einschraenkung des Testnetzes; keine reale Versorgungsstoerung.'),
            immediate_actions='Testbetrieb stabilisiert und Uebungskoordination informiert.', reporting_status=report_status,
            suspected_reportable=key == 'A', affected_service='Fiktive Energieversorgung', affected_location='Fiktives Testgebiet',
            disruption_started_at=start, disruption_ended_at=None if ongoing else end, disruption_status='OUTAGE',
            unplanned_confirmed=None if key == 'D' else True, affected_metering_points=metering,
            affected_geographic_area='Fiktives Uebungsgebiet Alpen Nord', cross_border_impact='NO',
            rkeg_awareness_at=start+timedelta(hours=2, minutes=35) if key == 'A' else None)
        incident.affected_services.add(services[(1, 2, 0, 1, 0)[index]])
        incident.affected_locations.add(locations[(1, 3, 3, 3, 2)[index]])
        incident.risks.add(risks[(0, 2, 3, 1, 0)[index]])
        incidents.append(incident)
    for incident in incidents[:2]:
        for minutes, kind, text in (
            (5, 'DETECTION', 'Stoerung in der Uebungsleitstelle erkannt.'),
            (10, 'ASSESSMENT', 'Betroffene Testdienste und Schweregrad erstmals bewertet.'),
            (15, 'ACTION', 'Technische Sofortmassnahmen im Testnetz eingeleitet.'),
            (20, 'ESCALATION', 'Uebungskoordination und Bereitschaft eingebunden.'),
            (25, 'COMMUNICATION', 'Interne Lageinformation an das Demo-Team uebergeben.'),
            (30, 'STATUS_CHANGE', 'Bearbeitungsstatus nach Stabilisierung aktualisiert.'),
        ):
            IncidentEvent.objects.create(incident=incident, event_time=incident.occurred_at+timedelta(minutes=minutes),
                event_type=kind, description=label(text), created_by=resilience)
    for index, (title, status) in enumerate((
        ('Ersatzversorgung aktivieren', 'DONE'), ('Technische Analyse durchfuehren', 'IN_PROGRESS'),
        ('Leitstelle informieren', 'DONE'), ('Netzsegment isolieren', 'IN_PROGRESS'), ('Lieferanten eskalieren', 'OPEN'),
    )):
        incident = incidents[0 if index < 3 else 1]
        IncidentAction.objects.create(incident=incident, title=label(title), description='Fiktiver Arbeitsauftrag im Uebungsszenario.',
            status=status, responsible_user=manager if index % 2 else resilience, due_date=timezone.localdate(now)+timedelta(days=index-2),
            completed_at=incident.occurred_at+timedelta(minutes=40) if status == 'DONE' else None)
    # A small real audit sample, never hand-crafted historical AuditEvents.
    for obj in (energy, services[0], risks[0], incidents[0]):
        record_change(obj, None, organization=energy, actor=admin, source='SYSTEM')
    with audited_change(measures[0], organization=energy, actor=manager, source='SYSTEM'):
        measures[0].description += ' Demo-Ergaenzung: Terminverzug dokumentiert.'
        measures[0].save()
    for (key, (_, expected)), incident in zip(SCENARIOS.items(), incidents):
        assessment = record_assessment(incident, admin, source='SYSTEM')
        if assessment.result != expected:
            raise CommandError(f'Demo-Szenario {key} liefert nicht das erwartete Ergebnis. Anlage vollstaendig zurueckgerollt.')
    report = IncidentReport.objects.create(incident=incidents[0], created_by=resilience, report_type='INITIAL',
        incident_type_description=label('Technischer Ausfall eines fiktiven Umspannwerks.'),
        suspected_cause='Simulierter Schaltanlagenfehler; technische Analyse laeuft.',
        consequences='300.000 Zaehlpunktstunden im abgeschlossenen Testintervall.',
        measures_taken='Ersatzversorgung aktiviert und Demo-Leitstelle informiert.',
        affected_critical_infrastructure='Fiktives Umspannwerk Nord', cross_border_information='Keine im Test dokumentiert.',
        additional_information=label('Interner Entwurf. Nicht an eine Behoerde uebermitteln.'))
    record_change(report, None, organization=energy, actor=resilience, source='SYSTEM')
    create_logistics(logistics, users['demo_logistics'], now)
    return [energy, logistics], True


def create_logistics(organization, user, now):
    location = Location.objects.create(organization=organization, name=label('Logistik-Testlager'), location_type='WAREHOUSE',
        description='Fiktiver zweiter Mandant fuer Isolationstests.', city='Fiktiver Logistik-Testort', country='AT')
    service = create_service(organization, user, label('Logistik-Testdienst'), 'FOOD_LOGISTICS', [location], 3, 3, 8, 24)
    risk = Risk.objects.create(organization=organization, created_by=user, title=label('LOGISTIK EXKLUSIV - Kuehlkettenausfall'),
                               description='Nur fuer den zweiten Demo-Mandanten sichtbar.')
    risk.critical_services.add(service)
    incident = Incident.objects.create(organization=organization, created_by=user, title=label('LOGISTIK EXKLUSIV - Teststoerung'),
        description='Mandantentrennung pruefen.', occurred_at=now-timedelta(hours=2), detected_at=now-timedelta(hours=1, minutes=55),
        impact_description='Ausschliesslich fiktive Daten im zweiten Mandanten.', affected_service=label('Logistik-Testdienst'))
    incident.affected_services.add(service)
    incident.affected_locations.add(location)
    incident.risks.add(risk)
    record_change(risk, None, organization=organization, actor=user, source='SYSTEM')
    record_change(incident, None, organization=organization, actor=user, source='SYSTEM')
    record_assessment(incident, user, source='SYSTEM')
    report = IncidentReport.objects.create(incident=incident, created_by=user, report_type='INITIAL',
        additional_information=label('LOGISTIK EXKLUSIV - Entwurf nur fuer Zugriffstest, keine Meldeentscheidung.'))
    record_change(report, None, organization=organization, actor=user, source='SYSTEM')
