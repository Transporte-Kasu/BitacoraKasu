"""
Script para cargar operadores desde CSV
Ubicación: apps/operadores/management/commands/load_operadores.py

Uso:
    python manage.py load_operadores ruta/al/archivo.csv
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from modulos.operadores.models import Operador
import csv
import os


class Command(BaseCommand):
    help = 'Carga operadores desde un archivo CSV'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Ruta al archivo CSV con los operadores'
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='Actualizar operadores existentes'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Eliminar todos los operadores antes de cargar'
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        update_mode = options['update']
        clear_mode = options['clear']

        # Verificar que el archivo existe
        if not os.path.exists(csv_file):
            raise CommandError(f'El archivo "{csv_file}" no existe')

        # Limpiar datos existentes si se solicita
        if clear_mode:
            confirm = input('¿Está seguro de eliminar todos los operadores? (si/no): ')
            if confirm.lower() == 'si':
                count = Operador.objects.all().count()
                Operador.objects.all().delete()
                self.stdout.write(
                    self.style.WARNING(f'Se eliminaron {count} operadores')
                )

        # Contadores
        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                # Leer el CSV
                csv_reader = csv.DictReader(file)

                with transaction.atomic():
                    for row_num, row in enumerate(csv_reader, start=2):
                        try:
                            # Limpiar y preparar datos
                            nombre = row.get('nombre', '').strip()

                            # Saltar filas vacías
                            if not nombre:
                                skipped_count += 1
                                continue

                            # Mapear tipo
                            tipo_raw = row.get('tipo', '').strip().upper()
                            tipo_map = {
                                'LOCAL': 'LOCAL',
                                'FORANEO': 'FORANEO',
                                'FORÁNEO': 'FORANEO',
                            }
                            tipo = tipo_map.get(tipo_raw, 'LOCAL')

                            # Preparar datos del operador
                            operador_data = {
                                'nombre': nombre,
                                'tipo': tipo,
                                'licencia': row.get('licencia', '').strip() or '',
                                'telefono': row.get('telefono', '').strip() or '',
                                'email': row.get('email', '').strip() or None,
                                'activo': row.get('activo', 'TRUE').strip().upper() == 'TRUE',
                            }

                            # Verificar si el operador ya existe
                            operador_exists = Operador.objects.filter(
                                nombre__iexact=nombre
                            ).first()

                            if operador_exists:
                                if update_mode:
                                    # Actualizar operador existente
                                    for key, value in operador_data.items():
                                        setattr(operador_exists, key, value)
                                    operador_exists.save()
                                    updated_count += 1
                                    self.stdout.write(
                                        self.style.SUCCESS(
                                            f'Fila {row_num}: Actualizado - {nombre}'
                                        )
                                    )
                                else:
                                    skipped_count += 1
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Fila {row_num}: Ya existe - {nombre}'
                                        )
                                    )
                            else:
                                # Crear nuevo operador
                                Operador.objects.create(**operador_data)
                                created_count += 1
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f'Fila {row_num}: Creado - {nombre}'
                                    )
                                )

                        except Exception as e:
                            error_count += 1
                            self.stdout.write(
                                self.style.ERROR(
                                    f'Fila {row_num}: Error - {str(e)}'
                                )
                            )

            # Resumen final
            self.stdout.write('\n' + '='*50)
            self.stdout.write(self.style.SUCCESS('RESUMEN DE IMPORTACIÓN'))
            self.stdout.write('='*50)
            self.stdout.write(f'Operadores creados:     {created_count}')
            self.stdout.write(f'Operadores actualizados: {updated_count}')
            self.stdout.write(f'Operadores omitidos:     {skipped_count}')
            self.stdout.write(f'Errores:                 {error_count}')
            self.stdout.write('='*50)

            if created_count > 0 or updated_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✓ Importación completada exitosamente'
                    )
                )

        except Exception as e:
            raise CommandError(f'Error al procesar el archivo: {str(e)}')