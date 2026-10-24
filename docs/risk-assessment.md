# Risikobewertung im Prototyp

Wahrscheinlichkeit und Auswirkung sind ganze Zahlen von 1 bis 5.
Der Risikowert ist ihr Produkt; er und seine Klasse werden nicht gespeichert.
Die Klassengrenzen stehen zentral in `risks/assessment.py`. Die Klassifikation
akzeptiert alternative Grenzen, damit spaeter eine organisationsbezogene
Methodik angebunden werden kann. Derzeit verwenden alle Organisationen dieselben
Grenzen: 1-4 niedrig, 5-9 mittel, 10-16 hoch, 17-25 kritisch.
Dies ist eine Prototypmethodik, keine Aussage ueber ISO-Konformitaet.

## Bruttorisiko, Kontrollen und Restrisiko

Bruttorisiko bezeichnet die Bewertung vor Beruecksichtigung bestehender
Kontrollen. Die bisherigen Felder `likelihood`, `impact`, `risk_score` und
`risk_class` behalten ihre Namen und diese Bedeutung. Risikoquelle/Ursache
(`risk_source`) und moegliche Auswirkungen (`potential_impact`) ergaenzen die
Beschreibung optional.

RiskControl dokumentiert bereits vorhandene Kontrollen, ihren Typ, die
eingeschaetzte Wirksamkeit (1-5) und eine optionale verantwortliche Person.
RiskMeasure bleibt fuer geplante bzw. nachverfolgte Massnahmen bestehen.

Restrisiko ist die vom Anwender bewusst bewertete Wahrscheinlichkeit und
Auswirkung nach Beruecksichtigung vorhandener Kontrollen. `residual_likelihood`
und `residual_impact` werden unabhaengig von der Bruttobewertung eingegeben.
`residual_risk_score` und `residual_risk_class` nutzen dieselben zentralen
Berechnungsfunktionen und Schwellenwerte wie Brutto.

Kontrollwirksamkeit wird NICHT mathematisch abgezogen: die ordinalen Skalen
beschreiben Einschaetzungen, keine direkt verrechenbaren Reduktionsprozente.
Das Anlegen, Bearbeiten oder Entfernen einer Kontrolle aendert keine
Risikobewertung. Auch eine hoehere Restrisikobewertung wird nicht technisch
verhindert; die fachliche Bewertung bleibt beim Anwender.

## Migration 0002: erste Bewertung

Bestehende Risiken erhalten Wahrscheinlichkeit 3 (moeglich) und Auswirkung 3
(mittel), also Risikowert 9 / Mittel. Dies ist ausschliesslich ein technischer
Startwert und muss fachlich ueberprueft werden. Auch neue Formulare starten mit
diesen Werten. Die Behandlungsstrategie bleibt leer. Bestehende IDs,
Organisationen, Ersteller, Beschreibungen, Status und Zeitstempel bleiben erhalten.
Es werden keine Massnahmen automatisch angelegt.

## Migration 0003: Restrisiko und Kontrollen

`0003_residual_risk_controls` legt die neuen Felder und RiskControl an.
Die Datenmigration kopiert fuer JEDES bestehende Risiko die vorhandenen Werte
`likelihood` und `impact` unveraendert nach `residual_likelihood` und
`residual_impact`. Damit gilt initial Brutto = Restrisiko, ohne eine
Risikoreduktion zu unterstellen. Bestehende Inhalte, IDs, Bruttowerte,
Organisationen und Zeitstempel bleiben unveraendert. Neue Textfelder bleiben
leer; Kontrollen werden nicht automatisch angelegt.

Neue Risikoformulare starten bei beiden Bewertungen mit 3/3. Alle vier
Bewertungsfelder sind Pflichtfelder und vor dem Speichern fachlich zu pruefen.
Eine spaetere Bruttoaenderung ueberschreibt keine manuelle Restrisikobewertung.
Ein Rueckrollen entfernt die neuen Felder und Kontrollen und verliert damit
die darin gespeicherten Daten; zuvor eine Datenbanksicherung erstellen.

## Ansichten und Kompatibilitaet

`/risks/matrix/` und `?type=gross` zeigen Brutto; `?type=residual` zeigt
Restrisiko. Unbekannte Typen fallen auf Brutto zurueck. Bestehende Filter und
Sortierparameter bleiben bruttoorientiert; `residual_risk_class` filtert
zusaetzlich die Restrisikoklasse. Das Dashboard zeigt getrennte Klassenzahlen.
Beide Matrixarten, Listen und Kennzahlen verwenden ausschliesslich die aktive
Organisation. Alle Werte/Klassen sind abgeleitet und keine editierbaren Felder.

## Bedienung und Datenintegritaet

"Bewertung berechnen" zeigt die eingegebenen Werte serverseitig an, ohne zu
speichern. "Speichern" berechnet mit denselben Regeln. Der Massnahmenstatus
"Ueberfaellig / nicht umgesetzt" wird manuell gesetzt; das Faelligkeitsdatum
loest keine automatische Statusaenderung aus.

Massnahmen und Kontrollen uebernehmen ihre Organisation aus dem Risiko. Verantwortliche muessen
aktive Benutzer mit aktiver Membership dieser Organisation sein. Entfaellt ihre
Mitgliedschaft spaeter, bleibt die historische Zuweisung sichtbar, muss aber beim
naechsten Speichern entfernt oder neu zugewiesen werden.

Risiken mit Massnahmen oder Kontrollen koennen ihre Organisation nicht wechseln. Model-Saves
validieren die Zuordnung; direkte SQL-Schreibzugriffe, bulk_create und
QuerySet.update umgehen Django-Modelvalidierung und sind fuer Aenderungen dieser
Zuordnungen nicht zulaessig. SQLite kann organisationsuebergreifende Bedingungen
zwischen Tabellen nicht mit einem normalen CHECK-Constraint pruefen.
