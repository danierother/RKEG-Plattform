# Konfiguration

Die Plattform verwendet Django 5.2 und lokal standardmaessig SQLite.
PostgreSQL kann ausschliesslich ueber die Environment-Konfiguration aktiviert
werden. `requirements.txt` enthaelt den vorgesehenen psycopg-Treiber; in diesem
Konfigurationsschritt wurden keine Pakete installiert oder Daten uebertragen.
`config/environment.py` liest ausschliesslich die Prozessumgebung. Eine `.env`
wird **nicht automatisch geladen**. `.env.example` enthaelt nur einen
absichtlich ungueltigen Schluesselplatzhalter, keine Zugangsdaten.

## Variablen

| Variable | Lokaler Standard | Bedeutung |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Nicht gesetzt: zufaelliger Entwicklungsschluessel je Prozess | Dauerhafter, geheimer Signaturschluessel. Bei `DEBUG=False` zwingend. |
| `DJANGO_DEBUG` | `true` | Debug-Ausgaben; auf einem Testserver/Produktivsystem explizit `false`. |
| `DJANGO_ALLOWED_HOSTS` | Bei Debug: `127.0.0.1,localhost`; sonst leer | Kommagetrennte Hostnamen ohne Schema/Pfad. Bei Debug aus: nicht leer, kein `*`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Leer | Optionale kommagetrennte Origins einschliesslich `http://` oder `https://`, ggf. Port, ohne Pfad/abschliessenden Slash. |
| `DJANGO_SECURE_SSL` | `false` | Schaltet SSL-Redirect sowie sichere Session- und CSRF-Cookies gemeinsam ein. Bei `true` sind konfigurierte CSRF-Origins nur mit HTTPS erlaubt. |
| `DJANGO_SECURE_HSTS_SECONDS` | `0` | HSTS-Laufzeit; nur mit aktivem Secure-SSL-Schalter. Zunaechst bewusst ausgeschaltet. |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | `false` | HSTS auch fuer Subdomains. Erfordert positive Laufzeit und abgesicherte Subdomains. |
| `DJANGO_SECURE_HSTS_PRELOAD` | `false` | Preload-Direktive, keine automatische Registrierung. Erfordert mindestens ein Jahr Laufzeit und IncludeSubDomains. |

Boolean-Werte akzeptieren `true/false`, `1/0`, `yes/no`, `on/off`, ohne
Beachtung von Gross-/Kleinschreibung. Unbekannte oder explizit leere Werte
fuehren zum Startabbruch statt zu stillen Sicherheitsannahmen. Listen werden
getrimmt, leere Elemente entfernt und Duplikate zusammengefasst.

Ein gesetzter Schluessel muss mindestens 50 Zeichen mit mindestens fuenf
unterschiedlichen Zeichen besitzen; `replace-me` wird abgewiesen. Diese
Mindestpruefung ersetzt keine kryptografisch sichere Erzeugung. Einen eigenen
Schluessel einmal sicher erzeugen, privat verwahren und unveraendert in alle
Prozesse derselben Umgebung laden. Nie zwischen Entwicklung und Produktion
teilen, in Git einchecken, protokollieren oder bei jedem Serverstart neu erzeugen.

## Lokale Entwicklung und Sessions

Ohne Variablen bleibt `http://127.0.0.1:8000` funktionsfaehig. Der zufaellige
Fallback ist ausschliesslich fuer kurzlebige Entwicklung geeignet. Er ist
nicht persistent und nicht fuer mehrere Prozesse geeignet.

Die bisherige Settings-Zeile erzeugte bei jedem Import ohne Environment-Key
einen neuen Schluessel. Vorhandene signierte Session-Daten konnten dadurch
nach Neustarts nicht mehr geprueft werden (`Session data corrupted`). Mit
demselben festen `DJANGO_SECRET_KEY` bleiben Signaturen nach normalen Neustarts
gueltig. Die Signaturpruefung wird nicht abgeschwaecht. Alte Sessions mit einem
bereits verlorenen Zufallsschluessel sind nicht wiederherstellbar: einmal neu
anmelden. Auch Passwortwechsel, Ablauf oder bewusste Schluesselrotation koennen
Sessions weiterhin ungueltig machen.

