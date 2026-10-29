# Demo und Integrationstests fuer Prototyp v0.1

## Zweck und Sicherheit

`seed_demo_data` legt ausschliesslich fiktive **DEMO / TESTDATEN** an.
Die Energieorganisation heisst `Alpen Energie Versorgung GmbH`, der isolierte
zweite Mandant `Test Logistik GmbH`. Die Kennzeichnung steht in `legal_name`,
Benutzernamen/-profilen und Beschreibungen bzw. Titeln. Bescheidreferenzen,
Lieferanten, Standorte und Auswirkungen sind erfunden. Keine echten Adressen
oder personenbezogenen Kontaktdaten werden verwendet.

Es werden keine Modelle, Migrationen, rechtlichen Regeln oder Fachfunktionen
geaendert. Die bestehenden Hilfsfunktionen erzeugen sechs Assessments und eine
kleine echte Audit-Historie. Kein Assessment oder AuditEvent wird direkt
nachgebildet oder rueckdatiert. Meldungen bleiben interne Entwuerfe.

## Laden

Im Projektverzeichnis mit aktivierter `.venv`, alternativ `python` durch
`.venv/bin/python` ersetzen. Passwort verdeckt in Bash einlesen:

```bash
read -r -s -p 'Temporaeres Demo-Passwort: ' DEMO_PASSWORD
printf '\n'
export DEMO_PASSWORD
python manage.py seed_demo_data
unset DEMO_PASSWORD
python manage.py runserver 127.0.0.1:8000
```

Ein bereits belegter Port muss durch einen freien Port ersetzt werden. Das
Passwort wird weder ausgegeben noch im Quellcode gespeichert; Django speichert
nur den Passwort-Hash. Ohne nichtleeres `DEMO_PASSWORD` bricht der Command ab.
Alle fuenf neu angelegten Benutzer erhalten das eingegebene Passwort.
Keine Benutzer erhalten Django-Staff- oder Superuserrechte.

| Benutzer | Organisation | Rolle |
| --- | --- | --- |
| demo_admin | Energie | ADMIN |
| demo_resilience | Energie | RESILIENCE_MANAGER |
| demo_risk | Energie | RISK_MANAGER |
| demo_viewer | Energie | VIEWER |
| demo_logistics | Logistik | ADMIN |

Die komplette Anlage ist transaktional. Ein Fehler rollt alle neuen Daten
zurueck. Vorhandene gleichnamige Organisationen oder Benutzer werden nicht
uebernommen: Ohne eindeutige Demo-Zuordnung bricht der Command ab.

Bei erneutem Aufruf mit vollstaendig erkanntem Demo-Bestand entstehen keine
Duplikate; Daten, Passwoerter und Zeitpunkte bleiben unveraendert. Bearbeitungen
werden nicht zurueckgesetzt. Fehlende Teildaten werden nicht automatisch
repariert. Die Erkennung ist eine Versions-/Zuordnungs- und Mindestmengenpruefung,
kein Integritaetsabgleich jedes einzelnen Datensatzes. Keine vollstaendige
Wiederherstellung nach manuellen Eingriffen versprochen.

Zum Aendern eines lokalen Demo-Passworts gezielt beispielsweise
`python manage.py changepassword demo_admin` verwenden. Erneutes Seeden rotiert
keine Passwoerter. `clear_demo_data` existiert bewusst nicht: Nach manueller
Weiterverwendung koennten kaskadierende Loeschungen auch neue Benutzerdaten
treffen. Die Demo nicht in einer produktiven Umgebung laden.

## Umfang nach erstmaligem Laden

| Datensatz | Energie | Logistik | Gesamt |
| --- | ---: | ---: | ---: |
| Organisationen | 1 | 1 | 2 |
| Benutzer | 4 | 1 | 5 |
| Standorte | 5 | 1 | 6 |
| Dienstleistungen | 3 | 1 | 4 |
| Abhaengigkeiten | 7 | 0 | 7 |
| Risiken | 10 | 1 | 11 |
| Kontrollen | 8 | 0 | 8 |
| Risikomassnahmen | 8 | 0 | 8 |
| Vorfaelle | 5 | 1 | 6 |
| Chronologieeintraege | 12 | 0 | 12 |
| Vorfallmassnahmen | 5 | 0 | 5 |
| Assessments | 5 | 1 | 6 |
| Meldungsentwuerfe | 1 | 1 | 2 |
| AuditEvents | 11 | 4 | 15 |

