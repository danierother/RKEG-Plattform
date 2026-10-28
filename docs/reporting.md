# Management- und Compliance-Berichte

## Uebersicht

`/reports/` buendelt sechs lesende, mandantenbezogene Berichte:

| URL | Inhalt |
| --- | --- |
| `/reports/management/` | Konsolidierte Kennzahlen, Top 10 Restrisiken, ueberfaellige Massnahmen, offene kritische Vorfaelle, kritische SPOFs |
| `/reports/risks/` | Risiken, Dienste, Brutto/Restrisiko, Behandlung, offene Massnahmen und deren Verantwortliche |
| `/reports/actions/` | RiskMeasure und IncidentAction mit Faelligkeit und Ueberfaelligkeit |
| `/reports/services/` | Dienstleistungen, MTD/RTO, Standorte, verknuepfte Risiken/Vorfaelle, Abhaengigkeiten/SPOFs |
| `/reports/incidents/` | Vorfaelle, Services, Verantwortliche und aktuelles automatisches RKEG-Ergebnis |
| `/reports/rkeg/` | Interne Meldeuebersicht je Vorfall und wesentlichem Dienst mit Regeln, Rechenwerten, Fristen und aktueller manueller Uebersteuerung |

Jeder HTML-/Druckbericht nennt aktive Organisation, Berichtstyp, serverseitigen
Erstellungszeitpunkt, aufrufenden Benutzer und aktive Filter. Kennzeichnung:
"Prototyp / interne Dokumentation". Berichte sind aktuelle Lesesichten, keine
persistierten, signierten Berichtssnapshots. Ein erneuter Abruf kann aufgrund
zwischenzeitlicher Aenderungen oder verstrichener Zeit andere Werte zeigen.

## Datenquellen und Definitionen

`core/reporting.py` liefert dieselben Tabellen fuer HTML, CSV und Druck. Die
bestehende Risikobewertungslogik bleibt unveraendert. Risikoverantwortliche sind
die Verantwortlichen der noch nicht umgesetzten RiskMeasures; das Risk-Modell
selbst hat kein eigenes Owner-Feld. Nicht zugewiesene Verantwortlichkeiten bleiben
sichtbar. Brutto- und Restrisikoklassen werden getrennt gezaehlt.

RiskMeasures sind offen, solange Status != IMPLEMENTED. Ueberfaellig: offener
Datensatz mit Faelligkeit vor dem heutigen lokalen Datum oder ausdruecklicher
Status OVERDUE. IncidentActions sind offen, solange weder DONE noch CANCELLED;
ueberfaellig nur mit Faelligkeit vor heute. Heute faellige Massnahmen sind noch
nicht ueberfaellig. Fehlendes Datum erzeugt keine geratene Frist.

Aktive Dienstleistungen haben Status ACTIVE. Kritische Dienstleistungen und
Abhaengigkeiten haben Kritikalitaet 4/5 (unabhaengig vom Aktivstatus). SPOFs sind
alle entsprechend markierten Abhaengigkeiten; die kompakte SPOF-Tabelle zeigt nur
Kritikalitaet 4/5. Standort-/Risiko-/Vorfallzaehlungen verwenden nur
organisationsgleiche Beziehungen, ohne Vervielfachung durch JOINs.

Offene Vorfaelle: NEW, ACTIVE, CONTAINED. Kritisch: Severity 5.
Die bestehende zentrale RKEG-Engine berechnet Einzelergebnisse und Fristen.
Es wird keine neue gesetzliche Bewertung eingefuehrt. Dokumentierte positive
Bewertungen oder eine externe Erstmeldung halten Meldeaufgaben konservativ
sichtbar, auch nach spaeteren Datenkorrekturen. Die Managementkennzahl benennt
deshalb sowohl meldepflichtige Vorfaelle als auch dokumentierte Meldeaufgaben.
Manuelle Pruefungen umfassen unvollstaendige/offene Bewertungen sowie fehlende
Kenntniszeiten bei Meldeaufgaben; aktuelle begruendete manuelle Bewertungen werden
wie im bestehenden Dashboard beruecksichtigt.

Im RKEG-Bericht werden automatisch berechnetes Gesamt- und Einzelergebnis klar
von der manuellen Uebersteuerung getrennt. Bei mehreren Diensten gibt es mehrere
Zeilen fuer denselben Vorfall. Unbekannte Werte bleiben unbekannt. Ohne Service
wird eine Zeile mit fehlender Zuordnung ausgegeben. Keine Behoerdenuebermittlung.

## Filter

