# Kritische Dienstleistungen

CriticalService beschreibt die von einer Organisation erbrachten
Dienstleistungen. Location beschreibt ihre Standorte. ServiceDependency
dokumentiert wesentliche Abhaengigkeiten einer Dienstleistung.

Die derzeitigen Kritikalitaets- und Prioritaetsskalen sind interne
Prototypmethoden und stellen keine automatische gesetzliche RKEG-Klassifizierung
dar. Es werden keine BIA, BCM-Automatik, Meldepflichten oder Fristen abgeleitet.

## Standorte und Dienstleistungen

Location enthaelt Name, optionale Beschreibung/Adressdaten, Standorttyp und
Aktivstatus. CriticalService enthaelt Beschreibung, optionalen Service Owner,
Status, Kritikalitaet, Recovery Priority, Wiederherstellungszeiten und Notizen.
Mehrere Standorte koennen einer Dienstleistung zugeordnet werden.
Inaktive Standorte/Dienstleistungen bleiben fuer historische Zuordnungen
auswaehlbar und werden als inaktiv angezeigt; es gibt keine Loeschfunktion.

Kritikalitaet: 1 Gering, 2 Mittel, 3 Hoch, 4 Sehr hoch, 5 Kritisch.
Recovery Priority: 1 Sehr hoch, 2 Hoch, 3 Mittel, 4 Niedrig, 5 Sehr niedrig.
Beide Skalen sind manuelle Einschaetzungen und unabhaengig voneinander.

## Wiederherstellung

MTD (Maximum Tolerable Downtime) beschreibt die maximal tolerierbare
Ausfallzeit; RTO (Recovery Time Objective) die angestrebte Wiederherstellungszeit.
Beide sind optionale Django DurationFields. Eingabe als HH:MM:SS oder
Tage HH:MM:SS, beispielsweise 04:00:00 oder 1 00:00:00. Leer bedeutet unbekannt,
0 bedeutet explizit keine tolerierte bzw. angestrebte Ausfallzeit.
Negative Dauern sind unzulaessig. Wenn beide gesetzt sind, muss RTO <= MTD
gelten. Formulare, Models und Datenbank-Constraints pruefen diese Regeln.
Es werden keine automatischen Wiederherstellungsplaene oder Termine erzeugt.

## Abhaengigkeiten

ServiceDependency gehoert zwingend zu einer Dienstleistung und uebernimmt deren
Organisation. Neben Typ und Kritikalitaet werden interne/externe Herkunft,
optionaler Lieferant und Notizen dokumentiert. Single Point of Failure bedeutet
eine als einzelnen Ausfallpunkt identifizierte Abhaengigkeit. Das separate
Feld contingency_available erfasst, ob eine Ausweichloesung vorhanden ist.
Beide Angaben werden manuell gesetzt und nicht automatisch gegeneinander
verrechnet. Kritikalitaet verwendet dieselbe interne 1-5-Skala wie Services.

## Risiko- und Vorfallbeziehungen

Risk.critical_services ist eine optionale ManyToMany-Beziehung.
Incident.affected_services und Incident.affected_locations sind zusaetzliche
optionale strukturierte Beziehungen. Die bisherigen Freitextfelder
Incident.affected_service und Incident.affected_location bleiben unveraendert
erhalten und sichtbar. Es gibt keine automatische Konvertierung oder
Synchronisierung zwischen Freitext und strukturierten Beziehungen.

## Mandantentrennung

Alle neuen Datensaetze gehoeren zu einer Organisation. Organisationswechsel
bestehender Standorte, Services und Abhaengigkeiten sind gesperrt. Verknuepfte
Risiken koennen nicht in eine fremde Organisation verschoben werden.
Organisationen werden in Formularen serverseitig gesetzt; fremde IDs werden
abgewiesen. Detailansichten und Relationszaehlungen filtern erneut nach aktiver
Organisation. Auch zusaetzliche aktive Memberships erlauben keinen Zugriff auf
Daten ausserhalb des aktuellen Organisationskontexts.

Service Owner muessen aktive Benutzer mit aktiver Membership derselben
Organisation sein. Spaeter entzogene Mitgliedschaften entfernen historische
Zuordnungen nicht; beim naechsten Speichern muss neu zugewiesen oder entfernt
werden. ADMIN, RESILIENCE_MANAGER, RISK_MANAGER und EDITOR duerfen schreiben,
VIEWER ausschliesslich lesen. Signierte Formularkontexte schuetzen vor einem
versehentlichen Organisationswechsel in einem zweiten Browser-Tab.

M2M-Zuordnungen werden im Formular und bei add()/set() in beiden Richtungen
mit m2m_changed validiert. Direkte SQL-Schreibzugriffe, bulk_create,
QuerySet.update und Schreiben in M2M-Zwischentabellen umgehen Model-/Signal-
Validierung und duerfen nicht fuer solche Zuordnungen verwendet werden.
Der zentrale Admin bietet Superusern lesenden Zugriff. Neue Zuordnungen werden
ueber die organisationsgebundenen Anwendungsformulare gepflegt; die neue
Risk-Relation ist auch im zentralen Risk-Admin schreibgeschuetzt.

## Dashboard

Aktive Services werden mit status=ACTIVE gezaehlt. Kritische Services und
Abhaengigkeiten haben Kritikalitaet 4 oder 5, unabhaengig vom Servicestatus.
Single Points of Failure zaehlt alle entsprechend markierten Abhaengigkeiten.
Die fuenf wichtigsten Services sind nach Kritikalitaet absteigend, Recovery
Priority aufsteigend und Name sortiert. Alle Zahlen sind organisationsbezogen.

## Migrationen und Bestandsschutz

services/0001_initial erstellt die drei neuen Tabellen sowie die
Service-Location-Verknuepfungstabelle. Die neuen Risk- und Incident-Migrationen
fuegen ausschliesslich optionale M2M-Beziehungen hinzu. Sie erstellen neue
Verknuepfungstabellen, aendern aber keine bisherigen Feldwerte oder Zeitstempel.
Bestehende Daten bleiben unveraendert; neue Zuordnungen sind initial leer.
Organization und User erhalten keine Schemaaenderungen. Vor Anwendung wird
die lokale SQLite-Datenbank gesichert und der Bestand danach verglichen.
