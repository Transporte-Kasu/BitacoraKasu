"""
Management command para reprocesar OCR de fotos de candados ya guardadas.

Uso:
    python manage.py reprocesar_ocr_candados
    python manage.py reprocesar_ocr_candados --dry-run
    python manage.py reprocesar_ocr_candados --desde 2025-01-01
    python manage.py reprocesar_ocr_candados --solo-anteriores
    python manage.py reprocesar_ocr_candados --solo-nuevos
    python manage.py reprocesar_ocr_candados --reprocesar-todos  # incluye ya procesados
"""

import logging
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reprocesa OCR de fotos de candados existentes (histórico)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra cuántos registros se procesarían sin hacer cambios.',
        )
        parser.add_argument(
            '--desde',
            type=str,
            metavar='YYYY-MM-DD',
            help='Procesa solo cargas desde esta fecha (inclusive).',
        )
        parser.add_argument(
            '--solo-anteriores',
            action='store_true',
            help='Procesa solo fotos de candado anterior (CargaCombustible).',
        )
        parser.add_argument(
            '--solo-nuevos',
            action='store_true',
            help='Procesa solo fotos de candado nuevo (FotoCandadoNuevo).',
        )
        parser.add_argument(
            '--reprocesar-todos',
            action='store_true',
            help='Reprocesa incluso registros que ya tienen OCR (sobrescribe).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        reprocesar_todos = options['reprocesar_todos']
        solo_anteriores = options['solo_anteriores']
        solo_nuevos = options['solo_nuevos']
        fecha_desde = None

        if options['desde']:
            try:
                fecha_desde = datetime.strptime(options['desde'], '%Y-%m-%d').date()
            except ValueError:
                raise CommandError("Formato de fecha inválido. Use YYYY-MM-DD (ej: 2025-01-01)")

        if dry_run:
            self.stdout.write(self.style.WARNING("MODO DRY-RUN: no se guardarán cambios.\n"))

        # Verificar que pytesseract esté disponible antes de comenzar
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            raise CommandError(
                "pytesseract no está instalado. Ejecuta: pip install pytesseract\n"
                "También necesitas Tesseract OCR instalado en el sistema."
            )

        procesar_anteriores = not solo_nuevos
        procesar_nuevos = not solo_anteriores

        total_anteriores = total_nuevos = 0

        if procesar_anteriores:
            total_anteriores = self._procesar_candados_anteriores(
                fecha_desde, dry_run, reprocesar_todos
            )

        if procesar_nuevos:
            total_nuevos = self._procesar_candados_nuevos(
                fecha_desde, dry_run, reprocesar_todos
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Proceso completado{'  (dry-run)' if dry_run else ''}:\n"
            f"  Candados anteriores procesados: {total_anteriores}\n"
            f"  Fotos candado nuevo procesadas: {total_nuevos}\n"
            f"  Total: {total_anteriores + total_nuevos}"
        ))

    def _procesar_candados_anteriores(self, fecha_desde, dry_run, reprocesar_todos):
        """
        Procesa foto_candado_anterior de CargaCombustible completadas.
        Actualiza numero_candado_anterior y ejecuta verificar_ciclo_candados().
        """
        from config.services.ocr_service import leer_numero_candado
        from modulos.combustible.models import CargaCombustible
        from modulos.combustible.services import verificar_ciclo_candados

        qs = CargaCombustible.objects.filter(
            estado='COMPLETADO',
        ).exclude(foto_candado_anterior='').select_related('unidad')

        if not reprocesar_todos:
            qs = qs.filter(ocr_candado_anterior_ok=False)

        if fecha_desde:
            qs = qs.filter(fecha_hora_inicio__date__gte=fecha_desde)

        total = qs.count()
        self.stdout.write(
            f"Candados anteriores pendientes: {self.style.MIGRATE_HEADING(str(total))}"
        )

        procesados = 0
        errores = 0

        for carga in qs.iterator():
            unidad = carga.unidad.numero_economico
            self.stdout.write(
                f"  [{procesados + 1}/{total}] Carga #{carga.pk} — Unidad {unidad} "
                f"({carga.fecha_hora_inicio.strftime('%d/%m/%Y %H:%M')}) ...",
                ending=' ',
            )

            if dry_run:
                self.stdout.write(self.style.WARNING("(omitido)"))
                procesados += 1
                continue

            try:
                numero = leer_numero_candado(carga.foto_candado_anterior)
                CargaCombustible.objects.filter(pk=carga.pk).update(
                    numero_candado_anterior=numero,
                    ocr_candado_anterior_ok=True,
                )
                # Actualizar en memoria para verificar_ciclo_candados
                carga.numero_candado_anterior = numero
                carga.ocr_candado_anterior_ok = True

                if numero:
                    self.stdout.write(self.style.SUCCESS(f"OK → '{numero}'"))
                    verificar_ciclo_candados(carga)
                else:
                    self.stdout.write(self.style.WARNING("OK → (no detectado)"))

                procesados += 1

            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"ERROR: {exc}"))
                logger.exception("Error procesando carga #%s", carga.pk)
                errores += 1

        if errores:
            self.stdout.write(self.style.ERROR(f"  Errores en candados anteriores: {errores}"))

        return procesados

    def _procesar_candados_nuevos(self, fecha_desde, dry_run, reprocesar_todos):
        """
        Procesa fotos de FotoCandadoNuevo.
        Actualiza numero_candado y ocr_procesado.
        """
        from config.services.ocr_service import leer_numero_candado
        from modulos.combustible.models import FotoCandadoNuevo

        qs = FotoCandadoNuevo.objects.exclude(foto='').select_related('carga__unidad')

        if not reprocesar_todos:
            qs = qs.filter(ocr_procesado=False)

        if fecha_desde:
            qs = qs.filter(carga__fecha_hora_inicio__date__gte=fecha_desde)

        total = qs.count()
        self.stdout.write(
            f"\nFotos candado nuevo pendientes: {self.style.MIGRATE_HEADING(str(total))}"
        )

        procesados = 0
        errores = 0

        for foto in qs.iterator():
            unidad = foto.carga.unidad.numero_economico
            desc = foto.descripcion or str(foto.pk)
            self.stdout.write(
                f"  [{procesados + 1}/{total}] Foto #{foto.pk} — Unidad {unidad} '{desc}' ...",
                ending=' ',
            )

            if dry_run:
                self.stdout.write(self.style.WARNING("(omitido)"))
                procesados += 1
                continue

            try:
                numero = leer_numero_candado(foto.foto)
                FotoCandadoNuevo.objects.filter(pk=foto.pk).update(
                    numero_candado=numero,
                    ocr_procesado=True,
                )

                if numero:
                    self.stdout.write(self.style.SUCCESS(f"OK → '{numero}'"))
                else:
                    self.stdout.write(self.style.WARNING("OK → (no detectado)"))

                procesados += 1

            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"ERROR: {exc}"))
                logger.exception("Error procesando foto #%s", foto.pk)
                errores += 1

        if errores:
            self.stdout.write(self.style.ERROR(f"  Errores en fotos nuevas: {errores}"))

        return procesados
