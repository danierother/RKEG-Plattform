# Checkliste vor einem spaeteren Testserver

Noch kein Hosting/Deployment eingerichtet. Jede Zeile separat pruefen und
Ergebnisse dokumentieren; bestandene Django-Checks ersetzen keinen Betriebstest.

Umgebung: __________  Verantwortlich: __________  Datum: __________

## Konfiguration und HTTPS

- [ ] `DJANGO_DEBUG=false` explizit gesetzt; keine Debug-Fehlerseiten erreichbar.
- [ ] Eigener starker `DJANGO_SECRET_KEY` dauerhaft und privat bereitgestellt,
      auf allen Prozessen identisch; kein Entwicklungskey, kein Platzhalter.
- [ ] `.env`/Secrets nicht versioniert, nicht in Static-Verzeichnissen oder
      Artefakten; restriktive Dateirechte und gesonderte Sicherung geklaert.
- [ ] `DJANGO_ALLOWED_HOSTS` enthaelt nur vorgesehene Hosts, keine `*`-Freigabe.
- [ ] `DJANGO_CSRF_TRUSTED_ORIGINS` nur bei Bedarf, mit expliziten HTTPS-Origins;
      normale Anmeldung und CSRF-Abweisung fremder Origins getestet.
- [ ] HTTPS und Zertifikatsbetrieb eingerichtet und getestet, bevor
      `DJANGO_SECURE_SSL=true` aktiviert wird. HTTP wird auf HTTPS umgeleitet.
- [ ] Session- und CSRF-Cookies haben Secure; Session-Cookie behaelt HttpOnly
      und die bestehenden SameSite-Einstellungen.
- [ ] Etwaige Proxy-Header nur von einem vertrauenswuerdigen, absichernden
      Proxy akzeptiert; keine blind uebernommenen Client-Header, keine Schleifen.
- [ ] HSTS zuerst mit kurzer Laufzeit getestet. Subdomains einzeln geprueft;
      IncludeSubDomains/Preload nur nach eigener bewusster Freigabe.

## Anwendung und Betrieb

- [ ] Abhaengigkeiten und Python-Version reproduzierbar dokumentiert/gebunden.
      Aktueller Stand: Python 3.12, Django 5.2.17, asgiref und sqlparse;
      bislang kein Requirements-/Lockfile vorhanden. Keine Pakete hier ergaenzt.
- [ ] Datenbankentscheidung gesondert getroffen. Aktuell weiterhin SQLite;
      keine PostgreSQL-Installation oder -Migration in diesem Schritt.
- [ ] Vorhandene Migrationen mit `showmigrations` geprueft; spaeteres `migrate`
      nur nach Backup und Freigabe. `makemigrations --check --dry-run` sauber.
- [ ] `collectstatic --noinput` im vorgesehenen Build/Betrieb ausgefuehrt;
      `STATIC_ROOT` nicht versioniert und korrekt ausgeliefert. CSS/Logo mit
      `DEBUG=False` abrufbar. `runserver` ist kein Produktionsserver.
- [ ] Keine Uploads erwartet. Spaetere Uploads brauchen ein eigenes
      Speicher-, Berechtigungs- und Sicherheitskonzept, kein offenes MEDIA-Verzeichnis.
- [ ] Konsolenlogging erfasst Django-, Security- und Anwendungsfehler;
      keine Geheimnisse oder personenbezogenen Nutzdaten in Testlogs.
- [ ] Zugriff, Rotation, Speichergrenzen und Aufbewahrungsdauer fuer Logs geklaert.
- [ ] Admin-Benutzer mit eigenem starken Passwort und minimal noetigen Rechten;
      keine oeffentliche Registrierung und keine Demo-Zugaenge auf realen Daten.
- [ ] Demo-Daten getrennt halten: vorzugsweise eigene leere Testdatenbank und
      eigene Umgebung. Kein pauschales Loeschen aus einer gemischten Datenbank;
      es gibt bewusst keinen `clear_demo_data`-Command.
- [ ] Vorhandene lokale/reale Daten unveraendert halten. Vorfall-, Risiko-,
      Audit- und Meldedaten auf Vertraulichkeit und Berechtigungen pruefen.
- [ ] Datenschutz: Zweck, Rollen, Zugriffe, Loesch-/Aufbewahrungskonzept,
      Informationspflichten und Verarbeitung sensibler Daten geklaert.

## Backup und Wiederherstellung

- [ ] Konsistentes Datenbankbackup vor Aenderungen; bei SQLite keine ungepruefte
      Kopie einer gerade beschriebenen Datei, sondern konsistente Backup-Methode.
- [ ] Sicherungsumfang, Zugriffsschutz, Verschluesselung, Aufbewahrung und
      Verantwortlichkeit festgelegt. Secrets separat und sicher gesichert.
- [ ] Restore-Test in isolierter Umgebung durchgefuehrt: Anmeldung,
      Mandantenrechte, Risiken, Vorfaelle, Assessments und Audit geprueft.
- [ ] Wiederanlauf/Rollback dokumentiert und praktisch erprobt.

## Abnahme

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test
.venv/bin/python manage.py check --deploy
```

- [ ] Alle bisherigen Fachtests und neuen Konfigurationstests erfolgreich.
- [ ] `check --deploy` mit den tatsaechlichen Testserver-Settings ausgefuehrt;
      Warnungen einzeln bewertet, keine pauschale Unterdrueckung.
- [ ] Session ueber einen normalen Neustart mit identischem Schluessel erhalten.
- [ ] Login/Logout, Viewer-Schreibverbote und direkte fremde URLs geprueft.
- [ ] Desktop/Mobil, breite Tabellen, leere Listen, Formularfehler,
      CSV-Export und echte Browser-Druck/PDF-Ausgabe manuell geprueft.
- [ ] Demo-Kennzeichnung im Bildschirm und Ausdruck sichtbar, keine
      fremden Mandantendaten. Sie ersetzt keine Zugriffskontrolle.
- [ ] Ungeklaerte Punkte dokumentiert und vor Freigabe erledigt.

Die lokalen Entwicklungswarnungen und ihre Ursachen stehen in
[configuration.md](configuration.md). Noch nicht umgesetzt sind Hosting,
Produktionsserver, TLS, Proxy, PostgreSQL, externe Backups und Monitoring.

Freigabe: __________  Offene Punkte: _________________________________
