"""
Management command: reenviar_reporte_wa

Reenvía uno o más reportes por WhatsApp sin volver a enviar email.

Modos de uso:

  # Listar reportes disponibles con sus IDs
  python manage.py reenviar_reporte_wa --listar

  # Reenviar desde datos ya guardados (ReporteGenerado ID)
  python manage.py reenviar_reporte_wa --reporte-id 12

  # Regenerar datos frescos y enviar solo por WhatsApp
  python manage.py reenviar_reporte_wa --config-id 3

  # Vista previa sin enviar
  python manage.py reenviar_reporte_wa --reporte-id 12 --dry-run
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from modulos.reportes.models import ConfiguracionReporte, ReporteGenerado
from modulos.reportes.generadores import almacen as gen_almacen
from modulos.reportes.generadores import combustible as gen_combustible
from modulos.reportes.generadores import unidades as gen_unidades
from config.services.whatsapp_service import enviar_mensaje as _wa_enviar

logger = logging.getLogger(__name__)

GENERADORES = {
    **gen_almacen.GENERADORES,
    **gen_combustible.GENERADORES,
    **gen_unidades.GENERADORES,
}


def _enviar_wa(config: ConfiguracionReporte, datos: dict, narrativa: str, dry_run: bool) -> bool:
    numeros = getattr(settings, 'WA_ALLOWED_NUMBERS', [])
    if not numeros:
        raise CommandError("WA_ALLOWED_NUMBERS está vacío — configura los números en .env")

    frecuencia_label = {
        'DIARIO': 'Diario', 'SEMANAL': 'Semanal', 'MENSUAL': 'Mensual',
    }.get(config.frecuencia, config.frecuencia)

    lineas = [
        f"📊 *Reporte {frecuencia_label} — BitacoraKasu*",
        f"*{datos.get('titulo', config.nombre)}*",
        f"Período: {datos.get('periodo_inicio', '')} → {datos.get('periodo_fin', '')}",
        "",
    ]

    resumen = datos.get('resumen', {})
    if resumen:
        lineas.append("*Resumen:*")
        for k, v in resumen.items():
            etiqueta = k.replace('_', ' ').title()
            lineas.append(f"  • {etiqueta}: {v}")
        lineas.append("")

    if narrativa:
        narrativa_corta = narrativa[:600] + ('…' if len(narrativa) > 600 else '')
        lineas += ["*Análisis IAKasu:*", narrativa_corta, ""]

    lineas.append("_BitacoraKasu — Sistema de Gestión de Flota_")

    mensaje = '\n'.join(lineas)

    if dry_run:
        return True

    return _wa_enviar(mensaje, numeros=numeros)


class Command(BaseCommand):
    help = 'Reenvía un reporte por WhatsApp sin volver a enviar email.'

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group(required=True)
        grupo.add_argument(
            '--listar',
            action='store_true',
            help='Muestra todos los reportes configurados y el historial reciente',
        )
        grupo.add_argument(
            '--reporte-id',
            type=int,
            metavar='ID',
            help='ID de ReporteGenerado — reenvía desde los datos ya guardados',
        )
        grupo.add_argument(
            '--config-id',
            type=int,
            metavar='ID',
            help='ID de ConfiguracionReporte — regenera datos frescos y envía por WA',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué se enviaría sin enviar nada',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)

        if options['listar']:
            self._cmd_listar()
            return

        if options['reporte_id']:
            self._cmd_desde_historial(options['reporte_id'], dry_run)
            return

        if options['config_id']:
            self._cmd_regenerar(options['config_id'], dry_run)

    # ------------------------------------------------------------------
    # Modo --listar
    # ------------------------------------------------------------------

    def _cmd_listar(self):
        self.stdout.write(self.style.HTTP_INFO('\n=== Configuraciones de Reporte ===\n'))
        configs = ConfiguracionReporte.objects.filter(activo=True).order_by('modulo', 'nombre')
        if not configs.exists():
            self.stdout.write('  Sin configuraciones activas.')
            return

        for cfg in configs:
            ultimo = cfg.ultimo_envio.strftime('%d/%m/%Y %H:%M') if cfg.ultimo_envio else 'nunca'
            self.stdout.write(
                f"  config-id={cfg.pk:>3}  [{cfg.get_frecuencia_display():<8}]  "
                f"{cfg.nombre}  (último envío: {ultimo})"
            )

        self.stdout.write(self.style.HTTP_INFO('\n=== Últimos 10 Reportes Generados ===\n'))
        reportes = ReporteGenerado.objects.select_related('configuracion').order_by('-fecha_generacion')[:10]
        if not reportes.exists():
            self.stdout.write('  Sin historial.')
            return

        for r in reportes:
            fecha = r.fecha_generacion.strftime('%d/%m/%Y %H:%M')
            self.stdout.write(
                f"  reporte-id={r.pk:>4}  {fecha}  [{r.estado}]  "
                f"{r.configuracion.nombre}  "
                f"({r.periodo_inicio} → {r.periodo_fin})"
            )
        self.stdout.write('')

    # ------------------------------------------------------------------
    # Modo --reporte-id: usa datos guardados en ReporteGenerado
    # ------------------------------------------------------------------

    def _cmd_desde_historial(self, reporte_id: int, dry_run: bool):
        try:
            reporte = ReporteGenerado.objects.select_related('configuracion').get(pk=reporte_id)
        except ReporteGenerado.DoesNotExist:
            raise CommandError(f"No existe ReporteGenerado con id={reporte_id}. Usa --listar para ver IDs válidos.")

        config = reporte.configuracion

        datos = {
            'titulo': config.nombre,
            'periodo_inicio': str(reporte.periodo_inicio),
            'periodo_fin': str(reporte.periodo_fin),
            'resumen': reporte.resumen or {},
        }
        narrativa = reporte.narrativa_ia or ''

        prefijo = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(
            f"{prefijo}Reenviando reporte-id={reporte_id} — '{config.nombre}' "
            f"({reporte.periodo_inicio} → {reporte.periodo_fin})"
        )

        ok = _enviar_wa(config, datos, narrativa, dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] No se envió nada.'))
        elif ok:
            self.stdout.write(self.style.SUCCESS('✓ Reporte enviado por WhatsApp.'))
        else:
            raise CommandError('Error al enviar por WhatsApp. Revisa los logs para más detalle.')

    # ------------------------------------------------------------------
    # Modo --config-id: regenera datos frescos
    # ------------------------------------------------------------------

    def _cmd_regenerar(self, config_id: int, dry_run: bool):
        try:
            config = ConfiguracionReporte.objects.get(pk=config_id, activo=True)
        except ConfiguracionReporte.DoesNotExist:
            raise CommandError(
                f"No existe ConfiguracionReporte activa con id={config_id}. Usa --listar para ver IDs válidos."
            )

        generador = GENERADORES.get(config.tipo_reporte)
        if not generador:
            raise CommandError(f"Sin generador para tipo '{config.tipo_reporte}'.")

        from modulos.reportes.management.commands.generar_reportes import _periodo
        from modulos.reportes.generadores.narrativa import generar_narrativa

        periodo_inicio, periodo_fin = _periodo(config.frecuencia, config.dia_semana, config.dia_mes)

        prefijo = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(
            f"{prefijo}Regenerando '{config.nombre}' ({periodo_inicio} → {periodo_fin})..."
        )

        datos = generador(periodo_inicio, periodo_fin)

        narrativa = generar_narrativa(
            tipo_reporte=config.tipo_reporte,
            resumen=datos.get('resumen', {}),
            periodo_inicio=str(periodo_inicio),
            periodo_fin=str(periodo_fin),
            datos=datos,
        )
        if narrativa:
            self.stdout.write('  Narrativa IAKasu generada.')

        ok = _enviar_wa(config, datos, narrativa, dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] No se envió nada.'))
        elif ok:
            self.stdout.write(self.style.SUCCESS('✓ Reporte enviado por WhatsApp.'))
        else:
            raise CommandError('Error al enviar por WhatsApp. Revisa los logs para más detalle.')
