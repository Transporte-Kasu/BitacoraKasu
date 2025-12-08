"""
Comando para generar checklist por defecto para tipos de mantenimiento

Uso:
    python manage.py generar_checklist_default
"""

from django.core.management.base import BaseCommand
from modulos.taller.models import TipoMantenimiento, ChecklistMantenimiento


class Command(BaseCommand):
    help = 'Genera checklist por defecto para los tipos de mantenimiento'

    def handle(self, *args, **options):
        self.stdout.write('Generando checklist por defecto...')

        # Checklist para Servicio A (Preventivo Menor)
        servicio_a = TipoMantenimiento.objects.filter(
            nombre__icontains='Servicio A'
        ).first()

        if servicio_a:
            items_a = [
                ('Cambio de aceite de motor', 1, True),
                ('Cambio de filtro de aceite', 2, True),
                ('Cambio de filtro de aire', 3, True),
                ('Revisión de niveles de fluidos', 4, True),
                ('Inspección de frenos', 5, True),
                ('Revisión de luces', 6, True),
                ('Revisión de limpiaparabrisas', 7, False),
                ('Inspección de neumáticos', 8, True),
                ('Lubricación de chasis', 9, False),
                ('Revisión de batería', 10, True),
                ('Inspección visual de fugas', 11, True),
                ('Revisión de tensión de bandas', 12, False),
            ]

            for desc, orden, obligatorio in items_a:
                ChecklistMantenimiento.objects.get_or_create(
                    tipo_mantenimiento=servicio_a,
                    descripcion=desc,
                    defaults={
                        'orden': orden,
                        'es_obligatorio': obligatorio
                    }
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Checklist creado para {servicio_a.nombre} ({len(items_a)} items)'
                )
            )

        # Checklist para Servicio B (Preventivo Mayor)
        servicio_b = TipoMantenimiento.objects.filter(
            nombre__icontains='Servicio B'
        ).first()

        if servicio_b:
            items_b = [
                # Todos los del Servicio A más:
                ('Cambio de aceite de motor', 1, True),
                ('Cambio de filtro de aceite', 2, True),
                ('Cambio de filtro de aire', 3, True),
                ('Cambio de filtro de combustible', 4, True),
                ('Revisión de niveles de fluidos', 5, True),
                ('Cambio de líquido de frenos', 6, True),
                ('Inspección completa de frenos', 7, True),
                ('Revisión de sistema de suspensión', 8, True),
                ('Revisión de dirección', 9, True),
                ('Revisión de transmisión', 10, True),
                ('Revisión de diferencial', 11, True),
                ('Inspección de sistema de escape', 12, True),
                ('Revisión de sistema de enfriamiento', 13, True),
                ('Cambio de refrigerante (si aplica)', 14, False),
                ('Inspección de neumáticos y rotación', 15, True),
                ('Revisión de batería y sistema eléctrico', 16, True),
                ('Revisión de luces y señales', 17, True),
                ('Inspección de mangueras y conexiones', 18, True),
                ('Lubricación completa de chasis', 19, True),
                ('Revisión de tensión de bandas', 20, True),
                ('Inspección visual completa de fugas', 21, True),
                ('Prueba de funcionamiento general', 22, True),
            ]

            for desc, orden, obligatorio in items_b:
                ChecklistMantenimiento.objects.get_or_create(
                    tipo_mantenimiento=servicio_b,
                    descripcion=desc,
                    defaults={
                        'orden': orden,
                        'es_obligatorio': obligatorio
                    }
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Checklist creado para {servicio_b.nombre} ({len(items_b)} items)'
                )
            )

        # Checklist para Reparación Correctiva
        correctivo = TipoMantenimiento.objects.filter(
            tipo='CORRECTIVO'
        ).first()

        if correctivo:
            items_c = [
                ('Diagnóstico inicial del problema', 1, True),
                ('Identificación de componentes afectados', 2, True),
                ('Verificación de códigos de error (si aplica)', 3, False),
                ('Inspección visual del área afectada', 4, True),
                ('Pruebas de funcionamiento', 5, True),
                ('Desmontaje de componentes (según necesidad)', 6, False),
                ('Reparación o reemplazo de piezas', 7, True),
                ('Instalación de componentes nuevos', 8, False),
                ('Ajustes y calibraciones', 9, False),
                ('Prueba de funcionamiento post-reparación', 10, True),
                ('Verificación de ausencia de fugas', 11, True),
                ('Limpieza del área de trabajo', 12, False),
                ('Documentación de trabajo realizado', 13, True),
            ]

            for desc, orden, obligatorio in items_c:
                ChecklistMantenimiento.objects.get_or_create(
                    tipo_mantenimiento=correctivo,
                    descripcion=desc,
                    defaults={
                        'orden': orden,
                        'es_obligatorio': obligatorio
                    }
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Checklist creado para {correctivo.nombre} ({len(items_c)} items)'
                )
            )

        # Checklist genérico para Preventivo sin especificar
        preventivos = TipoMantenimiento.objects.filter(
            tipo='PREVENTIVO'
        ).exclude(
            nombre__icontains='Servicio'
        )

        for preventivo in preventivos:
            items_gen = [
                ('Revisión de niveles de fluidos', 1, True),
                ('Inspección de frenos', 2, True),
                ('Revisión de neumáticos', 3, True),
                ('Inspección de sistema eléctrico', 4, True),
                ('Revisión de luces', 5, True),
                ('Inspección visual de fugas', 6, True),
                ('Lubricación según especificaciones', 7, False),
                ('Prueba de funcionamiento', 8, True),
            ]

            for desc, orden, obligatorio in items_gen:
                ChecklistMantenimiento.objects.get_or_create(
                    tipo_mantenimiento=preventivo,
                    descripcion=desc,
                    defaults={
                        'orden': orden,
                        'es_obligatorio': obligatorio
                    }
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Checklist creado para {preventivo.nombre} ({len(items_gen)} items)'
                )
            )

        total_items = ChecklistMantenimiento.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Proceso completado. Total de items: {total_items}'
            )
        )