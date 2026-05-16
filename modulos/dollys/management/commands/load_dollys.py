import csv
from pathlib import Path
from django.core.management.base import BaseCommand
from modulos.dollys.models import Dolly


class Command(BaseCommand):
    help = 'Importa dollys desde dollys.csv'

    def add_arguments(self, parser):
        parser.add_argument('--csv', default='dollys.csv', help='Ruta al archivo CSV')
        parser.add_argument('--dry-run', action='store_true', help='Simula sin guardar')

    def handle(self, *args, **options):
        csv_path = Path(options['csv'])
        if not csv_path.exists():
            self.stderr.write(f'Archivo no encontrado: {csv_path}')
            return

        creados = 0
        actualizados = 0
        errores = 0

        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            # Normalizar nombres de columna (strip espacios)
            for row in reader:
                row = {k.strip(): v for k, v in row.items()}
                eco = row.get('ECO', '').strip().upper()
                if not eco:
                    continue

                numero_serie = row.get('NO SERIE', '').strip()
                if not numero_serie:
                    self.stdout.write(self.style.WARNING(f'  [{eco}] Sin número de serie, omitido'))
                    errores += 1
                    continue

                datos = dict(
                    marca=row.get('MARCA', '').strip(),
                    color=row.get('COLOR', '').strip(),
                    activo=True,
                )

                if not options['dry_run']:
                    obj, created = Dolly.objects.update_or_create(
                        numero_economico=eco,
                        defaults={**datos, 'numero_serie': numero_serie},
                    )
                    if created:
                        creados += 1
                    else:
                        actualizados += 1
                else:
                    self.stdout.write(f'  [DRY] {eco} — {numero_serie}')
                    creados += 1

        self.stdout.write(self.style.SUCCESS(
            f'Dollys: {creados} creados, {actualizados} actualizados, {errores} errores'
        ))
