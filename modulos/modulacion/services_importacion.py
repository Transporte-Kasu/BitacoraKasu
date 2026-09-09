"""
Orquestador del import de programación de citas de LCTPC.

Recorre los correos del remitente configurado, salta los ya procesados
(`ImportacionProgramacionLCTPC.graph_message_id`), y por cada correo nuevo:
parsea el adjunto, clasifica FULL/SENCILLO y, por cada contenedor, actualiza
la Modulación activa de la terminal LCTPC o crea un stub incompleto.
Cada correo se procesa en su propia transacción y deja una fila de auditoría.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Agencia, ImportacionProgramacionLCTPC, Modulacion, TerminalPortuaria
from .services_graph import GraphError, descargar_adjunto_xls, listar_correos
from .services_lctpc import ErrorParseoLCTPC, clasificar, parsear_programacion

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


def _procesar_renglon(r, terminal, fecha):
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
        agencia = Agencia.objects.get_or_create(nombre='POR DEFINIR')[0]
        m = Modulacion.objects.create(
            agencia=agencia,
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


def _procesar_correo(correo, resumen):
    try:
        xls = descargar_adjunto_xls(correo.id)
        prog = parsear_programacion(xls, correo.asunto)
        clasificar(prog.renglones)
    except (GraphError, ErrorParseoLCTPC) as exc:
        ImportacionProgramacionLCTPC.objects.create(
            graph_message_id=correo.id,
            asunto=correo.asunto,
            fecha_recibido=correo.recibido or timezone.now(),
            estado='ERROR',
            mensaje_error=str(exc)[:2000],
        )
        resumen.correos_con_error += 1
        logger.warning('Correo LCTPC %s con error: %s', correo.id, exc)
        return

    with transaction.atomic():
        terminal = TerminalPortuaria.objects.get_or_create(
            nombre=settings.MODULACION_TERMINAL_LCTPC
        )[0]
        detalle = []
        for r in prog.renglones:
            fila = _procesar_renglon(r, terminal, prog.fecha)
            detalle.append(fila)
            if fila['resultado'] == 'CREADA':
                resumen.creadas += 1
            elif fila['resultado'] == 'ACTUALIZADA_AMBIGUA':
                resumen.actualizadas += 1
                resumen.ambiguas += 1
            else:
                resumen.actualizadas += 1

        hay_ambiguas = any(f['resultado'] == 'ACTUALIZADA_AMBIGUA' for f in detalle)
        estado = 'OK_CON_AVISOS' if (prog.avisos or hay_ambiguas) else 'OK'
        ImportacionProgramacionLCTPC.objects.create(
            graph_message_id=correo.id,
            asunto=correo.asunto,
            fecha_recibido=correo.recibido or timezone.now(),
            fecha_modulacion_aduana=prog.fecha,
            estado=estado,
            total_renglones=len(prog.renglones),
            creadas=sum(1 for f in detalle if f['resultado'] == 'CREADA'),
            actualizadas=sum(1 for f in detalle if f['resultado'].startswith('ACTUALIZADA')),
            ambiguas=sum(1 for f in detalle if f['resultado'] == 'ACTUALIZADA_AMBIGUA'),
            detalle=detalle,
            mensaje_error='\n'.join(prog.avisos),
        )
    resumen.correos_procesados += 1


def importar_programaciones_lctpc() -> ResumenImportacion:
    resumen = ResumenImportacion()
    try:
        correos = listar_correos()
    except GraphError as exc:
        logger.error('No se pudieron listar los correos de LCTPC: %s', exc)
        return resumen

    ya_vistos = set(
        ImportacionProgramacionLCTPC.objects
        .filter(graph_message_id__in=[c.id for c in correos])
        .values_list('graph_message_id', flat=True)
    )
    for correo in correos:
        if correo.id in ya_vistos:
            resumen.correos_saltados += 1
            continue
        _procesar_correo(correo, resumen)

    return resumen
