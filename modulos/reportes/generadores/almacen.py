"""Generadores de datos para reportes del módulo Almacén."""

from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone


def generar_inventario_general(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de inventario general: todos los productos activos con su stock actual."""
    from modulos.almacen.models import ProductoAlmacen

    productos = ProductoAlmacen.objects.filter(activo=True).order_by('categoria', 'descripcion')

    filas = []
    valor_total = Decimal('0')
    for p in productos:
        valor = p.costo_total
        valor_total += valor
        filas.append({
            'sku': p.sku,
            'descripcion': p.descripcion,
            'categoria': p.categoria,
            'cantidad': float(p.cantidad),
            'unidad': p.unidad_medida,
            'costo_unitario': float(p.costo_unitario),
            'valor_total': float(valor),
            'stock_bajo': p.stock_bajo,
            'stock_agotado': p.stock_agotado,
        })

    return {
        'tipo': 'ALMACEN_INVENTARIO',
        'titulo': 'Inventario General de Almacén',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_productos': len(filas),
            'valor_total': float(valor_total),
            'productos_stock_bajo': sum(1 for f in filas if f['stock_bajo']),
            'productos_agotados': sum(1 for f in filas if f['stock_agotado']),
        },
        'filas': filas,
    }


def generar_stock_critico(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de productos con stock en o por debajo del mínimo."""
    from modulos.almacen.models import ProductoAlmacen

    productos = (
        ProductoAlmacen.objects
        .filter(activo=True, cantidad__lte=models_stock_minimo())
        .order_by('cantidad')
    )
    # Filtro manual porque stock_minimo es un campo DecimalField
    from django.db.models import F
    productos = (
        ProductoAlmacen.objects
        .filter(activo=True, cantidad__lte=F('stock_minimo'))
        .order_by('cantidad')
    )

    filas = []
    for p in productos:
        filas.append({
            'sku': p.sku,
            'descripcion': p.descripcion,
            'categoria': p.categoria,
            'cantidad': float(p.cantidad),
            'stock_minimo': float(p.stock_minimo),
            'unidad': p.unidad_medida,
            'agotado': p.stock_agotado,
            'tiempo_reorden_dias': p.tiempo_reorden_dias,
            'proveedor': str(p.proveedor_principal) if p.proveedor_principal else '',
        })

    return {
        'tipo': 'ALMACEN_STOCK_CRITICO',
        'titulo': 'Productos en Stock Crítico',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_criticos': len(filas),
            'total_agotados': sum(1 for f in filas if f['agotado']),
        },
        'filas': filas,
    }


def models_stock_minimo():
    """Placeholder — no se usa directamente, ver filtro F() en generar_stock_critico."""
    return 0


def generar_proximos_caducar(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de productos próximos a caducar (dentro de 30 días) o ya caducados."""
    from modulos.almacen.models import ProductoAlmacen

    hoy = timezone.now().date()
    limite = hoy + timedelta(days=30)

    productos = (
        ProductoAlmacen.objects
        .filter(activo=True, tiene_caducidad=True, fecha_caducidad__lte=limite)
        .order_by('fecha_caducidad')
    )

    filas = []
    for p in productos:
        dias = (p.fecha_caducidad - hoy).days if p.fecha_caducidad else None
        filas.append({
            'sku': p.sku,
            'descripcion': p.descripcion,
            'categoria': p.categoria,
            'cantidad': float(p.cantidad),
            'unidad': p.unidad_medida,
            'fecha_caducidad': str(p.fecha_caducidad),
            'dias_restantes': dias,
            'caducado': dias is not None and dias < 0,
        })

    return {
        'tipo': 'ALMACEN_CADUCIDAD',
        'titulo': 'Productos Próximos a Caducar',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total': len(filas),
            'ya_caducados': sum(1 for f in filas if f['caducado']),
            'proximos_30d': sum(1 for f in filas if not f['caducado']),
        },
        'filas': filas,
    }


def generar_movimientos(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de movimientos (entradas y salidas) en el período."""
    from modulos.almacen.models import MovimientoAlmacen

    movimientos = (
        MovimientoAlmacen.objects
        .filter(fecha__date__gte=periodo_inicio, fecha__date__lte=periodo_fin)
        .select_related('producto', 'usuario')
        .order_by('-fecha')
    )

    filas = []
    for m in movimientos:
        filas.append({
            'fecha': m.fecha.strftime('%d/%m/%Y %H:%M'),
            'tipo': m.tipo,
            'tipo_display': m.get_tipo_display() if hasattr(m, 'get_tipo_display') else m.tipo,
            'producto_sku': m.producto.sku if m.producto else '',
            'producto_desc': m.producto.descripcion if m.producto else '',
            'cantidad': float(m.cantidad),
            'usuario': m.usuario.get_full_name() or m.usuario.username if m.usuario else '',
            'referencia': m.referencia if hasattr(m, 'referencia') else '',
        })

    return {
        'tipo': 'ALMACEN_MOVIMIENTOS',
        'titulo': f'Movimientos de Almacén — {periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_movimientos': len(filas),
            'entradas': sum(1 for f in filas if 'ENT' in f.get('tipo', '') or 'ENTRADA' in f.get('tipo', '')),
            'salidas': sum(1 for f in filas if 'SAL' in f.get('tipo', '') or 'SALIDA' in f.get('tipo', '')),
        },
        'filas': filas,
    }


# Mapa tipo_reporte → función generadora
GENERADORES = {
    'ALMACEN_INVENTARIO': generar_inventario_general,
    'ALMACEN_STOCK_CRITICO': generar_stock_critico,
    'ALMACEN_CADUCIDAD': generar_proximos_caducar,
    'ALMACEN_MOVIMIENTOS': generar_movimientos,
}
