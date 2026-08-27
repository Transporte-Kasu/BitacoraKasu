"""Generadores de datos para reportes del módulo Modulación."""

from collections import defaultdict
from datetime import date, timedelta

from django.utils import timezone

_MESES_ABREV = [
    '', 'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
]


def _rango_semana_iso(anio_iso: int, semana_iso: int) -> tuple:
    """Devuelve (lunes, domingo) como date para una semana ISO dada."""
    lunes = date.fromisocalendar(anio_iso, semana_iso, 1)
    return lunes, lunes + timedelta(days=6)


def _etiqueta_semana(anio_iso: int, semana_iso: int) -> str:
    """Ej. '2026-W35 (25 ago – 31 ago)'."""
    lunes, domingo = _rango_semana_iso(anio_iso, semana_iso)
    return (
        f"{anio_iso}-W{semana_iso:02d} "
        f"({lunes.day} {_MESES_ABREV[lunes.month]} – {domingo.day} {_MESES_ABREV[domingo.month]})"
    )


def generar_contenedores_por_operador(periodo_inicio: date, periodo_fin: date) -> dict:
    """Contenedores extraídos por cada operador local en el período, por semana ISO.

    "Extraído" = modulación con `fecha_retiro` dentro del rango y con
    `operador` asignado (vía la acción "Asignar unidad y operador" del módulo
    de modulación). Las modulaciones sin operador asignado no cuentan.
    """
    from modulos.modulacion.models import Modulacion

    modulaciones = (
        Modulacion.objects
        .filter(
            fecha_retiro__date__gte=periodo_inicio,
            fecha_retiro__date__lte=periodo_fin,
            operador__isnull=False,
        )
        .select_related('operador')
    )

    # (operador, anio_iso, semana_iso) -> conteo
    por_operador_semana = defaultdict(int)
    # operador -> conteo total del período
    por_operador_total = defaultdict(int)
    semanas_vistas = {}

    for m in modulaciones:
        local = timezone.localtime(m.fecha_retiro)
        anio_iso, semana_iso, _ = local.isocalendar()
        nombre = m.operador.nombre
        por_operador_semana[(nombre, anio_iso, semana_iso)] += 1
        por_operador_total[nombre] += 1
        semanas_vistas[(anio_iso, semana_iso)] = _etiqueta_semana(anio_iso, semana_iso)

    filas = [
        {
            'operador': nombre,
            'semana': semanas_vistas[(anio_iso, semana_iso)],
            'contenedores': conteo,
        }
        for (nombre, anio_iso, semana_iso), conteo in sorted(
            por_operador_semana.items(),
            key=lambda kv: (kv[0][1], kv[0][2], -kv[1], kv[0][0]),
        )
    ]

    totales_operador = [
        {'operador': nombre, 'contenedores': conteo}
        for nombre, conteo in sorted(
            por_operador_total.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]

    total_contenedores = sum(por_operador_total.values())
    operadores_activos = len(por_operador_total)
    promedio_por_operador = (
        round(total_contenedores / operadores_activos, 2) if operadores_activos else 0
    )
    operador_top = totales_operador[0]['operador'] if totales_operador else '—'
    contenedores_operador_top = totales_operador[0]['contenedores'] if totales_operador else 0

    return {
        'tipo': 'MODULACION_CONTENEDORES_OPERADOR',
        'titulo': (
            f'Contenedores extraídos por operador — '
            f'{periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}'
        ),
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_contenedores': total_contenedores,
            'operadores_activos': operadores_activos,
            'operador_top': operador_top,
            'contenedores_operador_top': contenedores_operador_top,
            'promedio_por_operador': promedio_por_operador,
        },
        'filas': filas,
        'totales_operador': totales_operador,
        'tablas': {
            'Por operador y semana': filas,
            'Totales por operador': totales_operador,
        },
    }


# Mapa tipo_reporte → función generadora
GENERADORES = {
    'MODULACION_CONTENEDORES_OPERADOR': generar_contenedores_por_operador,
}
