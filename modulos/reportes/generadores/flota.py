"""Generadores de datos para reportes de Flota (dollys, equipos, cajas secas)."""

from datetime import date, timedelta
from django.utils import timezone

DIAS_ALERTA_VENCIMIENTO = 30


def _estado_vigencia(vigencia, hoy):
    """Clasifica una fecha de vigencia contra hoy. Devuelve (estado, dias_restantes)."""
    if not vigencia:
        return 'SIN_DATO', None
    dias = (vigencia - hoy).days
    if dias < 0:
        return 'VENCIDO', dias
    if dias <= DIAS_ALERTA_VENCIMIENTO:
        return 'POR_VENCER', dias
    return 'VIGENTE', dias


def generar_vigencias_flota(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de vigencias de equipos (doble articulado) y catálogo de dollys/cajas secas.

    Es un snapshot del estado actual (no depende del período), pero acepta
    los parámetros de período para mantener la firma estándar del sistema.

    Dollys y Cajas Secas aún no tienen campos de vigencia en el modelo, así que
    se listan sin datos de vencimiento hasta que se agreguen esos campos.
    """
    from modulos.equipos.models import Equipo
    from modulos.dollys.models import Dolly
    from modulos.caja_seca.models import CajaSeca

    hoy = timezone.now().date()
    orden_estado = {'VENCIDO': 0, 'POR_VENCER': 1, 'SIN_DATO': 2, 'VIGENTE': 3}

    filas_equipos = []
    for e in Equipo.objects.filter(activo=True).order_by('numero_economico'):
        estado, dias = _estado_vigencia(e.vigencia_doble_articulado, hoy)
        filas_equipos.append({
            'tipo_equipo': 'Equipo',
            'numero_economico': e.numero_economico,
            'marca': e.marca or '—',
            'modelo': e.modelo or '—',
            'placas': e.placas or '—',
            'numero_serie': e.numero_serie,
            'vigencia_doble_articulado': str(e.vigencia_doble_articulado) if e.vigencia_doble_articulado else 'Sin dato',
            'dias_restantes': dias if dias is not None else '',
            'estado_vigencia': estado,
        })
    filas_equipos.sort(key=lambda f: (orden_estado[f['estado_vigencia']], f['dias_restantes'] if f['dias_restantes'] != '' else 0))

    filas_dollys = [
        {
            'tipo_equipo': 'Dolly',
            'numero_economico': d.numero_economico,
            'marca': d.marca or '—',
            'modelo': '—',
            'placas': '—',
            'numero_serie': d.numero_serie,
            'vigencia_doble_articulado': '—',
            'dias_restantes': '',
            'estado_vigencia': 'N/A',
        }
        for d in Dolly.objects.filter(activo=True).order_by('numero_economico')
    ]

    filas_cajas = [
        {
            'tipo_equipo': 'Caja Seca',
            'numero_economico': c.numero_economico,
            'marca': c.marca or '—',
            'modelo': c.modelo or '—',
            'placas': c.placas or '—',
            'numero_serie': c.numero_serie,
            'vigencia_doble_articulado': '—',
            'dias_restantes': '',
            'estado_vigencia': 'N/A',
        }
        for c in CajaSeca.objects.filter(activo=True).order_by('numero_economico')
    ]

    filas = filas_equipos + filas_dollys + filas_cajas

    total_equipos = len(filas_equipos)
    equipos_con_vigencia = sum(1 for f in filas_equipos if f['estado_vigencia'] != 'SIN_DATO')
    equipos_vencidos = sum(1 for f in filas_equipos if f['estado_vigencia'] == 'VENCIDO')
    equipos_por_vencer = sum(1 for f in filas_equipos if f['estado_vigencia'] == 'POR_VENCER')
    equipos_sin_dato = sum(1 for f in filas_equipos if f['estado_vigencia'] == 'SIN_DATO')

    return {
        'tipo': 'FLOTA_VIGENCIAS',
        'titulo': 'Vigencias de Flota — Dollys, Equipos y Cajas Secas',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_equipos': total_equipos,
            'equipos_con_vigencia': equipos_con_vigencia,
            'equipos_vencidos': equipos_vencidos,
            'equipos_por_vencer_30d': equipos_por_vencer,
            'equipos_sin_dato': equipos_sin_dato,
            'total_dollys': len(filas_dollys),
            'total_cajas_secas': len(filas_cajas),
        },
        'filas': filas,
    }


# Mapa tipo_reporte → función generadora
GENERADORES = {
    'FLOTA_VIGENCIAS': generar_vigencias_flota,
}
