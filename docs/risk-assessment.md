# Risikobewertung im Prototyp

Wahrscheinlichkeit und Auswirkung sind ganze Zahlen von 1 bis 5.
Der Risikowert ist ihr Produkt; er und seine Klasse werden nicht gespeichert.
Die Klassengrenzen stehen zentral in `risks/assessment.py`. Die Klassifikation
akzeptiert alternative Grenzen, damit spaeter eine organisationsbezogene
Methodik angebunden werden kann. Derzeit verwenden alle Organisationen dieselben
Grenzen: 1-4 niedrig, 5-9 mittel, 10-16 hoch, 17-25 kritisch.
Dies ist eine Prototypmethodik, keine Aussage ueber ISO-Konformitaet.

## Migration bestehender Risiken

Bestehende Risiken erhalten Wahrscheinlichkeit 3 (moeglich) und Auswirkung 3
(mittel), also Risikowert 9 / Mittel. Dies ist ausschliesslich ein technischer
Startwert und muss fachlich ueberprueft werden. Auch neue Formulare starten mit
diesen Werten. Die Behandlungsstrategie bleibt leer. Bestehende IDs,
Organisationen, Ersteller, Beschreibungen, Status und Zeitstempel bleiben erhalten.
Es werden keine Massnahmen automatisch angelegt.

## Bedienung und Datenintegritaet

"Bewertung berechnen" zeigt die eingegebenen Werte serverseitig an, ohne zu
speichern. "Speichern" berechnet mit denselben Regeln. Der Massnahmenstatus
"Ueberfaellig / nicht umgesetzt" wird manuell gesetzt; das Faelligkeitsdatum
loest keine automatische Statusaenderung aus.

Massnahmen uebernehmen ihre Organisation aus dem Risiko. Verantwortliche muessen
aktive Benutzer mit aktiver Membership dieser Organisation sein. Entfaellt ihre
Mitgliedschaft spaeter, bleibt die historische Zuweisung sichtbar, muss aber beim
naechsten Speichern entfernt oder neu zugewiesen werden.

Risiken mit Massnahmen koennen ihre Organisation nicht wechseln. Model-Saves
validieren die Zuordnung; direkte SQL-Schreibzugriffe, bulk_create und
QuerySet.update umgehen Django-Modelvalidierung und sind fuer Aenderungen dieser
Zuordnungen nicht zulaessig. SQLite kann organisationsuebergreifende Bedingungen
zwischen Tabellen nicht mit einem normalen CHECK-Constraint pruefen.
