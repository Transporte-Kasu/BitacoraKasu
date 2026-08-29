"""Generadores de datos para reportes del módulo Vacíos."""

from collections import defaultdict
from datetime import date, timedelta

from django.utils import timezone

_MESES_ABREV = [
    '', 'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
]


def _rango_semana_iso(anio_iso: int, semana_iso: int) -> tuple:
    lunes = date.fromisocalendar(anio_iso, semana_iso, 1)
    return lunes, lunes + timedelta(days=6)


def _etiqueta_semana(anio_iso: int, semana_iso: int) -> str:
    lunes, domingo = _rango_semana_iso(anio_iso, semana_iso)
    return (
        f"{anio_iso}-W{semana_iso:02d} "
        f"({lunes.day} {_MESES_ABREV[lunes.month]} – {domingo.day} {_MESES_ABREV[domingo.month]})"
    )


def generar_entregas_por_operador(periodo_inicio: date, periodo_fin: date) -> dict:
    """Entregas de vacíos a la naviera por operador y semana ISO en el período.

    "Entregado" = Vacio con `fecha_entrega_naviera` dentro del rango y con
    `operador` asignado. Incluye también el conteo de cambios de operador por
    causa (por `CambioOperadorVacio.created_at` en el rango) y un snapshot de
    los vacíos que siguen sin entregar.
    """
    from modulos.vacios.models import CambioOperadorVacio, Vacio

    entregados = (
        Vacio.objects
        .filter(
            fecha_entrega_naviera__date__gte=periodo_inicio,
            fecha_entrega_naviera__date__lte=periodo_fin,
            operador__isnull=False,
        )
        .select_related('operador')
    )

    por_operador_semana = defaultdict(int)
    por_operador_total = defaultdict(int)
    semanas_vistas = {}

    for v in entregados:
        local = timezone.localtime(v.fecha_entrega_naviera)
        anio_iso, semana_iso, _ = local.isocalendar()
        nombre = v.operador.nombre
        por_operador_semana[(nombre, anio_iso, semana_iso)] += 1
        por_operador_total[nombre] += 1
        semanas_vistas[(anio_iso, semana_iso)] = _etiqueta_semana(anio_iso, semana_iso)

    filas = [
        {
            'operador': nombre,
            'semana': semanas_vistas[(anio_iso, semana_iso)],
            'entregas': conteo,
        }
        for (nombre, anio_iso, semana_iso), conteo in sorted(
            por_operador_semana.items(),
            key=lambda kv: (kv[0][1], kv[0][2], -kv[1], kv[0][0]),
        )
    ]

    totales_operador = [
        {'operador': nombre, 'entregas': conteo}
        for nombre, conteo in sorted(
            por_operador_total.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]

    # Cambios de operador por causa en el período
    cambios = (
        CambioOperadorVacio.objects
        .filter(created_at__date__gte=periodo_inicio, created_at__date__lte=periodo_fin)
    )
    causa_labels = dict(CambioOperadorVacio.CAUSA_CHOICES)
    por_causa = defaultdict(int)
    for c in cambios:
        por_causa[c.causa] += 1
    tabla_cambios = [
        {'causa': causa_labels.get(k, k), 'cantidad': v}
        for k, v in sorted(por_causa.items(), key=lambda kv: -kv[1])
    ]
    cambios_operador_total = sum(por_causa.values())

    # Snapshot de pendientes (no depende del rango)
    ahora = timezone.now()
    pendientes = (
        Vacio.objects
        .exclude(estado='ENTREGADO_NAVIERA')
        .select_related('cliente', 'operador')
        .order_by('fecha_entrega_cliente')
    )
    filas_pendientes = []
    for v in pendientes:
        dias = (ahora - v.fecha_entrega_cliente).days
        filas_pendientes.append({
            'folio': v.folio,
            'contenedor': v.contenedor,
            'cliente': v.cliente.nombre if v.cliente else '—',
            'estado': v.get_estado_display(),
            'dias_en_proceso': dias,
        })

    total_entregados = sum(por_operador_total.values())
    operadores_activos = len(por_operador_total)
    promedio_por_operador = (
        round(total_entregados / operadores_activos, 2) if operadores_activos else 0
    )
    operador_top = totales_operador[0]['operador'] if totales_operador else '—'
    entregas_operador_top = totales_operador[0]['entregas'] if totales_operador else 0

    return {
        'tipo': 'VACIOS_ENTREGAS_SEMANAL',
        'titulo': (
            f'Entregas de vacíos por operador — '
            f'{periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}'
        ),
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_entregados': total_entregados,
            'operadores_activos': operadores_activos,
            'operador_top': operador_top,
            'entregas_operador_top': entregas_operador_top,
            'promedio_por_operador': promedio_por_operador,
            'cambios_operador_total': cambios_operador_total,
            'vacios_pendientes': len(filas_pendientes),
        },
        'filas': filas,
        'tablas': {
            'Entregas por operador y semana': filas,
            'Totales por operador': totales_operador,
            'Cambios de operador por causa': tabla_cambios,
            'Aún sin entregar': filas_pendientes,
        },
    }


def generar_retrasos(periodo_inicio: date, periodo_fin: date) -> dict:
    """Retrasos de vacíos registrados en el período, por tipo."""
    from modulos.vacios.models import RetrasoVacio

    retrasos = (
        RetrasoVacio.objects
        .filter(created_at__date__gte=periodo_inicio, created_at__date__lte=periodo_fin)
        .select_related('vacio', 'vacio__cliente')
        .order_by('created_at')
    )

    filas = []
    maniobra = 0
    retorno = 0
    notificados = 0
    for r in retrasos:
        if r.tipo == 'MANIOBRA':
            maniobra += 1
        else:
            retorno += 1
        if r.notificado_agencia:
            notificados += 1
        filas.append({
            'folio': r.vacio.folio,
            'contenedor': r.vacio.contenedor,
            'cliente': r.vacio.cliente.nombre if r.vacio.cliente else '—',
            'tipo': r.get_tipo_display(),
            'motivo': r.motivo,
            'fecha_estimada_nueva': r.fecha_estimada_nueva.strftime('%d/%m/%Y'),
            'notificado_agencia': 'Sí' if r.notificado_agencia else 'No',
        })

    total = maniobra + retorno
    pct_notificados = round(notificados / total * 100, 1) if total else 0

    return {
        'tipo': 'VACIOS_RETRASOS',
        'titulo': (
            f'Retrasos de vacíos — '
            f'{periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}'
        ),
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_retrasos': total,
            'retrasos_maniobra': maniobra,
            'retrasos_retorno': retorno,
            'pct_notificados': pct_notificados,
        },
        'filas': filas,
        'tablas': {
            'Retrasos del periodo': filas,
        },
    }


GENERADORES = {
    'VACIOS_ENTREGAS_SEMANAL': generar_entregas_por_operador,
    'VACIOS_RETRASOS': generar_retrasos,
}
