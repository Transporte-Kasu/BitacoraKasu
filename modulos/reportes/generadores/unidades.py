"""Generadores de datos para reportes del módulo Unidades."""

from datetime import date
from django.utils import timezone


def generar_kilometraje_unidades(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de kilometraje actual de todas las unidades activas.

    Es un snapshot del estado actual (no depende del período), pero acepta
    los parámetros de período para mantener la firma estándar del sistema.
    """
    from modulos.unidades.models import Unidad

    unidades = (
        Unidad.objects
        .filter(activa=True)
        .order_by('-kilometraje_actual')
        .values('numero_economico', 'placa', 'marca', 'modelo', 'kilometraje_actual', 'tipo')
    )

    filas = []
    total_km = 0
    for u in unidades:
        total_km += u['kilometraje_actual'] or 0
        filas.append({
            'numero_economico': u['numero_economico'],
            'placa': u['placa'] or '—',
            'marca': u['marca'] or '—',
            'modelo': u['modelo'] or '—',
            'kilometraje_km': u['kilometraje_actual'] or 0,
            'tipo': u['tipo'],
        })

    total = len(filas)
    km_promedio = round(total_km / total) if total else 0
    km_maximo = filas[0]['kilometraje_km'] if filas else 0
    unidad_max = filas[0]['numero_economico'] if filas else '—'

    return {
        'tipo': 'UNIDADES_KILOMETRAJE',
        'titulo': 'Kilometraje de Flota',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_unidades': total,
            'km_promedio': km_promedio,
            'km_maximo': km_maximo,
            'unidad_mayor_km': unidad_max,
        },
        'filas': filas,
    }


def generar_balanza_utilidad(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de utilidad/pérdida por unidad en el período (ingresos vs. gastos).

    Reutiliza el mismo cálculo que la vista bajo demanda del admin de Unidad
    (modulos.unidades.services.calcular_reporte_utilidad).
    """
    from modulos.unidades.services import calcular_reporte_utilidad

    resultado = calcular_reporte_utilidad(periodo_inicio, periodo_fin)

    filas = [
        {
            'unidad': f['unidad'].numero_economico,
            'ingresos': float(f['ingresos']),
            'gasto_combustible': float(f['gasto_combustible']),
            'gasto_taller': float(f['gasto_taller']),
            'gasto_consumibles': float(f['gasto_consumibles']),
            'gasto_total': float(f['gasto_total']),
            'utilidad': float(f['utilidad']),
            'utilidad_pct': round(float(f['utilidad_pct']), 2) if f['utilidad_pct'] is not None else None,
        }
        for f in resultado['filas']
    ]

    unidades_en_utilidad = sum(1 for f in filas if f['utilidad'] > 0)
    unidades_en_perdida = sum(1 for f in filas if f['utilidad'] < 0)
    unidades_sin_actividad = sum(1 for f in filas if f['utilidad'] == 0.0)

    con_actividad = [f for f in filas if f['utilidad'] != 0]
    ordenadas = sorted(con_actividad, key=lambda f: f['utilidad'])
    mayor_perdida = ordenadas[0] if ordenadas else None
    mas_rentable = ordenadas[-1] if ordenadas else None

    return {
        'tipo': 'UNIDADES_BALANZA_UTILIDAD',
        'titulo': f'Balanza de Utilidad por Unidad — {periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_unidades': len(filas),
            'unidades_en_utilidad': unidades_en_utilidad,
            'unidades_en_perdida': unidades_en_perdida,
            'unidades_sin_actividad': unidades_sin_actividad,
            'ingresos_totales': float(resultado['totales']['ingresos']),
            'gasto_total': float(resultado['totales']['gasto_total']),
            'utilidad_total': float(resultado['totales']['utilidad']),
            'bitacoras_excluidas': resultado['bitacoras_excluidas'],
            'cargas_excluidas': resultado['cargas_excluidas'],
        },
        'filas': filas,
        'unidad_mas_rentable': mas_rentable,
        'unidad_mayor_perdida': mayor_perdida,
    }


# Mapa tipo_reporte → función generadora
GENERADORES = {
    'UNIDADES_KILOMETRAJE': generar_kilometraje_unidades,
    'UNIDADES_BALANZA_UTILIDAD': generar_balanza_utilidad,
}
