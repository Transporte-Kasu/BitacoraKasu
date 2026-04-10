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


# Mapa tipo_reporte → función generadora
GENERADORES = {
    'UNIDADES_KILOMETRAJE': generar_kilometraje_unidades,
}