Beispiel fuer Bash, ohne einen Schluessel in die Shell-History zu schreiben:

```bash
read -r -s -p 'Dauerhaften lokalen Secret Key eingeben: ' DJANGO_SECRET_KEY
printf '\n'
export DJANGO_SECRET_KEY
export DJANGO_DEBUG=true
export DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
export DJANGO_CSRF_TRUSTED_ORIGINS=
export DJANGO_SECURE_SSL=false
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Nach Oeffnen einer neuen Shell denselben privaten Schluessel erneut laden.
Alternativ kann eine private, zugriffsbeschraenkte `.env` ausserhalb der
Versionsverwaltung verwendet werden. `.gitignore` schliesst `.env` bereits
aus, nicht jedoch beliebig benannte Dateien wie `.env.production`.
Nur eine selbst kontrollierte Datei in der eigenen Shell auswerten:

```bash
set -a
. ./.env
set +a
```

Shell-Sonderzeichen in Werten muessen korrekt quotiert sein. Das Auswerten
fuehrt Shell-Code aus; fremde oder hochgeladene Dateien niemals sourcen.
Es gibt absichtlich keinen dotenv-Loader und kein neues Paket.

## Beispiel fuer einen spaeteren HTTPS-Testserver

Den dauerhaften Key vorher aus einem privaten Speicher in die Umgebung laden.
Die folgende Beispieldomain ist kein konfiguriertes Hostingziel:

```bash
export DJANGO_DEBUG=false
export DJANGO_ALLOWED_HOSTS=rkeg-test.example.org
export DJANGO_CSRF_TRUSTED_ORIGINS=https://rkeg-test.example.org
export DJANGO_SECURE_SSL=true
export DJANGO_SECURE_HSTS_SECONDS=0
export DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false
export DJANGO_SECURE_HSTS_PRELOAD=false
.venv/bin/python manage.py check --deploy
```

Das ist eine Settings-Vorbereitung, kein funktionierendes HTTPS-Deployment.
`runserver` stellt dadurch kein TLS bereit. Django muss spaeter tatsaechlich
HTTPS erkennen. `SECURE_PROXY_SSL_HEADER` wird hier bewusst nicht gesetzt:
Blindes Vertrauen in vom Client gesetzte Forwarded-Header waere unsicher.
Erst nach Auswahl und Absicherung des Proxys entscheiden, welche Header dieser
entfernt/ueberschreibt und welche Django vertrauen darf. Sonst drohen auch
Redirect-Schleifen. Ohne echten HTTPS-Zugang keine Secure-Cookies fuer den
lokalen HTTP-Betrieb einschalten.

HSTS erst nach verifiziertem HTTPS aktivieren, anfangs beispielsweise mit
300 Sekunden. IncludeSubDomains und Preload bleiben separate Entscheidungen.
Browser merken sich HSTS; Abschalten auf dem Server setzt den Browserzustand
nicht sofort zurueck. Keine dauerhaften HSTS-Experimente auf localhost.

## Systemchecks

Der Settings-Import scheitert bei fehlendem Produktionsschluessel, fehlenden
Produktionshosts, Wildcard-Produktionshosts und fehlerhaften Variablen.
Zusaetzliche Checks werden ueber `core.apps.CoreConfig.ready()` registriert
und nur bei `check --deploy` ausgefuehrt. `rkeg.E001/E002` erkennen dort auch
spaetere ungueltige Settings-Ueberschreibungen.

Bei unveraenderter lokaler Umgebung ohne Key sind folgende Warnungen erwartet:

| Warnung | Grund / spaetere Behebung |
| --- | --- |
| `rkeg.W001` | Ephemerer Entwicklungsschluessel; festen Environment-Key setzen. |
| `security.W004` | HSTS aus; erst nach funktionierendem HTTPS bewusst einschalten. |
| `security.W008` | HTTP-Redirect aus; auf echtem HTTPS-Testserver einschalten. |
| `security.W012` | Session-Cookie nicht Secure; lokal HTTP, auf HTTPS einschalten. |
| `security.W016` | CSRF-Cookie nicht Secure; lokal HTTP, auf HTTPS einschalten. |
| `security.W018` | DEBUG an; auf dem Testserver explizit ausschalten. |

Im HTTPS-Beispiel verbleibt nur `security.W004`. Mit einer positiven
HSTS-Laufzeit und weiterhin ausgeschalteten Subdomain-/Preload-Optionen
erscheinen stattdessen `security.W005` (IncludeSubDomains) und `security.W021`
(Preload). Diese Warnungen bewusst bewerten und dokumentieren, nicht allein
fuer einen gruenen Check die Optionen aktivieren. Erst eine explizite
Konfiguration mit mindestens einem Jahr HSTS, IncludeSubDomains und Preload
kann hier ohne diese Warnungen bestehen. Das ist kein Sicherheitsnachweis
fuer Infrastruktur oder Rechtskonformitaet.
Keine Warnungen werden per `SILENCED_SYSTEM_CHECKS` ausgeblendet.

## Static, Medien und Datenbank

`STATIC_URL=/static/`; `STATIC_ROOT=<Projekt>/staticfiles`. Die Dateien verbleiben
in den bisherigen App-Verzeichnissen; `runserver` findet sie im Debug-Modus.
`collectstatic --dry-run --noinput` prueft das Einsammeln ohne Dateien anzulegen.
Beim spaeteren Betrieb sammelt `collectstatic --noinput` die Dateien im
Ausgabeverzeichnis. Dieses ist ein Build-Artefakt, keine Quelle: nicht committen
oder mit einer echten `.env` ausliefern. `.gitignore` wurde hier nicht erweitert.
Bei `DEBUG=False` braucht es spaeter eine eigene Static-Auslieferung; es wurden
weder WhiteNoise noch Webserver oder CDN eingerichtet.

Es existieren derzeit keine FileField/ImageField-Uploads. Daher keine neuen
MEDIA-Einstellungen oder URL-Routen. Spaeter `MEDIA_ROOT` getrennt von Static
definieren und `MEDIA_URL`, Zugriffsschutz, Dateipruefung, Limits, Backup und
Mandantenrechte gemeinsam planen. Vertrauliche Uploads nicht einfach oeffentlich
ausliefern.

## Datenbankauswahl

`config.environment.load_database()` erzeugt den `DATABASES`-Block ohne einen
Treiber zu laden oder eine Verbindung aufzubauen. Die bisherigen
Sicherheitseinstellungen gelten unabhaengig vom Datenbanktyp weiter.

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `DJANGO_DB_ENGINE` | `sqlite` | `sqlite` oder `postgresql`; unbekannte oder leere Werte brechen den Start ab. |
| `POSTGRES_DB` | Keiner | Datenbankname, bei PostgreSQL erforderlich. |
| `POSTGRES_USER` | Keiner | DB-Benutzer, bei PostgreSQL erforderlich. |
| `POSTGRES_PASSWORD` | Keiner | Nur ueber Environment; bei PostgreSQL erforderlich. |
| `POSTGRES_HOST` | Keiner | DB-Host, bei PostgreSQL erforderlich. Auf diesem Testserver `127.0.0.1`. |
| `POSTGRES_PORT` | `5432` | Ganzzahl zwischen 1 und 65535. |

Lokale Entwicklung:

```bash
export DJANGO_DB_ENGINE=sqlite
```

Auch ohne diese Variable wird unveraendert `django.db.backends.sqlite3` mit
`BASE_DIR / 'db.sqlite3'` verwendet. PostgreSQL-Variablen werden im SQLite-Modus
nicht ausgewertet. Die Umschaltung veraendert oder kopiert keine Daten.

Testserver (Konfigurationsschema; `<secret>` ist nur ein Platzhalter):

```text
DJANGO_DB_ENGINE=postgresql
POSTGRES_DB=rkeg
POSTGRES_USER=rkeg_app
POSTGRES_PASSWORD=<secret>
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

