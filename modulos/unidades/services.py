from decimal import Decimal

from django.db.models import Sum

from .models import Unidad


def _suma_cantidad_por_costo(queryset):
    """Suma cantidad * producto.costo_unitario sobre un queryset de salidas de almacén."""
    total = Decimal('0')
    for item in queryset.select_related('producto'):
        total += item.cantidad * item.producto.costo_unitario
    return total


def calcular_reporte_utilidad(desde, hasta):
    """
    Calcula ingreso, gasto y utilidad por unidad activa en el rango [desde, hasta].

    Gasto = combustible (CargaCombustible.costo_calculado) + taller (OrdenTrabajo.costo_total_real)
    + consumibles de almacén (SalidaRapidaConsumible + AsignacionDirectaAlmacen +
    ItemAsignacionSalida con tipo_destino='UNIDAD'). Las piezas de taller vía SalidaAlmacen
    ligada a OrdenTrabajo no se incluyen aquí para no duplicar el gasto ya contado en
    OrdenTrabajo.costo_total_real.
    """
    from modulos.almacen.models import (
        SalidaRapidaConsumible, AsignacionDirectaAlmacen, ItemAsignacionSalida,
    )
    from modulos.bitacoras.models import BitacoraViaje
    from modulos.combustible.models import CargaCombustible
    from modulos.taller.models import OrdenTrabajo

    filas = []
    for unidad in Unidad.objects.filter(activa=True).order_by('numero_economico'):
        ingresos = BitacoraViaje.objects.filter(
            unidad=unidad, completado=True,
            fecha_llegada__date__gte=desde, fecha_llegada__date__lte=hasta,
        ).aggregate(t=Sum('ingreso_calculado'))['t'] or Decimal('0')

        gasto_combustible = CargaCombustible.objects.filter(
            unidad=unidad, estado='COMPLETADO',
            fecha_hora_inicio__date__gte=desde, fecha_hora_inicio__date__lte=hasta,
        ).aggregate(t=Sum('costo_calculado'))['t'] or Decimal('0')

        ordenes_completadas = OrdenTrabajo.objects.filter(
            unidad=unidad, estado='COMPLETADA',
            fecha_finalizacion__date__gte=desde, fecha_finalizacion__date__lte=hasta,
        )
        gasto_taller = sum((orden.costo_total_real for orden in ordenes_completadas), Decimal('0'))

        gasto_consumibles = (
            _suma_cantidad_por_costo(SalidaRapidaConsumible.objects.filter(
                unidad=unidad, fecha_salida__date__gte=desde, fecha_salida__date__lte=hasta,
            ))
            + _suma_cantidad_por_costo(AsignacionDirectaAlmacen.objects.filter(
                unidad=unidad, fecha_asignacion__date__gte=desde, fecha_asignacion__date__lte=hasta,
            ))
            + _suma_cantidad_por_costo(ItemAsignacionSalida.objects.filter(
                asignacion__tipo_destino='UNIDAD', asignacion__unidad=unidad,
                asignacion__fecha__gte=desde, asignacion__fecha__lte=hasta,
            ))
        )

        gasto_total = gasto_combustible + gasto_taller + gasto_consumibles
        utilidad = ingresos - gasto_total
        utilidad_pct = (utilidad / ingresos * 100) if ingresos else None

        filas.append({
            'unidad': unidad,
            'ingresos': ingresos,
            'gasto_combustible': gasto_combustible,
            'gasto_taller': gasto_taller,
            'gasto_consumibles': gasto_consumibles,
            'gasto_total': gasto_total,
            'utilidad': utilidad,
            'utilidad_pct': utilidad_pct,
        })

    totales = {
        clave: sum((f[clave] for f in filas), Decimal('0'))
        for clave in ('ingresos', 'gasto_combustible', 'gasto_taller', 'gasto_consumibles', 'gasto_total', 'utilidad')
    }

    bitacoras_excluidas = BitacoraViaje.objects.filter(
        completado=True, fecha_llegada__date__gte=desde, fecha_llegada__date__lte=hasta,
        ingreso_calculado__isnull=True,
    ).count()
    cargas_excluidas = CargaCombustible.objects.filter(
        estado='COMPLETADO', fecha_hora_inicio__date__gte=desde, fecha_hora_inicio__date__lte=hasta,
        costo_calculado__isnull=True,
    ).count()

    return {
        'filas': filas,
        'totales': totales,
        'bitacoras_excluidas': bitacoras_excluidas,
        'cargas_excluidas': cargas_excluidas,
    }
