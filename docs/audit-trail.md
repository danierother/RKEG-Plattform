# Audit-Trail

## Zweck und Geltungsbereich

Die App `audit` liefert eine fachlich nachvollziehbare Aenderungshistorie ab ihrer
Einfuehrung. Sie ist anwendungsseitig unveraenderlich, aber **keine zertifizierte
Revisionssicherheit**, keine digitale Signatur und kein externes Archiv.
Bestehende Datensaetze erhalten keine erfundene rueckwirkende Historie.

`AuditEvent` speichert Organisation, optionalen Actor, serverseitigen Zeitpunkt,
Aktion, Modellkennung, Objekt-ID und -bezeichnung, optionalen Feldnamen,
alte/neue Werte, Zusammenfassung, Quelle und Metadaten. IDs und Bezeichnungen
bleiben auch nach einer erlaubten Objektloeschung erhalten. JSON-Werte behalten
Zahlen, Wahrheitswerte und Listen; Datum, Zeit und Dauer werden serialisiert.

## Auditierte Objekte und Schreibpfade

- Risk, RiskControl, RiskMeasure
- CriticalService, Location, ServiceDependency
- Incident, IncidentEvent, IncidentAction
- IncidentReport, IncidentRKEGAssessment
- Zusaetzlich IncidentServiceImpact fuer dienstbezogene RKEG-Pruefdaten
- Organization: ausschliesslich die drei RKEG-Einstellungsfelder

Die explizite Feld-Allowlist liegt in `audit/services.py`. Sie umfasst insbesondere
Brutto-/Restrisikowerte und berechnete Klassen, Behandlungsstrategie, Wirksamkeit,
Status, Severity, Reportingstatus, Uebermittlungszeitpunkt und RKEG-Zuordnung.
M2M-Zuordnungen werden nach `save_m2m()` als sortierte Listen organisationsgleicher
IDs erfasst. Die Quelle ist WEB, ADMIN, SYSTEM, MIGRATION oder OTHER.

Normale Web-Formulare rufen `AuditFormMixin` auf. Die Organisations-RKEG-Ansicht
verwendet `audited_change` direkt. Die zentrale Funktion `record_assessment`
schreibt ASSESSMENT und ggf. MANUAL_OVERRIDE innerhalb derselben Transaktion
wie die unveraenderlichen Assessment-Datensaetze. Ein ungueltiger Override rollt
auch den automatischen Ausgangseintrag und dessen Audit-Eintrag zurueck.

Schreibbare Risk-/RiskControl-/RiskMeasure- und Organization-Admin-Pfade verwenden
dieselbe Schicht mit Quelle ADMIN. Deren erlaubte Fachloeschungen werden mit
`audited_delete` inklusive auditierter Kaskadenobjekte protokolliert. Die bereits
lesenden Services-/Incident-Admin-Klassen bleiben lesend. Organisationen werden
nicht ueber den Admin geloescht, damit die mandantenbezogene Historie erhalten
bleibt. Assessment-Historien und dokumentierte externe Meldungen sind auch fuer
den zentralen Loeschhelfer gesperrt.

## Aktionen und Werte

CREATE speichert den freigegebenen Anfangszustand. UPDATE speichert je geaendertem
Feld den alten und neuen Wert. Statusfelder erzeugen STATUS_CHANGE. Eine UUID in
`metadata.change_id` verbindet Feldereignisse desselben Speichervorgangs.
Ein Speichern ohne fachliche Aenderung erzeugt keinen Eintrag; `updated_at`
allein zaehlt nicht als fachaendernde Aktion.

IncidentReport-Erstellung verwendet REPORT_CREATED. Beim erstmaligen Wechsel zu
MARKED_AS_SUBMITTED entsteht zusaetzlich REPORT_MARKED_SUBMITTED, auch wenn eine
Meldung bereits bei Erstellung als uebermittelt dokumentiert wird. Die konkreten
Status-/Zeitpunkt-Aenderungen bleiben ebenfalls nachvollziehbar.
ASSESSMENT und MANUAL_OVERRIDE bewahren das zugrunde liegende Ergebnis, den
Regelstand, Eingabesnapshot und die Begruendung. DELETE bewahrt den Endzustand.
OTHER ist fuer kuenftige explizite Ereignisse reserviert.

