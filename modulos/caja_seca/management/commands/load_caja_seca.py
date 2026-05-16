import csv
from pathlib import Path
from django.core.management.base import BaseCommand
from modulos.caja_seca.models import CajaSeca


class Command(BaseCommand):
    help = 'Importa cajas secas desde caja_seca.csv'

    def add_arguments(self, parser):
        parser.add_argument('--csv', default='caja_seca.csv', help='Ruta al archivo CSV')
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
            for row in reader:
                eco = row.get('ECO', '').strip().upper()
                if not eco:
                    continue

                numero_serie = row.get('NUMERO DE SERIE', '').strip()
                if not numero_serie:
                    self.stdout.write(self.style.WARNING(f'  [{eco}] Sin número de serie, omitido'))
                    errores += 1
                    continue

                anio_raw = row.get('AÑO', '').strip()
                anio = None
                if anio_raw:
                    try:
                        anio = int(anio_raw)
                    except ValueError:
                        pass

                datos = dict(
                    placas=row.get('PLACAS', '').strip(),
                    marca=row.get('MARCA', '').strip(),
                    modelo=row.get('MODELO', '').strip(),
                    anio=anio,
                    color=row.get('COLOR', '').strip(),
                    activo=True,
                )

                if not options['dry_run']:
                    obj, created = CajaSeca.objects.update_or_create(
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
            f'Cajas Secas: {creados} creadas, {actualizados} actualizadas, {errores} errores'
        ))
