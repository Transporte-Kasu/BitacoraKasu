"""Generadores de datos para reportes del módulo Almacén."""

from collections import defaultdict
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
    from django.db.models import Count
    from modulos.almacen.models import MovimientoAlmacen, ProductoAlmacen

    movimientos = (
        MovimientoAlmacen.objects
        .filter(fecha_movimiento__date__gte=periodo_inicio, fecha_movimiento__date__lte=periodo_fin)
        .select_related('producto_almacen', 'usuario')
        .order_by('-fecha_movimiento')
    )

    filas = []
    for m in movimientos:
        filas.append({
            'fecha': m.fecha_movimiento.strftime('%d/%m/%Y %H:%M'),
            'tipo': m.tipo,
            'tipo_display': m.get_tipo_display(),
            'producto_sku': m.producto_almacen.sku if m.producto_almacen_id else '',
            'producto_desc': m.producto_almacen.descripcion if m.producto_almacen_id else '',
            'cantidad': float(m.cantidad),
            'usuario': m.usuario.get_full_name() or m.usuario.username if m.usuario_id else '',
            'referencia': m.observaciones,
        })

    # Top 5 productos con más registros de salida en el período
    top_salidas_qs = (
        MovimientoAlmacen.objects
        .filter(
            tipo='SALIDA',
            fecha_movimiento__date__gte=periodo_inicio,
            fecha_movimiento__date__lte=periodo_fin,
        )
        .values('producto_almacen__sku', 'producto_almacen__descripcion')
        .annotate(num_salidas=Count('id'))
        .order_by('-num_salidas')[:5]
    )
    top_5_salidas = [
        {
            'sku': r['producto_almacen__sku'],
            'descripcion': r['producto_almacen__descripcion'],
            'num_salidas': r['num_salidas'],
        }
        for r in top_salidas_qs
    ]

    # Productos activos sin ningún movimiento en el período
    con_movimiento_ids = list(
        MovimientoAlmacen.objects
        .filter(
            fecha_movimiento__date__gte=periodo_inicio,
            fecha_movimiento__date__lte=periodo_fin,
        )
        .values_list('producto_almacen_id', flat=True)
        .distinct()
    )
    sin_mov_qs = (
        ProductoAlmacen.objects
        .filter(activo=True)
        .exclude(id__in=con_movimiento_ids)
        .order_by('descripcion')
    )
    total_activos = ProductoAlmacen.objects.filter(activo=True).count()
    total_sin_movimiento = sin_mov_qs.count()
    sin_movimiento = [
        {
            'sku': p['sku'],
            'descripcion': p['descripcion'],
            'cantidad': float(p['cantidad']),
        }
        for p in sin_mov_qs.values('sku', 'descripcion', 'cantidad')[:5]
    ]

    num_entradas = sum(1 for f in filas if f['tipo'] == 'ENTRADA')
    num_salidas = sum(1 for f in filas if f['tipo'] == 'SALIDA')
    num_ajustes = len(filas) - num_entradas - num_salidas

    return {
        'tipo': 'ALMACEN_MOVIMIENTOS',
        'titulo': f'Movimientos de Almacén — {periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'top_5_salidas': top_5_salidas,
        'sin_movimiento': sin_movimiento,
        'resumen': {
            'total_movimientos': len(filas),
            'entradas': num_entradas,
            'salidas': num_salidas,
            'ajustes_traslados': num_ajustes,
            'total_productos_activos': total_activos,
            'productos_con_movimiento': total_activos - total_sin_movimiento,
            'total_sin_movimiento': total_sin_movimiento,
        },
        'filas': filas,
    }