## Actor, Organisation und Transaktionen

WEB bezieht Actor und Organisation aus dem serverseitigen Request-Kontext,
niemals aus POST-Feldern. Der Helper prueft aktive Schreibmitgliedschaft. ADMIN
setzt einen aktiven Superuser voraus. SYSTEM/MIGRATION sind ausschliesslich fuer
vertrauenswuerdige Backend-Aufrufer gedacht; dort kann der Actor fehlen.

`audited_change` liest den vorherigen Datenbankzustand (nicht die bereits durch
ModelForm veraenderte Instanz), prueft die Organisation und umfasst Speichern,
M2M-Aenderungen und Audit in einer Transaktion. Scheitert Audit, wird die
Fachaenderung nicht als erfolgreich gespeichert. `select_for_update` dient auf
unterstuetzenden Datenbanken der Zeilensperre; SQLite bietet keine gleichwertige
Zeilensperre. Konflikte und die SQLite-Schreibsperre sind kein Ersatz fuer eine
spaetere fachliche Versions-/Konfliktpruefung.

Systemjobs muessen explizit `audited_change`, `record_change` innerhalb ihrer
Transaktion bzw. `audited_delete` verwenden. Reine ORM-Aufrufe ausserhalb dieser
Grenzen werden absichtlich NICHT durch globale Signale automatisch erfasst.

## Anzeige und Datenschutz

`/audit/` erlaubt Lesen fuer alle aktiven Mitgliedsrollen einschliesslich VIEWER.
Suche: Objektbezeichnung/Aenderungsbeschreibung. Filter: Von/Bis inklusiv in
Projektzeitzone, Benutzer, Objekttyp, Aktion. Die Benutzerwahl enthaelt nur Actors
aus Audit-Eintraegen der aktiven Organisation. Ungueltige Filter liefern keine
Datensaetze. Listen sind paginiert (50 Eintraege); die Detailseiten von Risk,
CriticalService und Incident zeigen die letzten 20 Eintraege des jeweiligen
Objekts, stets organisationsgefiltert.

AuditEvents haben keine normalen Create-/Edit-/Delete-Views. Im Admin sind sie
nur fuer Systemadministratoren lesbar. Modell-save/delete blockieren Aenderungen
an vorhandenen Eintraegen. Beim Loeschen eines Benutzers darf dessen Actor-FK
aus Datenschutzgruenden NULL werden; die Fachdatenhistorie bleibt bestehen.

Es werden keine Passwoerter, Tokens, Sessiondaten, Cookies, Request-Bodies oder
beliebige User-Model-Felder protokolliert. Unerwartete POST-Felder werden ignoriert.
Die Allowlist enthaelt notwendige fachliche Freitexte. Diese duerfen bereits bei
der Eingabe keine Secrets enthalten; eine automatische Erkennung aller in
Freitext versteckten Geheimnisse wird nicht behauptet. Auditdaten koennen
personenbezogene und vertrauliche Fachdaten enthalten: Berechtigungen,
Aufbewahrungs-/Loeschkonzept und Backups sind organisatorisch festzulegen.

## Grenzen und Migration

`audit/0001_initial` erstellt ausschliesslich die neue Tabelle mit Indizes fuer
Organisation/Zeitpunkt und Organisation/Objekt. Bestehende Fachmodelle und Daten
werden nicht migriert oder umgedeutet.

Direkte SQL-Zugriffe, QuerySet.update/delete, bulk-Operationen und privilegierte
Datenbankadministration koennen die Modell-/Helper-Grenzen umgehen. Es gibt keine
externe unveraenderliche Log-Datenbank und keine kryptografische Verkettung.
Keine Aussage ueber vollstaendige historische Aktivitaeten vor der Einfuehrung.
