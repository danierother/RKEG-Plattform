# RKEG-Meldepruefung

## Rechtsquellen und Stand

Regelversion: `RKEV-2026-04-15/v1`, Quellenabgleich am 27.10.2026.

- [RKEG, BGBl. I Nr. 60/2025, § 17](https://www.ris.bka.gv.at/NormDokument.wxe?Abfrage=Bundesnormen&Gesetzesnummer=20012981&Paragraf=17): Meldungen und Meldeinformationen.
- [RKEG § 18 Abs. 3](https://www.ris.bka.gv.at/NormDokument.wxe?Abfrage=Bundesnormen&Gesetzesnummer=20012981&Paragraf=18): Sektorausnahmen.
- [Authentisch kundgemachte RKEV, BGBl. II Nr. 91/2026](https://www.ris.bka.gv.at/Dokumente/BgblAuth/BGBLA_2026_II_91/BGBLA_2026_II_91.html): Definitionen in § 2 und Vorfallschwellen in §§ 3-14. Kundmachung 14.04.2026, Inkrafttreten 15.04.2026 gemaess § 16.

Die Implementierung verwendet die Vorfallschwellen, NICHT die ebenfalls in der
RKEV enthaltenen Schwellen zur erstmaligen Einstufung kritischer Einrichtungen.
Marktanteile, Personalzahlen und Unternehmensgroesse werden nicht zur Einstufung
herangezogen. Interne Kritikalitaet und Recovery Priority bleiben unabhaengig.
Vor einem produktiven Einsatz sind die Bescheidzuordnung, Sachverhaltsqualifikation,
Fristbehandlung und der aktuelle Rechtsstand fachlich/rechtlich freizugeben.

## Datenmodell und Anwendbarkeit

`Organization.rkeg_classified` ist dreistufig: unbekannt (`NULL`), ausdruecklich
keine Einstufung dokumentiert (`False`), Einstufung dokumentiert (`True`).
Eine positive Angabe braucht fuer die automatische Pruefung eine Bescheidreferenz.
`rkeg_reporting_obligation_start_date` wird ausdruecklich eingetragen. Die Engine
berechnet dieses Datum NICHT aus einem Bescheiddatum. § 17 Abs. 1 nennt einen
Beginn nach zehn Monaten; dessen konkrete Anwendung bleibt ausserhalb der Engine.

`CriticalService.rkeg_sector`, `rkeg_subsector`, `rkeg_service_code` und
`rkeg_service_reference` bilden die dokumentierte Bescheidzuordnung ab. Codes
sind interne Plattformkennungen, kein behoerdliches Format. Das Formular leitet
den Teilsektor aus dem ausgewaehlten Dienst ab und prueft den Sektor. Unvollstaendige,
widerspruechliche oder unbekannte Zuordnungen liefern keine positive Entscheidung.

Incident-Pruefdaten sind optional und getrennt von bisherigen Angaben. Insbesondere
ist `rkeg_awareness_at` die Kenntnis vom MELDEPFLICHTIGEN Sicherheitsvorfall, nicht
automatisch `detected_at`. Die beiden Zeitpunkte werden niemals gleichgesetzt.
Der bestehende manuelle `reporting_status` wird weder migriert noch ueberschrieben.

Bei genau einem betroffenen Dienst koennen die Incident-Pruefdaten verwendet werden.
`IncidentServiceImpact` erlaubt dienstbezogene Daten und hat fuer diesen Dienst
Vorrang. Bei mehreren Diensten sind solche Einzelangaben erforderlich: Globale
Nutzerzahlen, Sonderkriterien und Stoerungsdauern werden nicht allen Diensten
zugerechnet. Fehlende Einzelangaben bleiben sichtbar. Nicht mehr zugeordnete
Dienst-Datensaetze werden nicht in der Pruefung verwendet.

`unplanned_confirmed` dokumentiert die ungeplante Stoerung gemaess § 2.
Fuer `RESTRICTED_AVAILABILITY` muss zusaetzlich
`significant_impairment_confirmed` dokumentiert sein. Das ist die fachliche
Bestaetigung der qualitativen Voraussetzungen nach § 2 Z 2, keine technische
Ableitung aus Dauer oder Severity. Ohne Bestaetigung: manuelle Pruefung.

## Implementierte Schwellen

Alle numerischen Vergleiche sind strikt **mehr als**, nicht groesser-gleich.
Im Katalog `incidents/rkeg_rules.py` hat jeder Dienst eine eigene Kennung,
Sektor, Teilsektor, Schwellentyp, Wert, Einheit, genaue Rechtsreferenz und
Inkrafttretensdatum. Die folgenden Dienstgruppen sind vollstaendig abgebildet:

| Sektor / Dienste | Schwelle | Rechtsstelle RKEV |
| --- | --- | --- |
| Stromversorgung; Stromverteilernetz | >250.000 Zaehlpunktstunden | § 3 Abs. 2 Z 1 lit. a |
| Stromuebertragungsnetz | >2 h | § 3 Abs. 2 Z 1 lit. b |
| Stromerzeugung | >4 h | § 3 Abs. 2 Z 1 lit. c |
| Nominierte Strommarktbetreiber | Kein Handelsergebnis fuer physische Erfuellung von Stromprodukten | § 3 Abs. 2 Z 1 lit. d |
| Laststeuerung | >24 h | § 3 Abs. 2 Z 1 lit. e |
| Stromaggregierung | >24 h | § 3 Abs. 2 Z 1 lit. f |
| Energiespeicherung | >12 h | § 3 Abs. 2 Z 1 lit. g |
| Fernwaerme / Fernkaelte | >250.000 Nutzerstunden | § 3 Abs. 2 Z 2 |
| Erdoelfernleitung, -produktion, -raffination/aufbereitung, -lagerung, Vorratsverwaltung | jeweils >24 h | § 3 Abs. 2 Z 3 |
| Erdgaslieferung; Erdgasspeicherung | >12 h | § 3 Abs. 2 Z 4 lit. a |
| Erdgasverteilung | >100.000 Zaehlpunktstunden | § 3 Abs. 2 Z 4 lit. b |
| Erdgasfernleitung, LNG, Gewinnung, Ankauf, Raffination/Aufbereitung | jeweils >24 h | § 3 Abs. 2 Z 4 lit. c |
| Wasserstofferzeugung, -speicherung, -fernleitung | jeweils >24 h | § 3 Abs. 2 Z 5 |
| Gewerbliche Luftverkehrsdienste; Flughafen/Flughafennetz | >12 h | § 4 Abs. 2 Z 1 lit. a |
| Flugverkehrskontrolle | >3 h | § 4 Abs. 2 Z 1 lit. b |
| Schienenpersonenverkehr | >4 h | § 4 Abs. 2 Z 2 lit. a |
| Schienengueterverkehr | >24 h | § 4 Abs. 2 Z 2 lit. a |
| Eisenbahninfrastruktur; Zugsteuerung/Signalgebung | >4 h | § 4 Abs. 2 Z 2 lit. b |
| Schienenverkehr-Serviceeinrichtungen | >24 h | § 4 Abs. 2 Z 2 lit. c |
| Binnen-/See-/Kuestenschifffahrt; Haefen; Schiffsverkehrsdienste | jeweils >24 h | § 4 Abs. 2 Z 3 |
| Strassenverkehrsmanagement; intelligente Verkehrsdienste | >4 h | § 4 Abs. 2 Z 4 |
| Oeffentlicher Personenverkehr | >4 h | § 4 Abs. 2 Z 5 |
| EU-Referenzlaboratorium | >72 h | § 7 Abs. 2 Z 1 |
| Arzneimittelforschung/-entwicklung | >48 h | § 7 Abs. 2 Z 2 |
| Pharmazeutische Grundstoffe/Zubereitungen; kritische Medizinprodukte; Arzneimittelvertrieb | jeweils >24 h | § 7 Abs. 2 Z 3 |
| Krankenanstalten nach § 8 Abs. 1 Z 1-4 | >8 h | § 8 Abs. 3 Z 1 |
| Leitstelle Notfallrettungstransporte nach § 8 Abs. 1 Z 5 | >6 h | § 8 Abs. 3 Z 2 |
| Trinkwasser | >600.000 Nutzerstunden | § 9 Abs. 2 |
| Abwasser | >24 h | § 10 Abs. 2 |
| Oeffentliche Verwaltung | >24 h | § 12 |
| Weltraum-Bodeninfrastruktur | >2 h | § 13 Abs. 2 |
| Industrielle Lebensmittelproduktion/-verarbeitung | >3 Tage (=72 h) | § 14 Abs. 2 Z 1 |
| Lebensmittellagerung/-logistik | >24 h | § 14 Abs. 2 Z 2 |
| Lebensmittelgrosshandel | >24 h | § 14 Abs. 2 Z 3 |

Bankwesen, Finanzmarktinfrastrukturen und digitale Infrastruktur sind nach
§ 18 Abs. 3 RKEG von § 17 ausgenommen. Die §§ 5, 6 und 11 RKEV enthalten
Einstufungskriterien, keine hier anzuwendenden Vorfallschwellen.
Ergebnis bei dokumentierter Sektorzuordnung: `EXEMPT_SECTOR`. Das trifft keine
Entscheidung ueber DORA-, NISG- oder andere sektorspezifische Pflichten.

## Rechenweg und Ergebnisse

Nutzerstunden = betroffene Nutzer x Stoerungsdauer in Stunden (§ 2 Z 4).
Zaehlpunktstunden = betroffene Zaehlpunkte x Stoerungsdauer in Stunden (§ 2 Z 6).
Fehlende Zahlen werden nicht geschaetzt, Null ist ein bekannter Zahlenwert.
Die Engine vergleicht ganzzahlige Mikrosekundenprodukte; Rundung der Anzeige
(acht Dezimalstellen) beeinflusst niemals die Entscheidung.

`NOT_ASSESSED`: keine dokumentierte Pruefung.
`NOT_APPLICABLE`: ausdruecklich keine Einstufung dokumentiert oder dokumentierter
Meldepflichtbeginn liegt in der Zukunft. Keine allgemeine rechtliche Entwarnung.
`EXEMPT_SECTOR`: dokumentierte Sektorausnahme.
`INSUFFICIENT_DATA`: entscheidende Daten fehlen; manuelle Pruefung erforderlich.
`BELOW_THRESHOLD`: beendete Stoerung, bekannte Daten, hinterlegte Schwelle nicht
ueberschritten. Kein Synonym fuer allgemein "nicht meldepflichtig".
`REPORTABLE`: hinterlegte Regel ist bei dokumentierter Anwendbarkeit eindeutig
erfuellt. `MANUAL_REVIEW`: unsichere Zuordnung, qualitative Voraussetzungen,
zeitliche Abgrenzung oder laufende Stoerung unterhalb der Schwelle.

Bei mehreren Diensten hat ein `REPORTABLE` Vorrang vor allen anderen Ergebnissen.
Ansonsten: unvollstaendige Daten vor manueller Pruefung vor unterschrittener
Schwelle vor Nichtanwendbarkeit vor Sektorausnahme. Alle Einzelergebnisse bleiben
sichtbar. Ein ausgenommener Dienst hebt eine positive Regel eines anderen Dienstes
nicht auf. Stoerungen, die vor Regelinkrafttreten oder Meldepflichtbeginn beginnen,
werden nicht rueckwirkend automatisch bewertet.

## Fristen und interne Meldungsentwuerfe

Erstmeldung: unverzueglich, maximal 24 verstrichene Stunden ab dokumentierter
Kenntnis vom meldepflichtigen Sicherheitsvorfall, soweit operativ moeglich.
Berechnung in UTC verhindert Fehler beim Sommer-/Winterzeitwechsel.
Fehlende Kenntniszeit bleibt offen, auch bei positivem Schwellenbefund.

Folgemeldung: ein Kalendermonat ab tatsaechlicher Erstmeldung, NICHT ab Erkennung
oder Entwurfserstellung. Berechnung in der Projektzeitzone Europe/Vienna, gleicher
Kalendertag, bei fehlendem Tag letzter Tag des Folgemonats (auch Schaltjahre).
Es wird kein pauschaler 30-Tage-Wert verwendet. Keine zusaetzliche Wochenend- oder
Feiertagsverlaengerung wird angenommen. Sonderfaelle der rechtlichen Fristbehandlung
muessen vor Produktivbetrieb freigegeben werden.

Beendigungsmeldung: unverzueglich nach dokumentiertem Ende; KEINE erfundene
Stundenfrist. Das interne Statusfeld CLOSED allein ersetzt keinen Endzeitpunkt.
Es gilt das Incident-Ende oder das dokumentierte Ende aller geprueften Dienste.

`IncidentReport` bildet INITIAL, FOLLOW_UP, ADDITIONAL_INFORMATION und
END_NOTIFICATION ab. Entwuerfe koennen bearbeitet werden. MARKED_AS_SUBMITTED
ist ausschliesslich die Dokumentation einer bereits erfolgten externen
Uebermittlung, mit Pflichtzeitpunkt. Solche Eintraege sind unveraenderlich;
Ergaenzungen erfolgen als neue Meldung. Bei mehreren dokumentierten Erstmeldungen
ist die zeitlich erste massgeblich. Eine Folgemeldung kann nicht vor ihr liegen.
Die strukturierten Inhaltsfelder decken die Informationskategorien von § 17 Abs. 3
ab; Unbekanntes darf im Entwurf leer bleiben. Keine Vollstaendigkeitsfreigabe fuer
eine behoerdliche Einreichung wird behauptet.

Es gibt KEINE elektronische Behoerdenuebermittlung, kein erfundenes BMI-Format,
keine API und keinen E-Mail-Versand. Parallele sektorspezifische/NISG-Pflichten
sind gesondert zu pruefen; DORA-/NISG-Entscheidungen werden nicht automatisiert.

## Audit und manuelle Uebersteuerung

GET berechnet eine aktuelle Vorschau ohne Schreibeffekt. Ein ausdrueckliches POST
speichert `IncidentRKEGAssessment` mit Ergebnis, Bearbeiter, Zeitpunkt, Regelversion,
vollstaendiger Regelzuordnung und Eingabesnapshot. Bei einem Dienst stehen die
Rechenwerte auch in typisierten Feldern; bei mehreren Diensten im JSON je Dienst,
ohne irrefuehrende Summierung unterschiedlicher Schwellen.

Eine manuelle Uebersteuerung erfordert eine nichtleere Begruendung. Es werden
atomar eine neue automatische Ausgangsbewertung und ein darauf verweisender
manueller Datensatz angelegt. Alte Ergebnisse werden nie ueberschrieben. Die
Oberflaeche zeigt manuelle und automatische Ergebnisse getrennt. Eine manuelle
Bewertung bleibt nur aktuell, solange Eingaben, Zuordnungen, Regelversion und
automatische Einzelergebnisse unveraendert sind. Neue Eingaben oder eine spaetere
Schwellenueberschreitung verlangen eine erneute Bewertung.

Das Dashboard zaehlt aktuelle Werte ausschliesslich fuer die aktive Organisation.
Fristenaufgaben aus bereits dokumentierten positiven Bewertungen oder erfolgten
Erstmeldungen verschwinden nicht durch nachtraegliches Herabsetzen von Daten.
Diese konservative Sicherung gilt auch bei manuellen Herabstufungen. "Faellig"
bedeutet beim Dashboard ueberfaellig oder innerhalb der naechsten 24 Stunden;
Erstmeldungen werden getrennt nach ueberfaellig/binnen 24 Stunden gezaehlt.
Fehlende Kenntniszeiten bleiben als manuelle Pruefung sichtbar.

## Sicherheit und Migration

Alle URLs verwenden den aktiven serverseitig geprueften Organisationskontext.
Unterobjekte werden nach Organisation UND Incident gefiltert. VIEWER liest nur;
ADMIN, RESILIENCE_MANAGER, RISK_MANAGER und EDITOR duerfen dokumentieren.
Organisation und Ersteller sind nicht editierbar. Dienstbezogene Daten akzeptieren
nur bereits zugeordnete Dienste derselben Organisation. Die bestehenden
M2M-Guards fuer Dienste, Standorte und Risiken bleiben erhalten. CSRF gilt fuer
alle schreibenden Formulare. Admin-Zugriffe auf neue Vorfallobjekte sind lesend
und Systemadministratoren vorbehalten.

Additive Migrationen in organizations, services und incidents fuegen optionale
Felder und drei Tabellen hinzu. Es werden keine alten Werte geloescht, keine
Einstufung abgeleitet, keine bisherigen Meldebewertungen umgedeutet und keine
Kenntniszeiten geraten. Alte Texte, Nutzer, Beziehungen und Risikodaten bleiben
erhalten. Das neue Organisationsreferenzfeld besitzt einen leeren Datenbankstandard
fuer historische Schreibpfade in Migrationstests.

## Bekannte Grenzen

- Keine rechtssichere Vollautomatik: Bescheid und qualitative Voraussetzungen
  muessen durch befugte Anwender korrekt dokumentiert werden.
- Keine Prognose potenzieller Stoerungen; unterhalb der gemessenen Schwelle bleibt
  deren gesonderte fachliche Pruefung erforderlich.
- Eine konstante Betroffenenzahl je Dienst/Zeitraum. Wechselnde Nutzerzahlen,
  getrennte Stoerungsintervalle oder komplexe Wiederanlaeufe sind manuell zu pruefen.
- Kein Hintergrundscheduler, keine Benachrichtigung. Laufende Werte aktualisieren
  sich beim Abruf; gespeicherte Snapshots behalten ihren damaligen Stand.
- Die Audit-Unveraenderlichkeit gilt fuer normale Modell-/UI-Schreibpfade.
  Direkte SQL-Zugriffe, QuerySet.update/bulk-Writes und privilegierte Datenbank-
  administration koennen Modellvalidierung umgehen. Kein revisionssicheres Archiv
  gegen Datenbankadministratoren; Backups und administrative Zugriffskontrollen
  bleiben erforderlich.
- Dashboard-Berechnung erfolgt pro Vorfall; fuer grosse Datenmengen sind spaeter
  gezielte Abfragen/Caching mit nachvollziehbarer Aktualisierung erforderlich.
