import os

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from core.demo_data import seed_demo_data, demo_summary


class Command(BaseCommand):
    help = 'Legt eindeutig markierte DEMO / TESTDATEN an; veraendert keinen vorhandenen Datenbestand.'

    def handle(self, *args, **options):
        password = os.environ.get('DEMO_PASSWORD', '')
        if not password.strip():
            raise CommandError('DEMO_PASSWORD fehlt oder ist leer. Bitte ein temporaeres lokales Passwort als Umgebungsvariable setzen.')
        try:
            organizations, created = seed_demo_data(password)
        except IntegrityError as exc:
            raise CommandError('Demo-Anlage wegen einer Datenkollision abgebrochen; alle Aenderungen wurden zurueckgerollt.') from exc
        self.stdout.write(self.style.SUCCESS(
            'DEMO / TESTDATEN angelegt.' if created else 'DEMO / TESTDATEN bereits vorhanden; keine Daten oder Passwoerter veraendert.'))
        for label, count in demo_summary(organizations).items():
            self.stdout.write(f'{label}: {count}')
        self.stdout.write('Keine reale behoerdliche Einstufung oder Uebermittlung. Nur lokale Demo-/Testnutzung.')