Django und PostgreSQL laufen auf demselben Ubuntu-Testserver. **Der PostgreSQL-
Port wird nicht oeffentlich geoeffnet.** PostgreSQL-Listener, `pg_hba.conf` und
Firewall muessen diesen lokalen Zugriff passend absichern; diese
Serverkonfiguration wird hier nicht veraendert. Der Passwortwert wird nur
ueber die Prozessumgebung bereitgestellt, nicht im Quellcode oder in Befehlen
mit echtem Passwort abgelegt. Eine `.env` wird weiterhin **nicht automatisch
geladen**. Die vorhandenen privaten Environment-Variablen muessen dem
Django-Prozess explizit uebergeben werden. `replace-me` in `.env.example` vor
echter PostgreSQL-Nutzung ersetzen; es ist kein Passwortdefault des Codes.

Fehlende oder nur aus Leerzeichen bestehende Pflichtwerte fuehren zu einer
Konfigurationsfehlermeldung, die nur den Variablennamen nennt. Das Passwort
wird unveraendert uebernommen, einschliesslich etwaiger Rand-Leerzeichen.
Ein fehlender Port verwendet 5432; ein explizit leerer/ungueltiger Port wird
abgewiesen. Es gibt keinen stillen Rueckfall von PostgreSQL auf SQLite.

