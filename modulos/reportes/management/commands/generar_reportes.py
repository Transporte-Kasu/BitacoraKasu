"""
Management command: generar_reportes

Ejecuta los reportes programados cuya fecha de ejecución ha llegado.
Diseñado para correr vía cron (GitHub Actions, DigitalOcean Scheduler, etc.):

    python manage.py generar_reportes

Flags opcionales:
    --forzar-id <id>   Ejecuta un reporte específico sin importar si es_debido()
    --dry-run          Muestra qué reportes se ejecutarían sin enviar correos
"""

import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings

from modulos.reportes.models import ConfiguracionReporte, ReporteGenerado
from modulos.reportes.generadores import almacen as gen_almacen
from modulos.reportes.generadores import combustible as gen_combustible

logger = logging.getLogger(__name__)

GENERADORES = {
    **gen_almacen.GENERADORES,
    **gen_combustible.GENERADORES,
}


def _periodo(frecuencia: str, dia_semana, dia_mes):
    """Calcula (periodo_inicio, periodo_fin) según la frecuencia del reporte."""
    hoy = timezone.now().date()
    if frecuencia == 'DIARIO':
        inicio = hoy - timedelta(days=1)
        fin = hoy - timedelta(days=1)
    elif frecuencia == 'SEMANAL':
        fin = hoy - timedelta(days=1)
        inicio = fin - timedelta(days=6)
    else:  # MENSUAL
        fin = hoy - timedelta(days=1)
        inicio = date(hoy.year, hoy.month, 1) - timedelta(days=1)
        inicio = date(inicio.year, inicio.month, 1)
    return inicio, fin


def _enviar_email(config: ConfiguracionReporte, datos: dict, dry_run: bool) -> list:
    """Envía el reporte por correo. Devuelve lista de destinatarios enviados."""
    destinatarios = config.get_destinatarios_list()
    if not destinatarios:
        logger.warning("Reporte %s sin destinatarios", config.nombre)
        return []

    if dry_run:
        logger.info("[DRY-RUN] Enviaría a: %s", ", ".join(destinatarios))
        return destinatarios

    asunto = f"[BitacoraKasu] {datos['titulo']}"
    texto_plano = f"{datos['titulo']}\n\nGenerado: {datos['generado_en']}\n\nResumen:\n"
    for k, v in datos.get('resumen', {}).items():
        texto_plano += f"  {k}: {v}\n"

    html = render_to_string('reportes/email/reporte_base.html', {'datos': datos, 'config': config})

    msg = EmailMultiAlternatives(
        subject=asunto,
        body=texto_plano,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=destinatarios,
    )
    msg.attach_alternative(html, 'text/html')
    msg.send(fail_silently=False)
    return destinatarios


class Command(BaseCommand):
    help = 'Ejecuta los reportes programados pendientes y los envía por correo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--forzar-id',
            type=int,
            metavar='ID',
            help='Ejecuta el reporte con este ID sin verificar si es_debido()',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué se ejecutaría sin enviar correos ni guardar historial',
        )

    def handle(self, *args, **options):
        forzar_id = options.get('forzar_id')
        dry_run = options.get('dry_run', False)

        if forzar_id:
            configs = ConfiguracionReporte.objects.filter(id=forzar_id, activo=True)
        else:
            configs = ConfiguracionReporte.objects.filter(activo=True)

        ejecutados = 0
        errores = 0

        for config in configs:
            if not forzar_id and not config.es_debido():
                self.stdout.write(f"  SKIP  {config.nombre} (no es su momento)")
                continue

            generador = GENERADORES.get(config.tipo_reporte)
            if not generador:
                self.stderr.write(f"  ERROR {config.nombre}: sin generador para '{config.tipo_reporte}'")
                errores += 1
                continue

            periodo_inicio, periodo_fin = _periodo(config.frecuencia, config.dia_semana, config.dia_mes)

            self.stdout.write(f"  RUN   {config.nombre} ({periodo_inicio} → {periodo_fin})")

            try:
                datos = generador(periodo_inicio, periodo_fin)
                enviados = _enviar_email(config, datos, dry_run)

                if not dry_run:
                    ReporteGenerado.objects.create(
                        configuracion=config,
                        periodo_inicio=periodo_inicio,
                        periodo_fin=periodo_fin,
                        estado='GENERADO',
                        destinatarios_enviados=', '.join(enviados),
                        resumen=datos.get('resumen', {}),
                    )
                    config.ultimo_envio = timezone.now()
                    config.save(update_fields=['ultimo_envio'])

                ejecutados += 1
                self.stdout.write(self.style.SUCCESS(f"  OK    {config.nombre}"))

            except Exception as exc:
                logger.exception("Error generando reporte %s", config.nombre)
                errores += 1
                if not dry_run:
                    ReporteGenerado.objects.create(
                        configuracion=config,
                        periodo_inicio=periodo_inicio,
                        periodo_fin=periodo_fin,
                        estado='ERROR',
                        mensaje_error=str(exc),
                    )
                self.stderr.write(self.style.ERROR(f"  FAIL  {config.nombre}: {exc}"))

        self.stdout.write(f"\nEjecutados: {ejecutados}  Errores: {errores}")
