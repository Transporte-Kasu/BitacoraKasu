"""
Comando de Django para cargar unidades desde archivo CSV
Ubicación: apps/unidades/management/commands/load_unidades.py
"""

import csv
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.unidades.models import Unidad
from decimal import Decimal
from datetime import datetime


class Command(BaseCommand):
    help = 'Carga unidades desde archivo CSV'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Ruta al archivo CSV con las unidades'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Eliminar todas las unidades existentes antes de cargar'
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        clear_existing = options['clear']

        self.stdout.write(self.style.WARNING(f'Cargando unidades desde: {csv_file}'))

        # Limpiar unidades existentes si se especifica
        if clear_existing:
            count = Unidad.objects.count()
            Unidad.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f'Se eliminaron {count} unidades existentes')
            )

        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                # Leer CSV
                csv_reader = csv.DictReader(file)

                unidades_creadas = 0
                unidades_actualizadas = 0
                errores = []

                with transaction.atomic():
                    for row_num, row in enumerate(csv_reader, start=2):
                        try:
                            # Limpiar espacios en blanco
                            numero_economico = row['numero_economico'].strip()
                            placa = row['placa'].strip()
                            tipo = row['tipo'].strip()

                            # Validar tipo
                            tipos_validos = dict(Unidad.TIPO_CHOICES)
                            if tipo not in tipos_validos:
                                errores.append(
                                    f"Fila {row_num}: Tipo '{tipo}' no válido para {numero_economico}"
                                )
                                continue

                            # Procesar campos opcionales
                            marca = row.get('marca', '').strip()
                            modelo = row.get('modelo', '').strip()

                            # Año por defecto si está vacío
                            año_str = row.get('año', '').strip()
                            año = int(año_str) if año_str else datetime.now().year

                            # Convertir campos numéricos
                            capacidad_combustible = Decimal(row['capacidad_combustible'].strip())
                            rendimiento_esperado = Decimal(row['rendimiento_esperado'].strip())
                            kilometraje_actual = int(row['kilometraje_actual'].strip())

                            # Crear o actualizar unidad
                            unidad, created = Unidad.objects.update_or_create(
                                numero_economico=numero_economico,
                                defaults={
                                    'placa': placa,
                                    'tipo': tipo,
                                    'marca': marca if marca else 'No especificada',
                                    'modelo': modelo if modelo else 'No especificado',
                                    'año': año,
                                    'capacidad_combustible': capacidad_combustible,
                                    'rendimiento_esperado': rendimiento_esperado,
                                    'kilometraje_actual': kilometraje_actual,
                                    'activa': True,
                                }
                            )

                            if created:
                                unidades_creadas += 1
                                self.stdout.write(
                                    self.style.SUCCESS(f'✓ Creada: {numero_economico} - {placa}')
                                )
                            else:
                                unidades_actualizadas += 1
                                self.stdout.write(
                                    self.style.WARNING(f'↻ Actualizada: {numero_economico} - {placa}')
                                )

                        except Exception as e:
                            error_msg = f"Fila {row_num}: Error procesando {row.get('numero_economico', 'N/A')} - {str(e)}"
                            errores.append(error_msg)
                            self.stdout.write(self.style.ERROR(f'✗ {error_msg}'))

                # Resumen
                self.stdout.write('\n' + '='*60)
                self.stdout.write(self.style.SUCCESS(f'Unidades creadas: {unidades_creadas}'))
                self.stdout.write(self.style.WARNING(f'Unidades actualizadas: {unidades_actualizadas}'))

                if errores:
                    self.stdout.write(self.style.ERROR(f'Errores: {len(errores)}'))
                    self.stdout.write('\nDetalle de errores:')
                    for error in errores:
                        self.stdout.write(self.style.ERROR(f'  - {error}'))
                else:
                    self.stdout.write(self.style.SUCCESS('✓ Sin errores'))

                self.stdout.write('='*60)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n¡Proceso completado! Total procesado: {unidades_creadas + unidades_actualizadas}'
                    )
                )

        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f'Error: No se encontró el archivo {csv_file}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error inesperado: {str(e)}')
            )