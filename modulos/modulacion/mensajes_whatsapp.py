"""
Construcción de los mensajes de WhatsApp del "Programa de despacho": un
texto por grupo de cliente, mismo contenido y numeración de maniobra que
el reporte xlsx (`reportes.py`). Módulo puro: no envía nada, no toca
request/response ni servicios externos.
"""
from .reportes import _agrupar_y_numerar, _fecha_es, _texto_hora


def _linea_horas(m, fecha):
    horas = [
        ('Registro', m.hora_registro),
        ('Ingreso', m.hora_ingreso),
        ('Carga', m.hora_carga),
    ]
    if not any(h for _etq, h in horas):
        return '  Horario: CITA PENDIENTE'
    return '\n'.join(
        f'  {etiqueta}: {_texto_hora(h, fecha) or "—"}' for etiqueta, h in horas
    )


def _bloque_maniobra(numero, m, fecha):
    operador_txt = m.operador.nombre if m.operador_id else '—'
    unidad_txt = (
        f'ECO {m.unidad.numero_economico} PLACAS {m.unidad.placa}'
        if m.unidad_id else ''
    )
    operador_unidad = f'{operador_txt} {unidad_txt}'.strip() if m.operador_id or m.unidad_id else '—'

    lineas = [
        f'Maniobra Nº {numero}',
        f'  Contenedor: {m.contenedor}',
        f'  Terminal: {m.terminal_portuaria.etiqueta if m.terminal_portuaria_id else "—"}',
        f'  Agencia: {m.agencia.nombre if m.agencia_id else "—"}',
        f'  Tipo: {m.tipo_contenedor or "—"}   Peso: {m.peso_toneladas if m.peso_toneladas is not None else "—"} t',
        f'  Operador/Unidad: {operador_unidad}',
        f'  Carril: {m.carril or "NA"}',
        _linea_horas(m, fecha),
        f'  Sello: {"SÍ" if m.sello_colocado else "NO"}',
    ]
    return '\n'.join(lineas)


def construir_mensajes_whatsapp(fecha):
    """
    Un (Cliente, texto) por cada grupo con cliente asignado, para la fecha
    dada. El grupo sin cliente (etiqueta '—') se omite — no hay a quién
    reenviárselo.
    """
    mensajes = []
    for etiqueta, cliente_id, items in _agrupar_y_numerar(fecha):
        if cliente_id is None:
            continue
        cliente = items[0][1].cliente
        bloques = '\n\n'.join(_bloque_maniobra(numero, m, fecha) for numero, m in items)
        partes = [
            f'*Programa de despacho — {_fecha_es(fecha)}*',
            f'*{etiqueta}* — {len(items)} maniobra(s)',
            '',
            bloques,
            '',
            '_BitacoraKasu — Modulación_',
        ]
        texto = '\n'.join(partes)
        mensajes.append((cliente, texto))
    return mensajes