- Risiken: Bruttoklasse, Restrisikoklasse, Status, kritische Dienstleistung.
- Massnahmen: Typ, jeweiliger Modellstatus, Verantwortlicher, ueberfaellig Ja/Nein.
- Vorfaelle und RKEG: Status, Severity, Vorfallart, automatisches RKEG-Ergebnis.
- Zeitraeume Von/Bis (inklusive): Risiken/Services nach letzter Aenderung,
  Massnahmen nach Faelligkeitsdatum, Vorfaelle/RKEG nach Ereignisdatum.
- Management: aktuelle Gesamtsicht ohne Zeitraumfilter.

Alle Filter sind GET-Parameter. Auswahllisten fuer Dienste und Verantwortliche
sind mandantenbezogen. Verantwortliche beruecksichtigen auch bereits zugewiesene
Personen, damit historische Massnahmen filterbar bleiben. Ungueltige Werte und
umgekehrte Zeitraeume erzeugen Formularfehler und **keine** Berichtsdaten;
CSV antwortet dann mit HTTP 400. Freie organization-/object_id-Parameter erweitern
niemals den serverseitig festgelegten Datenbereich.

## CSV

Die fuenf tabellarischen Berichte exportieren mit `?format=csv` alle gefilterten
Zeilen, unabhaengig von der HTML-Seitennummer. HTML zeigt 50 Zeilen pro Seite.
UTF-8 mit BOM, Semikolon als Trennzeichen und korrektes csv.writer-Quoting
unterstuetzen Tabellenkalkulationen und mehrzeilige Texte.

Jede CSV-Datenzeile enthaelt Organisation, Berichtstyp, Erstellungszeitpunkt,
Benutzer und Filter vor den Fachspalten. Leere Ergebnismengen enthalten nur die
Spaltenueberschriften, keine erfundene Datenzeile. Potenzielle Formelanfaenge
(`=`, `+`, `-`, `@` sowie fuehrende Tab-/Zeilenzeichen) werden mit einem Apostroph
neutralisiert. Das ist beabsichtigter Exportschutz, keine Aenderung der Quelldaten.

## Druck und PDF

Alle sechs Berichte bieten `/print/`, z.B. `/reports/management/print/`.
Die Druckansicht behaelt aktive Filter bei und umfasst alle Zeilen. Navigation,
Filter und Bedienaktionen werden beim Drucken ausgeblendet. Druck-CSS verwendet
A4-Hochformat fuer Management, A4-Querformat fuer breite Fachberichte, wiederholte
Tabellenkoepfe und nach Moeglichkeit zusammengehaltene Zeilen. Sehr lange einzelne
Texte koennen browserbedingt auf mehrere Seiten umbrechen.

**PDF-Status:** Im vorhandenen Environment sind nur Django, asgiref, sqlparse und
pip installiert. Keine geeignete serverseitige PDF-Bibliothek ist vorhanden;
es wurde keine installiert. Bereits jetzt kann der Browser ueber
**Drucken -> Als PDF sichern** PDF-Dateien aus den Druckansichten erzeugen.
Echte serverseitige PDF-Erzeugung, reproduzierbare Seitengestaltung und ein
abgestimmter Renderer sind ein spaeterer technischer Schritt. Die aktuelle
Implementation behauptet keine serverseitig erzeugte PDF-Datei.

## Mandantentrennung und Performance

Alle Berichte verwenden OrganizationContextMixin mit aktiver Membership und
Login-Pflicht. ADMIN, RESILIENCE_MANAGER, RISK_MANAGER, EDITOR und VIEWER duerfen
lesen/exportieren. Keine schreibenden Berichts-Endpunkte. Objekt- und
Beziehungsabfragen sind jeweils nach aktiver Organisation gefiltert, auch bei
manipulierten Queryparametern und bereits inkonsistenten M2M-/Kindbeziehungen.

select_related und gefilterte Prefetch-Abfragen verhindern offensichtliche
N+1-Muster. Die RKEG-Engine kann vorab geladene Dienste, Pruefdaten, Meldungen und
Assessments verwenden; fuer eine Vorfallliste sind konstant fuenf Abfragen
ausreichend, unabhaengig von der Anzahl der Vorfaelle. Die fachliche Engine bleibt
auch ohne Vorabladen nutzbar. Ein Bericht verwendet einen gemeinsamen
Berechnungszeitpunkt fuer die zeitabhaengigen Kennzahlen.

Exports, Druck und Management werden derzeit im Speicher aufgebaut. Sehr grosse
Datenmengen koennen spaeter Streaming, Hintergrundauftraege oder materialisierte
Berichtssnapshots erfordern. Keine solche Infrastruktur wird vorweggenommen.
Vertrauliche heruntergeladene CSV-/PDF-Dateien unterliegen anschliessend den
organisatorischen Zugriffs- und Aufbewahrungsregeln ausserhalb der Plattform.
