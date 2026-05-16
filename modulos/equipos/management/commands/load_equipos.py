import csv
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand
from modulos.equipos.models import Equipo


class Command(BaseCommand):
    help = 'Importa equipos desde equipos.csv'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            default='equipos.csv',
            help='Ruta al archivo CSV (default: equipos.csv en raíz del proyecto)'
        )
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
                eco = row.get('ECONOMICO', '').strip().upper()
                if not eco:
                    continue

                # Tipo desde el económico
                if eco.startswith('PLANA'):
                    tipo = 'PLANA'
                elif eco.startswith('CHASIS'):
                    tipo = 'CHASIS'
                else:
                    tipo = 'OTRO'

                # Vigencia — puede ser fecha DD/MM/YYYY o "N/A"
                vigencia_raw = row.get('VIGENCIA DOBLE ARTICULADO', '').strip()
                vigencia = None
                if vigencia_raw and vigencia_raw.upper() != 'N/A':
                    try:
                        vigencia = datetime.strptime(vigencia_raw, '%d/%m/%Y').date()
                    except ValueError:
                        self.stdout.write(
                            self.style.WARNING(f'  [{eco}] Fecha inválida: {vigencia_raw}')
                        )

                verificacion = row.get('VERIFICACION', 'SI').strip().upper() == 'SI'
                numero_serie = row.get('NO. DE SERIE', '').strip()

                if not numero_serie:
                    self.stdout.write(self.style.WARNING(f'  [{eco}] Sin número de serie, omitido'))
                    errores += 1
                    continue

                datos = dict(
                    tipo=tipo,
                    placas=row.get('PLACAS', '').strip(),
                    marca=row.get('MARCA', '').strip(),
                    modelo=row.get('MODELO', '').strip(),
                    color=row.get('COLOR', '').strip(),
                    vigencia_doble_articulado=vigencia,
                    verificacion=verificacion,
                    activo=True,
                )

                if not options['dry_run']:
                    obj, created = Equipo.objects.update_or_create(
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
            f'Equipos: {creados} creados, {actualizados} actualizados, {errores} errores'
        ))