Die Energie-Demo hat drei kritische Bruttorisiken, vier hohe Restrisiken und
zwei niedrige Restrisiken. Zwei noch nicht umgesetzte Risikomassnahmen haben
bereits beim Laden ein vergangenes Faelligkeitsdatum. Vier Abhaengigkeiten
sind Single Points of Failure, drei haben keine Ausweichloesung.

Die Dienstleistungen verwenden `E_SUPPLY` und `E_DISTRIBUTION` aus dem
vorhandenen Regelkatalog. Die Netzleitstelle ist als Steuerungsfunktion des
fiktiven Verteilernetzdienstes zugeordnet, nicht als neue gesetzliche Kategorie.
Der Logistikdienst nutzt `FOOD_LOGISTICS`; dessen Organisation ist nicht als
RKEG-klassifiziert markiert. Diese Zuordnungen sind reine Testannahmen.

## RKEG-Szenarien der bestehenden Engine

| Titel-Praefix | Tatsachen | Erwartetes Engine-Ergebnis |
| --- | --- | --- |
| A - Ausfall eines Umspannwerks | Beendet, 100.000 Zaehlpunkte mal 3 Stunden = 300.000 | REPORTABLE |
| B - Cybervorfall | Beendet, 100.000 Zaehlpunkte mal 2,5 Stunden = exakt 250.000 | BELOW_THRESHOLD |
| C - Telekommunikationsausfall | Beendet, Zaehlpunktzahl fehlt | INSUFFICIENT_DATA |
| D - Kleine Stoerung der Fernwirktechnik | Laufend, Qualifikation als ungeplant nicht bestaetigt | MANUAL_REVIEW |
| E - Kurze Unterbrechung der Ersatzversorgung | Beendet, 100 Zaehlpunkte mal 0,25 Stunden = 25 | BELOW_THRESHOLD |

Bei A liegt die dokumentierte Awareness nach der Schwellenueberschreitung.
Die bestehende Fristfunktion berechnet daraus die Erstmeldefrist, Awareness
plus 24 Stunden. Ein Erstmeldungsentwurf und ein automatisches Assessment
sind vorhanden. B demonstriert bewusst die strikte Mehr-als-Grenze. E ist ein
zusaetzlicher abgeschlossener kleiner Vorfall; D demonstriert die manuelle
Pruefung und bleibt wegen der fehlenden qualitativen Bestaetigung manuell.
Die Reporting-Statusfelder dienen dem Bearbeitungsstand und muessen nicht mit
dem automatisch berechneten Engine-Ergebnis identisch sein.

Alle Zeitpunkte entstehen relativ zum ersten Laden. Abgeschlossene Intervalle
werden danach nicht verschoben. Die Fristanzeige und Faelligkeitsanzeigen
altern mit der Zeit; die Erstmeldefrist kann spaeter ueberfaellig werden.
Die Demo setzt eine Systemzeit mindestens zwei Tage nach dem Inkrafttreten
der vorhandenen Regelversion voraus. Es findet keine neue Rechtspruefung statt.

## Automatisierte Pruefung

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test core.test_demo_e2e
python manage.py test
```

Die neuen Tests laufen in einer separaten Django-Testdatenbank. Sie pruefen
den Command, Idempotenz inklusive aller Tabellen/Passwort-Hashes, Kollisionen,
Rollback, Bestandserhalt, Demo-Mengen und die vorhandene Bewertungsengine.
Die HTTP-Ablauftests melden sich mit echten Django-Login-POSTs an und besuchen
Dashboard, Dienstleistungen, Risiken, Kontrollen, Massnahmen, Vorfaelle,
Chronologie, Assessments, Entwuerfe, Audit und Berichte. Viewer-Schreibverbote,
fremde URLs, manipulierte Beziehungen, CSV-Ausgaben, Druckansichten und ein
Login/Logout mit aktivierter CSRF-Pruefung sind enthalten.

Dies sind integrations-/E2E-nahe Django-Client-Tests, keine Browserautomation.
CSS, responsive Darstellung, echte Downloads, Druckdialog und erzeugte PDF
muessen weiterhin manuell geprueft werden. Bestehende Fachtests bleiben erhalten.

## Manueller Demo-Check

Datum: __________  Tester: __________  Commit/Branch: __________

Basis-URL: `http://127.0.0.1:8000` (Port gegebenenfalls anpassen).
IDs werden beim Laden vergeben: `<risk>`, `<service>`, `<incident>` und
`<report>` jeweils aus den Listen/Detail-Links uebernehmen, nicht fest annehmen.
Als Referenz Risiko "Grossflaechiger Stromausfall" (mit Umlaut im Titel),
Elektrizitaetsversorgung und Vorfall A verwenden. Formulare und Logout normal
ueber die Oberflaeche absenden, damit CSRF-Token mitgesendet werden.