def generar_analisis_integral(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte integral de asignaciones directas, entradas y auditoría del período."""
    from modulos.almacen.models import (
        AsignacionDirectaAlmacen, AsignacionSalida, EntradaAlmacen, AuditoriaAlmacen,
    )

    # --- Asignaciones directas (AsignacionDirectaAlmacen + AsignacionSalida) ---
    directas_qs = (
        AsignacionDirectaAlmacen.objects
        .filter(fecha_asignacion__date__gte=periodo_inicio, fecha_asignacion__date__lte=periodo_fin)
        .select_related('producto', 'unidad', 'entregado_por')
    )
    salidas_qs = (
        AsignacionSalida.objects
        .filter(creado_en__date__gte=periodo_inicio, creado_en__date__lte=periodo_fin)
        .select_related('unidad', 'equipo', 'dolly', 'caja_seca', 'entregado_por')
        .prefetch_related('items__producto')
    )

    asignaciones = []
    for a in directas_qs:
        asignaciones.append({
            'folio': a.folio,
            'tipo': 'DIRECTA',
            'destino': str(a.unidad),
            'producto_sku': a.producto.sku,
            'producto_desc': a.producto.descripcion,
            'cantidad': float(a.cantidad),
            'motivo': a.motivo,
            'entregado_por': a.entregado_por.get_full_name() or a.entregado_por.username,
            'fecha': a.fecha_asignacion.strftime('%d/%m/%Y %H:%M'),
        })
    for s in salidas_qs:
        entregado_por = (
            (s.entregado_por.get_full_name() or s.entregado_por.username) if s.entregado_por_id else ''
        )
        for item in s.items.all():
            asignaciones.append({
                'folio': s.folio,
                'tipo': 'SALIDA',
                'destino': s.destino_display,
                'producto_sku': item.producto.sku,
                'producto_desc': item.producto.descripcion,
                'cantidad': float(item.cantidad),
                'motivo': s.justificacion,
                'entregado_por': entregado_por,
                'fecha': s.creado_en.strftime('%d/%m/%Y %H:%M'),
            })

    destino_totales = defaultdict(float)
    for fila in asignaciones:
        destino_totales[fila['destino']] += fila['cantidad']
    top_destinos = [
        {'destino': destino, 'cantidad_total': total}
        for destino, total in sorted(destino_totales.items(), key=lambda kv: kv[1], reverse=True)[:5]
    ]

    # --- Entradas (EntradaAlmacen) ---
    entradas_qs = (
        EntradaAlmacen.objects
        .filter(fecha_entrada__date__gte=periodo_inicio, fecha_entrada__date__lte=periodo_fin)
        .select_related('recibido_por')
    )
    entradas = []
    entradas_por_tipo = defaultdict(int)
    valor_total_entradas = Decimal('0')
    for e in entradas_qs:
        entradas_por_tipo[e.get_tipo_display()] += 1
        valor_total_entradas += e.costo_total_entrada
        entradas.append({
            'folio': e.folio,
            'tipo': e.tipo,
            'tipo_display': e.get_tipo_display(),
            'recibido_por': e.recibido_por.get_full_name() or e.recibido_por.username,
            'costo_total_entrada': float(e.costo_total_entrada),
            'total_items': e.total_items,
            'fecha_entrada': e.fecha_entrada.strftime('%d/%m/%Y %H:%M'),
        })

    # --- Auditoría (AuditoriaAlmacen) ---
    auditoria_qs = (
        AuditoriaAlmacen.objects
        .filter(fecha__date__gte=periodo_inicio, fecha__date__lte=periodo_fin, usuario__isnull=False)
        .select_related('usuario')
    )
    accion_a_campo = {
        'CREAR': 'crear', 'EDITAR': 'editar', 'ELIMINAR': 'eliminar',
        'AUTORIZAR': 'autorizar', 'RECHAZAR': 'rechazar',
        'ENTREGAR': 'entregar', 'CANCELAR': 'cancelar',
    }
    por_usuario = defaultdict(lambda: {campo: 0 for campo in accion_a_campo.values()})
    auditoria_por_accion = {label: 0 for _, label in AuditoriaAlmacen.ACCION_CHOICES}
    total_eventos_auditoria = 0
    for ev in auditoria_qs:
        usuario_nombre = (
            (ev.usuario.get_full_name() or ev.usuario.username) if ev.usuario_id else 'sistema'
        )
        campo = accion_a_campo[ev.accion]
        por_usuario[usuario_nombre][campo] += 1
        auditoria_por_accion[ev.get_accion_display()] += 1
        total_eventos_auditoria += 1

    auditoria = []
    for usuario_nombre, conteos in por_usuario.items():
        total_usuario = sum(conteos.values())
        auditoria.append({'usuario': usuario_nombre, 'total_eventos': total_usuario, **conteos})
    auditoria.sort(key=lambda f: f['total_eventos'], reverse=True)
    top_usuarios_auditoria = auditoria[:5]

    alertas_auditoria = []
    if total_eventos_auditoria > 0:
        if len(auditoria) >= 2:
            top = auditoria[0]
            pct_top = top['total_eventos'] / total_eventos_auditoria
            if pct_top > 0.5:
                alertas_auditoria.append(
                    f"El usuario {top['usuario']} concentra el {round(pct_top * 100)}% de la "
                    f"actividad de auditoría del período."
                )
        eliminar_count = auditoria_por_accion.get('Eliminar', 0)
        pct_eliminar = eliminar_count / total_eventos_auditoria
        if pct_eliminar > 0.2:
            alertas_auditoria.append(
                f"Las eliminaciones representan el {round(pct_eliminar * 100)}% de los eventos de "
                f"auditoría del período, por encima del umbral esperado."
            )

    resumen = {
        'total_asignaciones_directas': directas_qs.count(),
        'total_asignaciones_salida': salidas_qs.count(),
        'total_items_asignados': sum(f['cantidad'] for f in asignaciones),
        'total_entradas': entradas_qs.count(),
        'entradas_por_tipo': dict(entradas_por_tipo),
        'valor_total_entradas': float(valor_total_entradas),
        'total_eventos_auditoria': total_eventos_auditoria,
        'auditoria_por_accion': auditoria_por_accion,
        'alertas_auditoria': alertas_auditoria,
    }

    return {
        'tipo': 'ALMACEN_ANALISIS_INTEGRAL',
        'titulo': (
            f'Análisis Integral de Almacén — {periodo_inicio.strftime("%d/%m/%Y")} '
            f'al {periodo_fin.strftime("%d/%m/%Y")}'
        ),
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': resumen,
        'asignaciones': asignaciones,
        'entradas': entradas,
        'auditoria': auditoria,
        'top_destinos': top_destinos,
        'top_usuarios_auditoria': top_usuarios_auditoria,
        'tablas': {
            'Asignaciones': asignaciones,
            'Entradas': entradas,
            'Auditoria': auditoria,
        },
    }


# Mapa tipo_reporte → función generadora
GENERADORES = {
    'ALMACEN_INVENTARIO': generar_inventario_general,
    'ALMACEN_STOCK_CRITICO': generar_stock_critico,
    'ALMACEN_CADUCIDAD': generar_proximos_caducar,
    'ALMACEN_MOVIMIENTOS': generar_movimientos,
    'ALMACEN_ANALISIS_INTEGRAL': generar_analisis_integral,
}