Die lokalen Settings-Tests simulieren PostgreSQL mit fluechtigen Dummy-Werten
und blockierten Netzwerkverbindungen. Sie benoetigen keinen installierten
PostgreSQL-Treiber und pruefen keine echte Anmeldung, Serverrechte oder
PostgreSQL-spezifischen Fachabfragen. Ein spaeterer Testlauf gegen eine eigene
isolierte PostgreSQL-Testdatenbank bleibt erforderlich. Nicht gegen eine
Datenbank mit realen Daten testen; Django-Tests legen Testdatenbanken an.
Es wurden keine Migrationen erzeugt/angewendet, keine SQLite-Daten kopiert und
kein `DATABASE_URL`-Paket ergaenzt.

## Logging und Datenschutz

Lesbare Konsolenausgabe mit Zeit, Level und Logger. `django` und
`django.security` protokollieren ab WARNING, `django.server` lokale Zugriffe
ab INFO; `rkeg` sowie die App-Namensraeume protokollieren ab WARNING.
Anwendungsfehler koennen beispielsweise mit `logging.getLogger(__name__)`
oder `logging.getLogger('rkeg')` erfasst werden. Keine E-Mail-Handler,
Logdateien, SQL-Debugausgaben oder externen Dienste hinzugefuegt.

Der Formatter maskiert bekannte Schluessel, `DEMO_PASSWORD` und
`POSTGRES_PASSWORD` (auch das bereits in `DATABASES` geladene Passwort), gaengige
Credential-Felder, Authorization-Tokens und URL-Querywerte auch in Tracebacks.
Er erfasst keine lokalen Variablen. Request-Bodies, Cookies, Authorization,
vollstaendige Settings und sensible Falldaten duerfen trotzdem niemals bewusst
protokolliert werden. Musterfilter koennen unbekannte, codierte oder frei
formulierte Geheimnisse nicht zuverlaessig erkennen. Zugriffsrechte,
Aufbewahrung, Rotation und Weiterleitung der Konsolenlogs sind spaetere
Betriebsaufgaben. Das fachliche Audit bleibt davon getrennt und unveraendert.

## Kleine Oberflaechenkorrekturen

Abmelden ist deutsch beschriftet. Kennzahlen passen auf kleinen Ansichten in
zwei Spalten, lange Statusbeschriftungen koennen umbrechen. Breite Tabellen
bleiben innerhalb ihres Containers scrollbar. Druckansichten blenden
Rueckmeldungen aus, behalten aber die Demo-Kennzeichnung sichtbar.
Die Kennzeichnung nutzt das bereits vorhandene `DEMO / TESTDATEN` in
`Organization.legal_name`, aendert keine Daten und ist kein Berechtigungsmerkmal.

## Referenzen

- [Django 5.2 Deployment-Checkliste](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Django 5.2 Logging und Sicherheitsaspekte](https://docs.djangoproject.com/en/5.2/topics/logging/)
