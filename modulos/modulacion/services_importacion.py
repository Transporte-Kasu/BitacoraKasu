"""
Orquestador del import de programación de citas de LCTPC.

Recorre los correos del remitente configurado, salta los ya procesados
CON ÉXITO (`ImportacionProgramacionLCTPC` en estado OK / OK_CON_AVISOS); los
que quedaron en ERROR se reintentan en cada corrida hasta que salgan bien.
Por cada correo a procesar: parsea el adjunto, clasifica FULL/SENCILLO y, por
cada contenedor, actualiza la Modulación activa de la terminal LCTPC o crea un
stub incompleto. Cada correo se procesa en su propia transacción y deja (o
reescribe) una fila de auditoría.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Agencia, ImportacionProgramacionLCTPC, Modulacion, TerminalPortuaria
from .services_graph import GraphError, descargar_adjunto_xls, listar_correos
from .services_lctpc import clasificar, parsear_programacion

logger = logging.getLogger('modulos.modulacion')

_ESTADOS_CERRADOS = ('ENVIADO_BITACORA', 'RETIRADO_TERCERO')


@dataclass
class ResumenImportacion:
    correos_procesados: int = 0
    correos_saltados: int = 0
    correos_con_error: int = 0
    creadas: int = 0
    actualizadas: int = 0
    ambiguas: int = 0
    # Mensaje de la falla al listar el buzón (Graph caído / token muerto). Si
    # está poblado, no se llegó a procesar ningún correo y la UI debe avisarlo.
    error_listado: str = ''


def _aware(fecha, hora):
    return timezone.make_aware(datetime.combine(fecha, hora))


def _linea_observacion(r):
    return (
        f'Cita LCTPC {r.folio_lctpc} — reg {r.registro_inicio:%H:%M} / '
        f'cita {r.cita_inicio:%H:%M} ({r.tipo_cita})'
    )


def _anexar_observacion(modulacion, r):
    linea = _linea_observacion(r)
    if linea in (modulacion.observaciones or '').splitlines():
        return
    modulacion.observaciones = (
        f'{modulacion.observaciones}\n{linea}'.strip()
        if modulacion.observaciones else linea
    )


def _procesar_renglon(r, terminal, fecha, agencia_defecto):
    hora_reg = _aware(fecha, r.registro_inicio)
    hora_ing = _aware(fecha, r.cita_inicio)

    qs = (
        Modulacion.objects
        .filter(terminal_portuaria=terminal, contenedor=r.contenedor)
        .exclude(estado__in=_ESTADOS_CERRADOS)
        .order_by('-fecha_recepcion')
    )
    m = qs.first()
    if m:
        m.fecha_modulacion_aduana = fecha
        m.hora_registro = hora_reg
        m.hora_ingreso = hora_ing
        m.tipo_cita = r.tipo_cita
        m.grupo_cita = r.grupo_cita
        _anexar_observacion(m, r)
        m.save()
        resultado = 'ACTUALIZADA_AMBIGUA' if qs.count() > 1 else 'ACTUALIZADA'
    else:
        m = Modulacion.objects.create(
            agencia=agencia_defecto,
            terminal_portuaria=terminal,
            tipo_contenedor='',
            peso_toneladas=Decimal('0'),
            contenedor=r.contenedor,
            cliente=None,
            origen='LCTPC',
            estado='PENDIENTE',
            fecha_modulacion_aduana=fecha,
            hora_registro=hora_reg,
            hora_ingreso=hora_ing,
            tipo_cita=r.tipo_cita,
            grupo_cita=r.grupo_cita,
            observaciones=(
                'Creada desde programación LCTPC — faltan agencia/cliente/tipo/peso.\n'
                + _linea_observacion(r)
            ),
        )
        resultado = 'CREADA'

    return {
        'contenedor': r.contenedor,
        'folio_lctpc': r.folio_lctpc,
        'resultado': resultado,
        'modulacion_id': m.id,
        'tipo_cita': r.tipo_cita,
    }


def _fila_error(correo, mensaje):
    """Crea la fila de auditoría ERROR. Debe llamarse FUERA de cualquier
    `atomic()` que se haya revertido, para que la auditoría sí persista.

    Si el correo ya tenía fila:
      - en ERROR (reintento que vuelve a fallar): se refresca el mensaje;
      - en OK / OK_CON_AVISOS (otra corrida ya lo procesó bien): NO se degrada,
        solo se avisa.
    Una carrera entre corridas puede hacer fallar el `get_or_create` con
    `IntegrityError`; ese caso se traga con un warning.
    """
    defaults = {
        'asunto': correo.asunto,
        'fecha_recibido': correo.recibido or timezone.now(),
        'estado': 'ERROR',
        'mensaje_error': str(mensaje)[:2000],
        'fecha_modulacion_aduana': None,
        'total_renglones': 0,
        'creadas': 0,
        'actualizadas': 0,
        'ambiguas': 0,
        'detalle': [],
    }
    try:
        with transaction.atomic():
            fila, creada = ImportacionProgramacionLCTPC.objects.get_or_create(
                graph_message_id=correo.id, defaults=defaults,
            )
            if creada:
                return
            if fila.estado == 'ERROR':
                for campo, valor in defaults.items():
                    setattr(fila, campo, valor)
                fila.save()
            else:
                logger.warning(
                    'Correo %s ya tiene fila en estado %s; no se degrada a ERROR',
                    correo.id, fila.estado,
                )
    except IntegrityError:
        logger.warning('Fila de auditoría duplicada para %s', correo.id)


def _procesar_correo(correo, resumen):
    try:
        xls = descargar_adjunto_xls(correo.id)
        prog = parsear_programacion(xls, correo.asunto)
        clasificar(prog.renglones)

        # Búsqueda estricta: nunca crear la terminal. Un nombre que no cuadra
        # con el setting es un error de configuración, no un caso a inventar.
        try:
            terminal = TerminalPortuaria.objects.get(
                nombre__iexact=settings.MODULACION_TERMINAL_LCTPC
            )
        except TerminalPortuaria.DoesNotExist:
            _fila_error(
                correo,
                f"No existe la TerminalPortuaria "
                f"'{settings.MODULACION_TERMINAL_LCTPC}' (revisar el setting "
                f"MODULACION_TERMINAL_LCTPC).",
            )
            resumen.correos_con_error += 1
            logger.error(
                'Correo LCTPC %s: no existe la TerminalPortuaria %r',
                correo.id, settings.MODULACION_TERMINAL_LCTPC,
            )
            return

        agencia_defecto = Agencia.objects.get_or_create(nombre='POR DEFINIR')[0]

        with transaction.atomic():
            detalle = []
            for r in prog.renglones:
                detalle.append(_procesar_renglon(r, terminal, prog.fecha, agencia_defecto))

            hay_ambiguas = any(f['resultado'] == 'ACTUALIZADA_AMBIGUA' for f in detalle)
            estado = 'OK_CON_AVISOS' if (prog.avisos or hay_ambiguas) else 'OK'
            creadas = sum(1 for f in detalle if f['resultado'] == 'CREADA')
            actualizadas = sum(1 for f in detalle if f['resultado'].startswith('ACTUALIZADA'))
            ambiguas = sum(1 for f in detalle if f['resultado'] == 'ACTUALIZADA_AMBIGUA')
            ImportacionProgramacionLCTPC.objects.update_or_create(
                graph_message_id=correo.id,
                defaults={
                    'asunto': correo.asunto,
                    'fecha_recibido': correo.recibido or timezone.now(),
                    'fecha_modulacion_aduana': prog.fecha,
                    'estado': estado,
                    'total_renglones': len(prog.renglones),
                    'creadas': creadas,
                    'actualizadas': actualizadas,
                    'ambiguas': ambiguas,
                    'detalle': detalle,
                    'mensaje_error': '\n'.join(prog.avisos),
                },
            )
    except Exception as exc:  # noqa: BLE001 — un correo malo no debe tumbar el lote
        # La fila ERROR se escribe aquí, ya fuera del atomic() revertido.
        _fila_error(correo, exc)
        resumen.correos_con_error += 1
        logger.exception('Correo LCTPC %s con error: %s', correo.id, exc)
        return

    # Contadores derivados de `detalle`, plegados al resumen SOLO si la
    # transacción cerró bien (si hubo rollback nunca llegamos hasta aquí).
    resumen.correos_procesados += 1
    resumen.creadas += creadas
    resumen.actualizadas += actualizadas
    resumen.ambiguas += ambiguas


def importar_programaciones_lctpc() -> ResumenImportacion:
    resumen = ResumenImportacion()
    try:
        correos = listar_correos()
    except GraphError as exc:
        logger.error('No se pudieron listar los correos de LCTPC: %s', exc)
        resumen.error_listado = str(exc)[:500]
        return resumen

    # Solo se saltan los ya procesados CON ÉXITO; un ERROR previo se reintenta.
    ya_vistos = set(
        ImportacionProgramacionLCTPC.objects
        .filter(
            graph_message_id__in=[c.id for c in correos],
            estado__in=('OK', 'OK_CON_AVISOS'),
        )
        .values_list('graph_message_id', flat=True)
    )
    for correo in correos:
        if correo.id in ya_vistos:
            resumen.correos_saltados += 1
            continue
        _procesar_correo(correo, resumen)

    return resumen
