"""Generadores de datos para reportes del módulo Combustible."""

from datetime import date
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Prefetch


def generar_cargas_periodo(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de todas las cargas de combustible en el período."""
    from modulos.combustible.models import CargaCombustible
    from modulos.operadores.models import Operador

    cargas = (
        CargaCombustible.objects
        .filter(
            fecha_hora_inicio__date__gte=periodo_inicio,
            fecha_hora_inicio__date__lte=periodo_fin,
            estado='COMPLETADO',
        )
        .select_related('unidad', 'despachador')
        .prefetch_related(
            Prefetch(
                'unidad__operadores',
                queryset=Operador.objects.filter(activo=True),
                to_attr='operadores_activos',
            ),
            'fotos_candado_nuevo',
        )
        .order_by('-fecha_hora_inicio')
    )

    # Calcular el número máximo de candados nuevos para generar columnas fijas
    todas_cargas = list(cargas)
    max_candados_nuevos = max(
        (c.fotos_candado_nuevo.all().count() for c in todas_cargas),
        default=1,
    )
    max_candados_nuevos = max(max_candados_nuevos, 1)

    filas = []
    total_litros = 0
    for c in todas_cargas:
        operadores_activos = getattr(c.unidad, 'operadores_activos', [])
        nombre_operador = operadores_activos[0].nombre if operadores_activos else ''

        fotos_nuevos = list(c.fotos_candado_nuevo.all())

        fila = {
            'fecha': c.fecha_hora_inicio.strftime('%d/%m/%Y %H:%M'),
            'unidad': c.unidad.numero_economico,
            'placa': c.unidad.placa if hasattr(c.unidad, 'placa') else '',
            'operador': nombre_operador,
            'despachador': c.despachador.nombre if c.despachador else '',
            'litros': float(c.cantidad_litros),
            'kilometraje': c.kilometraje_actual,
            'estado_candado': c.get_estado_candado_anterior_display(),
            'candado_anterior': c.numero_candado_anterior or '',
            'foto_candado_anterior': c.foto_candado_anterior.url if c.foto_candado_anterior else '',
        }
        # Una columna de número y una de foto por cada candado nuevo posible
        for i in range(1, max_candados_nuevos + 1):
            foto = fotos_nuevos[i - 1] if i <= len(fotos_nuevos) else None
            fila[f'candado_nuevo_{i}'] = foto.numero_candado if foto else ''
            fila[f'foto_candado_nuevo_{i}'] = foto.foto.url if (foto and foto.foto) else ''

        filas.append(fila)
        total_litros += float(c.cantidad_litros)

    return {
        'tipo': 'COMBUSTIBLE_CARGAS',
        'titulo': f'Cargas de Combustible — {periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_cargas': len(filas),
            'total_litros': round(total_litros, 2),
        },
        'filas': filas,
    }


def generar_consumo_por_unidad(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de consumo total de combustible agrupado por unidad."""
    from modulos.combustible.models import CargaCombustible

    datos = (
        CargaCombustible.objects
        .filter(
            fecha_hora_inicio__date__gte=periodo_inicio,
            fecha_hora_inicio__date__lte=periodo_fin,
            estado='COMPLETADO',
        )
        .values('unidad__numero_economico', 'unidad__placa')
        .annotate(
            total_litros=Sum('cantidad_litros'),
            num_cargas=Count('id'),
        )
        .order_by('-total_litros')
    )

    filas = []
    gran_total = 0
    for d in datos:
        filas.append({
            'unidad': d['unidad__numero_economico'],
            'placa': d.get('unidad__placa', ''),
            'num_cargas': d['num_cargas'],
            'total_litros': float(d['total_litros']),
        })
        gran_total += float(d['total_litros'])

    return {
        'tipo': 'COMBUSTIBLE_CONSUMO',
        'titulo': f'Consumo de Combustible por Unidad — {periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_unidades': len(filas),
            'total_litros': round(gran_total, 2),
            'promedio_por_unidad': round(gran_total / len(filas), 2) if filas else 0,
        },
        'filas': filas,
    }


def generar_alertas_candado(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de alertas de candado en el período."""
    from modulos.combustible.models import AlertaCombustible

    alertas = (
        AlertaCombustible.objects
        .filter(
            fecha_generacion__date__gte=periodo_inicio,
            fecha_generacion__date__lte=periodo_fin,
        )
        .select_related('carga__unidad', 'resuelta_por')
        .order_by('-fecha_generacion')
    )

    filas = []
    for a in alertas:
        filas.append({
            'fecha': a.fecha_generacion.strftime('%d/%m/%Y %H:%M'),
            'tipo': a.get_tipo_alerta_display(),
            'unidad': a.carga.unidad.numero_economico,
            'mensaje': a.mensaje,
            'resuelta': a.resuelta,
            'resuelta_por': (
                a.resuelta_por.get_full_name() or a.resuelta_por.username
            ) if a.resuelta_por else '',
            'fecha_resolucion': a.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if a.fecha_resolucion else '',
        })

    return {
        'tipo': 'COMBUSTIBLE_ALERTAS',
        'titulo': f'Alertas de Candado — {periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_alertas': len(filas),
            'resueltas': sum(1 for f in filas if f['resuelta']),
            'pendientes': sum(1 for f in filas if not f['resuelta']),
        },
        'filas': filas,
    }


# Mapa tipo_reporte → función generadora
GENERADORES = {
    'COMBUSTIBLE_CARGAS': generar_cargas_periodo,
    'COMBUSTIBLE_CONSUMO': generar_consumo_por_unidad,
    'COMBUSTIBLE_ALERTAS': generar_alertas_candado,
}
