"""
Comando para probar los reportes automáticos sin esperar al scheduler.

Uso:
    # Probar ambos reportes
    python manage.py test_reportes

    # Probar solo uno
    python manage.py test_reportes --reporte almacen
    python manage.py test_reportes --reporte combustible

    # Solo generar el Excel (sin enviar correo)
    python manage.py test_reportes --solo-excel

    # Enviar a un correo diferente al configurado
    python manage.py test_reportes --correo tu@email.com

    # Simular período específico (para revisar datos históricos)
    python manage.py test_reportes --periodicidad mensual
    python manage.py test_reportes --periodicidad diario
"""
import io
import os

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone


REPORTES_DISPONIBLES = ['almacen', 'combustible']


class Command(BaseCommand):
    help = 'Prueba los reportes automáticos: genera el Excel y/o envía el correo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reporte',
            choices=REPORTES_DISPONIBLES,
            default=None,
            help='Reporte a probar. Sin este argumento se prueban ambos.',
        )
        parser.add_argument(
            '--solo-excel',
            action='store_true',
            default=False,
            help='Solo genera el Excel y lo guarda en /tmp, sin enviar correo.',
        )
        parser.add_argument(
            '--correo',
            default=None,
            help='Enviar el reporte a este correo en lugar de los configurados.',
        )
        parser.add_argument(
            '--periodicidad',
            choices=['diario', 'semanal', 'mensual'],
            default=None,
            help='Sobreescribe la periodicidad configurada para esta prueba.',
        )

    def handle(self, *args, **options):
        reportes = (
            [options['reporte']] if options['reporte']
            else REPORTES_DISPONIBLES
        )

        for nombre in reportes:
            self.stdout.write('')
            self.stdout.write(self.style.HTTP_INFO(f'=== Reporte: {nombre.upper()} ==='))

            if nombre == 'almacen':
                self._probar_almacen(options)
            elif nombre == 'combustible':
                self._probar_combustible(options)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Prueba finalizada.'))

    # ── Almacén ──────────────────────────────────────────────────────────────

    def _probar_almacen(self, options):
        from config.reportes.almacen import (
            _get_periodo, generar_excel_almacen, enviar_reporte_almacen
        )

        cfg = getattr(settings, 'REPORTES_CONFIG', {}).get('almacen', {})
        periodicidad = options['periodicidad'] or cfg.get('periodicidad', 'semanal')

        fecha_inicio, fecha_fin, label = _get_periodo(periodicidad)
        self.stdout.write(f'  Periodo    : {label}')
        self.stdout.write(f'  Desde      : {fecha_inicio.strftime("%d/%m/%Y %H:%M")}')
        self.stdout.write(f'  Hasta      : {fecha_fin.strftime("%d/%m/%Y %H:%M")}')
        self.stdout.write(f'  Periodicidad: {periodicidad}')

        # Contar registros
        from modulos.almacen.models import SalidaAlmacen, SalidaRapidaConsumible
        total_salidas = SalidaAlmacen.objects.filter(
            fecha_salida__range=(fecha_inicio, fecha_fin)
        ).count()
        total_rapidas = SalidaRapidaConsumible.objects.filter(
            fecha_salida__range=(fecha_inicio, fecha_fin)
        ).count()
        self.stdout.write(f'  Salidas almacen encontradas : {total_salidas}')
        self.stdout.write(f'  Salidas rapidas encontradas : {total_rapidas}')

        # Preview del cuerpo del correo
        self.stdout.write('')
        self.stdout.write('  ── Preview del cuerpo del correo ──')
        try:
            from config.reportes.almacen import generar_cuerpo_reporte
            cuerpo = generar_cuerpo_reporte(fecha_inicio, fecha_fin, label)
            for linea in cuerpo.splitlines():
                self.stdout.write(f'  {linea}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ERROR generando cuerpo: {e}'))
            return
        self.stdout.write('')

        # Generar Excel
        self.stdout.write('  Generando Excel...')
        try:
            excel = generar_excel_almacen(fecha_inicio, fecha_fin)
            size_kb = round(len(excel.getvalue()) / 1024, 1)
            self.stdout.write(self.style.SUCCESS(f'  Excel generado: {size_kb} KB'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ERROR generando Excel: {e}'))
            return

        if options['solo_excel']:
            ruta = f'/tmp/test_reporte_almacen_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            with open(ruta, 'wb') as f:
                f.write(excel.getvalue())
            self.stdout.write(self.style.SUCCESS(f'  Excel guardado en: {ruta}'))
            return

        # Enviar correo
        self._enviar_excel(
            nombre_reporte='almacen',
            label=label,
            excel=excel,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            correo_override=options['correo'],
            cfg=cfg,
            options=options,
            cuerpo_extra=cuerpo,
        )

    # ── Combustible ──────────────────────────────────────────────────────────

    def _probar_combustible(self, options):
        from config.reportes.combustible import (
            _get_periodo, generar_excel_combustible, generar_cuerpo_reporte
        )
        from modulos.combustible.models import CargaCombustible

        cfg = getattr(settings, 'REPORTES_CONFIG', {}).get('combustible', {})
        periodicidad = options['periodicidad'] or cfg.get('periodicidad', 'mensual')

        fecha_inicio, fecha_fin, label = _get_periodo(periodicidad)
        self.stdout.write(f'  Periodo    : {label}')
        self.stdout.write(f'  Desde      : {fecha_inicio.strftime("%d/%m/%Y %H:%M")}')
        self.stdout.write(f'  Hasta      : {fecha_fin.strftime("%d/%m/%Y %H:%M")}')
        self.stdout.write(f'  Periodicidad: {periodicidad}')

        total_cargas = CargaCombustible.objects.filter(
            fecha_hora_inicio__range=(fecha_inicio, fecha_fin),
            estado='COMPLETADO'
        ).count()
        self.stdout.write(f'  Cargas completadas encontradas: {total_cargas}')

        # Mostrar preview del cuerpo del correo
        self.stdout.write('')
        self.stdout.write('  ── Preview del cuerpo del correo ──')
        try:
            cuerpo = generar_cuerpo_reporte(fecha_inicio, fecha_fin, label)
            for linea in cuerpo.splitlines():
                self.stdout.write(f'  {linea}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ERROR generando cuerpo: {e}'))
            return

        # Generar Excel
        self.stdout.write('')
        self.stdout.write('  Generando Excel...')
        try:
            excel = generar_excel_combustible(fecha_inicio, fecha_fin)
            size_kb = round(len(excel.getvalue()) / 1024, 1)
            self.stdout.write(self.style.SUCCESS(f'  Excel generado: {size_kb} KB'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ERROR generando Excel: {e}'))
            return

        if options['solo_excel']:
            ruta = f'/tmp/test_reporte_combustible_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            with open(ruta, 'wb') as f:
                f.write(excel.getvalue())
            self.stdout.write(self.style.SUCCESS(f'  Excel guardado en: {ruta}'))
            return

        self._enviar_excel(
            nombre_reporte='combustible',
            label=label,
            excel=excel,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            correo_override=options['correo'],
            cfg=cfg,
            options=options,
            cuerpo_extra=cuerpo,
        )

    # ── Envío ────────────────────────────────────────────────────────────────

    def _enviar_excel(self, nombre_reporte, label, excel, fecha_inicio,
                      fecha_fin, correo_override, cfg, options, cuerpo_extra=None):
        from django.core.mail import EmailMessage

        destinatarios = (
            [correo_override] if correo_override
            else cfg.get('destinatarios', [])
        )

        if not destinatarios:
            self.stdout.write(self.style.WARNING(
                '  Sin destinatarios. Usa --correo tu@email.com o configura '
                'REPORTES_CONFIG en settings.'
            ))
            return

        asunto = f'[PRUEBA] Reporte {nombre_reporte.capitalize()} — {label}'
        cuerpo = cuerpo_extra or (
            f'Reporte de prueba generado manualmente.\n\n'
            f'Periodo: {fecha_inicio.strftime("%d/%m/%Y")} — {fecha_fin.strftime("%d/%m/%Y")}\n\n'
            f'---\nSistema BitacoraKasu — Transportes Kasu'
        )
        nombre_archivo = (
            f'test_reporte_{nombre_reporte}_'
            f'{fecha_inicio.strftime("%Y%m%d")}_{fecha_fin.strftime("%Y%m%d")}.xlsx'
        )

        self.stdout.write(f'  Enviando a: {", ".join(destinatarios)}')

        email = EmailMessage(
            subject=asunto,
            body=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=destinatarios,
        )
        email.attach(
            nombre_archivo,
            excel.getvalue(),
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        try:
            email.send(fail_silently=False)
            self.stdout.write(self.style.SUCCESS(
                f'  Correo enviado a: {", ".join(destinatarios)}'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ERROR enviando correo: {e}'))