| Nr. | Aktion / URL | Erwartetes Ergebnis | Pass/Fail / Notiz |
| --- | --- | --- | --- |
| 1 | Command wie oben zweimal ausfuehren; URL: entfällt | Erste Anlage mit Mengen oben; zweiter Aufruf ohne neue Daten/Passwoerter. | __________ |
| 2 | `/login/`, demo_admin | Anmeldung erfolgreich, aktive Energieorganisation sichtbar; keine Admin-Superuserrechte erforderlich. | __________ |
| 3 | `/dashboard/` | 10 Risiken, 3 aktive Dienstleistungen, 4 SPOF, 1 kritischer Vorfall; keine Logistikdaten. | __________ |
| 4 | `/risks/`, danach `/risks/<risk>/` | Brutto/Restrisiko verschieden; Beispiel Stromausfall 25/Kritisch und 16/Hoch; Kontrolle und Massnahme erreichbar. | __________ |
| 5 | `/risks/matrix/?type=gross`, danach `?type=residual` | Eindeutige Moduskennzeichnung, unterschiedliche Verteilung, nur Energie-Risiken. | __________ |
| 6 | `/services/<service>/` | Owner, RTO <= MTD, Standorte, Abhaengigkeiten und verknuepfte Risiken sichtbar. | __________ |
| 7 | `/incidents/`, `/incidents/<incident>/` fuer A und B | Beschreibung, Service/Standort, sechs geordnete Chronologieeintraege je Vorfall sowie Sofortmassnahmen. | __________ |
| 8 | `/incidents/<incident>/`, Assessment-Link und `/incidents/<incident>/reports/<report>/` | A REPORTABLE mit Awareness, Frist und Entwurf; B BELOW_THRESHOLD, C INSUFFICIENT_DATA, D MANUAL_REVIEW, E BELOW_THRESHOLD. | __________ |
| 9 | `/audit/` | Nachvollziehbare System-Aktionen mit Demo-Akteuren, keine Logistikereignisse. | __________ |
| 10 | `/reports/management/` sowie `/reports/` | Sinnvoll gefuellte Kennzahlen und alle sechs Berichte; keine Logistikdaten. | __________ |
| 11 | `/reports/risks/?format=csv`, analog actions/services/incidents/rkeg | UTF-8-CSV mit Semikolon; 10/13/3/5/5 Datenzeilen, keine fremden Daten. | __________ |
| 12 | `/reports/management/print/`, `/reports/risks/print/`, Browser Drucken / als PDF speichern | Lesbare Druckansicht mit Metadaten; keine abgeschnittenen Spalten, PDF im Browser erzeugbar. Desktop und schmale Ansicht pruefen. | __________ |
| 13 | Logout per Navigationsformular, `/login/` als demo_viewer | Dashboard, Risiko, Vorfall, Audit und Berichte lesbar. | __________ |
| 14 | `/risks/new/`, `/risks/<risk>/edit/`, Kontrolle/Massnahme/Vorfall/Meldung bearbeiten, Assessment ausloesen | GET-Schreibseiten gesperrt bzw. keine Schreibfunktion; manipulierter POST mit gueltigem CSRF wird serverseitig abgewiesen. Daten unveraendert. | __________ |
| 15 | Separates Browserprofil als demo_logistics: eigene IDs notieren; diese `/risks/<id>/`, `/services/<id>/`, `/incidents/<id>/` und Meldungs-URLs im Energieprofil aufrufen | Fremde Objekte 404/403; Listen, Dashboard, Audit, Reports, CSV und Druckansichten bleiben mandantengetrennt. Gegenrichtung ebenso pruefen. | __________ |

Fehler / Beobachtungen: ________________________________________________

Gesamtergebnis: __________  Offene Punkte: _____________________________
