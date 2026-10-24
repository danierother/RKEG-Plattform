# Vorfallmanagement

Das Modul erfasst, bewertet und dokumentiert Vorfaelle einer Organisation.
Es bereitet eine spaetere Meldepflichtpruefung vor. Gesetzliche Meldefristen,
konkrete RKEG-Meldekriterien, automatische Meldeentscheidungen, Meldungen an
Behoerden und Benachrichtigungen sind NICHT implementiert.

## Modelle

- Incident: Beschreibung, Ereignis- und Erkennungszeit, Auswirkungen,
  betroffener Dienst/Standort, Status, Schweregrad, manuelle Meldepruefung und
  optional verknuepfte Risiken derselben Organisation.
- IncidentEvent: manuell erfasster Chronologieeintrag mit Ereigniszeit,
  Eintragsart, Beschreibung, Ersteller und Erfassungszeit. Anzeige aufsteigend
  nach event_time, bei Gleichstand nach ID. Nachtraeglich erfasste Eintraege
  sind erlaubt. Statusaenderungen erzeugen derzeit keinen automatischen Eintrag.
  Es gibt keine Bearbeitungsfunktion fuer Eintraege und keine Zusicherung eines
  revisionssicheren/aenderungsfesten Audit-Logs.
- IncidentAction: Sofortmassnahme mit Titel, Beschreibung, Status, optionalem
  Verantwortlichem, Faelligkeitsdatum und Abschlusszeitpunkt. Alle Termine
  werden manuell gesetzt; sie sind keine gesetzlichen Meldefristen.

## Status und Bewertung

Incident: NEW (Neu), ACTIVE (In Bearbeitung), CONTAINED (Eingedaemmt),
RESOLVED (Behoben), CLOSED (Abgeschlossen). Wechsel und Wiedereroeffnung sind
manuell moeglich. Das Dashboard zaehlt NEW, ACTIVE und CONTAINED als offen.
"Kritisch" zaehlt alle Vorfaelle mit Severity 5, unabhaengig vom Status.
"Meldepflicht in Pruefung" zaehlt UNDER_REVIEW, unabhaengig vom Status.
Die letzten fuenf Vorfaelle werden nach Erfassungszeit angezeigt.

Severity: 1 Gering, 2 Moderat, 3 Erheblich, 4 Schwer, 5 Kritisch.
Dies ist eine operative Einschaetzung, keine gesetzliche Einstufung.

suspected_reportable dokumentiert eine Vermutung als Ja/Nein.
reporting_status ist eine gesonderte manuelle Einschaetzung:
NOT_ASSESSED, UNDER_REVIEW, REPORTABLE, NOT_REPORTABLE, REPORTED.
Weder Severity noch die Vermutung aendern diesen Status automatisch.
REPORTED dokumentiert eine extern bereits erfolgte Meldung; das System
versendet nichts. Es werden keine rechtlichen Kriterien unterstellt.

IncidentAction: OPEN, IN_PROGRESS, DONE, CANCELLED. completed_at ist optional,
aber nur bei DONE erlaubt. Bei einer Wiedereroeffnung muss ein vorhandener
Abschlusszeitpunkt entfernt werden. Der Status allein setzt keinen Zeitpunkt.

Ereignis- und Erkennungszeit sind Pflichtangaben. detected_at muss groesser
oder gleich occurred_at sein. Speicherung erfolgt mit Zeitzonenunterstuetzung;
Eingabe und Darstellung verwenden die konfigurierte Zeitzone Europe/Vienna.

## Mandantentrennung und Rechte

Alle Seiten verlangen eine Anmeldung und aktive Membership. Jede Abfrage
wird nach der aktiven Organisation gefiltert, einschliesslich Kindobjekten,
Risikoauswahl, Chronologie und Dashboard. ADMIN, RESILIENCE_MANAGER,
RISK_MANAGER und EDITOR duerfen schreiben. VIEWER darf ausschliesslich lesen.
Ersteller und Organisation werden serverseitig gesetzt. Ein signierter
Formularkontext verhindert versehentliches Speichern in einer anderen
Organisation nach einem Wechsel in einem zweiten Browser-Tab.

Verantwortliche muessen aktive Benutzer mit aktiver Membership derselben
Organisation sein. Spaeter entzogene Mitgliedschaften loeschen historische
Zuweisungen nicht; beim naechsten Speichern muss neu zugewiesen oder geloescht
werden. Die Organisation eines gespeicherten Vorfalls kann nicht wechseln.

Risk-Verknuepfungen werden im ModelForm und durch m2m_changed fuer add/set in
beiden Richtungen validiert. Verknuepfte Risiken koennen nicht in eine fremde
Organisation verschoben werden. Direkte SQL-Schreibzugriffe, QuerySet.update,
bulk_create oder direktes Schreiben in die automatisch erzeugte M2M-Tabelle
umgehen Django-Validierung und duerfen nicht fuer solche Zuordnungen verwendet
werden. Normale Datenbank-Constraints schuetzen Zeitreihenfolge und Severity.

Der zentrale Django Admin bietet aktiven Superusern eine lesende Ansicht;
Schreiboperationen laufen ueber die organisationsgebundenen Anwendungsformulare.
Auch Superuser benoetigen dort eine aktive Membership.

## Migration und Schnittstellen

incidents/0001_initial erstellt die drei Modelle und die M2M-Tabelle. Bestehende
Risiken, Kontrollen, Massnahmen und Organisationen bleiben unveraendert.
Es gibt keine Datenmigration und keine automatisch angelegten Vorfaelle.
Die Migration haengt vom bestehenden Risk-Modell und dem Custom User ab.

URLs: /incidents/, /incidents/new/, /incidents/<id>/,
/incidents/<id>/edit/, /incidents/<id>/events/new/,
/incidents/<id>/actions/new/, /incidents/<id>/actions/<action_id>/edit/.

Suche (q), Filter (status, severity, incident_type, reporting_status) und
Sortierung (sort) erfolgen per GET. Unbekannte Sortierungen fallen auf newest
zurueck. Ungueltige Filter zeigen Fehler, waehrend andere gueltige Filter
weiter angewendet werden. Beim Blaettern bleiben die GET-Parameter erhalten.
