from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta

from .models import (
    OrdenTrabajo, PiezaRequerida, TipoMantenimiento,
    CategoriaFalla, SeguimientoOrden, ChecklistMantenimiento,
    ChecklistOrden, HistorialMantenimiento, ReporteFalla
)
from modulos.compras.models import Requisicion, ItemRequisicion
from modulos.unidades.models import Unidad


@login_required
def dashboard_taller(request):
    """Dashboard principal del taller"""
    hoy = timezone.now().date()
    hace_30_dias = hoy - timedelta(days=30)
    hace_7_dias = hoy - timedelta(days=7)
    
    # ========== Estadísticas Generales ==========
    total_ordenes = OrdenTrabajo.objects.count()
    ordenes_activas = OrdenTrabajo.objects.exclude(
        estado__in=['COMPLETADA', 'CANCELADA']
    )
    
    ordenes_pendientes = ordenes_activas.filter(estado='PENDIENTE').count()
    ordenes_en_diagnostico = ordenes_activas.filter(estado='EN_DIAGNOSTICO').count()
    ordenes_esperando_piezas = ordenes_activas.filter(estado='ESPERANDO_PIEZAS').count()
    ordenes_en_reparacion = ordenes_activas.filter(estado='EN_REPARACION').count()
    ordenes_en_pruebas = ordenes_activas.filter(estado='EN_PRUEBAS').count()
    
    # Totales activas
    total_ordenes_activas = ordenes_activas.count()
    
    # Órdenes completadas este mes
    ordenes_completadas_mes = OrdenTrabajo.objects.filter(
        estado='COMPLETADA',
        fecha_finalizacion__gte=hace_30_dias
    ).count()
    
    # Órdenes críticas (más de 7 días en taller)
    ordenes_criticas = ordenes_activas.filter(
        fecha_inicio_real__lte=hace_7_dias
    ).select_related('unidad', 'mecanico_asignado')[:5]
    ordenes_criticas_count = ordenes_criticas.count()
    
    # ========== Unidades ==========
    unidades_en_taller = Unidad.objects.filter(
        ordenes_trabajo__estado__in=['EN_DIAGNOSTICO', 'EN_REPARACION', 'EN_PRUEBAS']
    ).distinct()
    unidades_en_taller_count = unidades_en_taller.count()
    
    # ========== Piezas ==========
    piezas_pendientes = PiezaRequerida.objects.filter(
        estado='PENDIENTE'
    ).select_related('orden_trabajo', 'producto')[:5]
    piezas_pendientes_count = PiezaRequerida.objects.filter(estado='PENDIENTE').count()
    
    piezas_solicitadas = PiezaRequerida.objects.filter(
        estado__in=['SOLICITADA', 'EN_COMPRA']
    ).count()
    
    # ========== Costos ==========
    # Costo total estimado de órdenes activas
    costo_total_estimado = sum(
        orden.costo_total_estimado for orden in ordenes_activas
    )
    
    # Costo total real de órdenes completadas este mes
    ordenes_completadas = OrdenTrabajo.objects.filter(
        estado='COMPLETADA',
        fecha_finalizacion__gte=hace_30_dias
    )
    costo_total_mes = sum(
        orden.costo_total_real for orden in ordenes_completadas
    )
    
    # ========== Tiempos Promedio ==========
    ordenes_con_tiempo = ordenes_completadas.filter(
        fecha_inicio_real__isnull=False,
        fecha_finalizacion__isnull=False
    )
    if ordenes_con_tiempo.exists():
        tiempo_promedio_dias = ordenes_con_tiempo.aggregate(
            Avg('dias_en_taller')
        )['dias_en_taller__avg'] or 0
    else:
        tiempo_promedio_dias = 0
    
    # ========== Últimas Órdenes ==========
    ultimas_ordenes = OrdenTrabajo.objects.select_related(
        'unidad', 'mecanico_asignado', 'tipo_mantenimiento'
    ).order_by('-fecha_creacion')[:10]
    
    # ========== Datos para Gráficas ==========
    
    # Gráfica: Órdenes por estado
    ordenes_por_estado = OrdenTrabajo.objects.values('estado').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Gráfica: Órdenes por prioridad (activas)
    ordenes_por_prioridad = ordenes_activas.values('prioridad').annotate(
        count=Count('id')
    ).order_by('prioridad')
    
    # Gráfica: Órdenes por tipo de mantenimiento (mes actual)
    ordenes_por_tipo = OrdenTrabajo.objects.filter(
        fecha_creacion__gte=hace_30_dias
    ).values('tipo_mantenimiento__nombre').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Gráfica: Órdenes creadas por día (últimos 7 días)
    ordenes_por_dia = []
    labels_dias = []
    for i in range(6, -1, -1):
        dia = hoy - timedelta(days=i)
        count = OrdenTrabajo.objects.filter(
            fecha_creacion__date=dia
        ).count()
        ordenes_por_dia.append(count)
        labels_dias.append(dia.strftime('%d/%m'))
    
    # Gráfica: Top 5 mecánicos por órdenes completadas (mes)
    top_mecanicos = ordenes_completadas.filter(
        mecanico_asignado__isnull=False
    ).values(
        'mecanico_asignado__first_name',
        'mecanico_asignado__last_name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Reportes de falla nuevos (para badge en dashboard)
    reportes_nuevos_count = ReporteFalla.objects.filter(estado='NUEVO').count()

    context = {
        # Estadísticas principales
        'total_ordenes': total_ordenes,
        'reportes_nuevos_count': reportes_nuevos_count,
        'total_ordenes_activas': total_ordenes_activas,
        'ordenes_completadas_mes': ordenes_completadas_mes,
        'ordenes_pendientes': ordenes_pendientes,
        'ordenes_en_diagnostico': ordenes_en_diagnostico,
        'ordenes_esperando_piezas': ordenes_esperando_piezas,
        'ordenes_en_reparacion': ordenes_en_reparacion,
        'ordenes_en_pruebas': ordenes_en_pruebas,
        'ordenes_criticas_count': ordenes_criticas_count,
        'ordenes_criticas': ordenes_criticas,
        
        # Unidades y piezas
        'unidades_en_taller_count': unidades_en_taller_count,
        'unidades_en_taller': unidades_en_taller,
        'piezas_pendientes_count': piezas_pendientes_count,
        'piezas_pendientes': piezas_pendientes,
        'piezas_solicitadas': piezas_solicitadas,
        
        # Costos y tiempos
        'costo_total_estimado': round(float(costo_total_estimado), 2),
        'costo_total_mes': round(float(costo_total_mes), 2),
        'tiempo_promedio_dias': round(tiempo_promedio_dias, 1),
        
        # Listas
        'ultimas_ordenes': ultimas_ordenes,
        
        # Datos para gráficas
        'ordenes_por_estado': list(ordenes_por_estado),
        'ordenes_por_prioridad': list(ordenes_por_prioridad),
        'ordenes_por_tipo': list(ordenes_por_tipo),
        'ordenes_por_dia': ordenes_por_dia,
        'labels_dias': labels_dias,
        'top_mecanicos': list(top_mecanicos),
    }
    
    return render(request, 'taller/dashboard.html', context)


@login_required
def lista_ordenes(request):
    """Lista de órdenes de trabajo con filtros"""
    ordenes = OrdenTrabajo.objects.select_related(
        'unidad', 'tipo_mantenimiento', 'mecanico_asignado', 'creada_por'
    ).prefetch_related('piezas_requeridas')

    # Filtros
    estado = request.GET.get('estado')
    if estado:
        ordenes = ordenes.filter(estado=estado)

    prioridad = request.GET.get('prioridad')
    if prioridad:
        ordenes = ordenes.filter(prioridad=prioridad)

    unidad_id = request.GET.get('unidad')
    if unidad_id:
        ordenes = ordenes.filter(unidad_id=unidad_id)

    mecanico = request.GET.get('mecanico')
    if mecanico:
        ordenes = ordenes.filter(mecanico_asignado_id=mecanico)

    busqueda = request.GET.get('q')
    if busqueda:
        ordenes = ordenes.filter(
            Q(folio__icontains=busqueda) |
            Q(descripcion_problema__icontains=busqueda) |
            Q(unidad__numero_economico__icontains=busqueda) |
            Q(unidad__placa__icontains=busqueda)
        )

    context = {
        'ordenes': ordenes,
        'estados': OrdenTrabajo.ESTADO_CHOICES,
        'prioridades': OrdenTrabajo.PRIORIDAD_CHOICES,
        'unidades': Unidad.objects.filter(activa=True),
    }

    return render(request, 'taller/lista_ordenes.html', context)


@login_required
def detalle_orden(request, folio):
    """Detalle de una orden de trabajo"""
    orden = get_object_or_404(
        OrdenTrabajo.objects.select_related(
            'unidad', 'tipo_mantenimiento', 'mecanico_asignado',
            'supervisor', 'creada_por', 'operador_reporta'
        ),
        folio=folio
    )

    piezas = orden.piezas_requeridas.select_related('producto', 'agregada_por')
    seguimientos = orden.seguimientos.select_related('usuario')
    checklist = orden.checklist.select_related('item_checklist', 'revisado_por')

    context = {
        'orden': orden,
        'piezas': piezas,
        'seguimientos': seguimientos,
        'checklist': checklist,
    }

    return render(request, 'taller/detalle_orden.html', context)


@login_required
@permission_required('taller.add_ordentrabajo', raise_exception=True)
def crear_orden(request):
    """Crear nueva orden de trabajo"""
    if request.method == 'POST':
        try:
            # Crear orden
            orden = OrdenTrabajo.objects.create(
                unidad_id=request.POST.get('unidad'),
                operador_reporta_id=request.POST.get('operador_reporta') or None,
                tipo_mantenimiento_id=request.POST.get('tipo_mantenimiento'),
                categoria_falla_id=request.POST.get('categoria_falla') or None,
                descripcion_problema=request.POST.get('descripcion_problema'),
                sintomas=request.POST.get('sintomas', ''),
                prioridad=request.POST.get('prioridad'),
                kilometraje_ingreso=request.POST.get('kilometraje_ingreso'),
                fecha_programada=request.POST.get('fecha_programada') or None,
                mecanico_asignado_id=request.POST.get('mecanico_asignado') or None,
                observaciones=request.POST.get('observaciones', ''),
                creada_por=request.user
            )

            # Si tiene tipo de mantenimiento con checklist, crear items
            if orden.tipo_mantenimiento:
                items_checklist = ChecklistMantenimiento.objects.filter(
                    tipo_mantenimiento=orden.tipo_mantenimiento,
                    activo=True
                )
                for item in items_checklist:
                    ChecklistOrden.objects.create(
                        orden_trabajo=orden,
                        item_checklist=item
                    )

            messages.success(request, f'Orden de trabajo {orden.folio} creada exitosamente.')
            return redirect('taller:detalle_orden', folio=orden.folio)

        except Exception as e:
            messages.error(request, f'Error al crear la orden: {str(e)}')

    context = {
        'unidades': Unidad.objects.filter(activa=True),
        'tipos_mantenimiento': TipoMantenimiento.objects.filter(activo=True),
        'categorias_falla': CategoriaFalla.objects.filter(activo=True),
        'prioridades': OrdenTrabajo.PRIORIDAD_CHOICES,
    }

    return render(request, 'taller/crear_orden.html', context)


@login_required
def buscar_producto_almacen(request):
    """Endpoint AJAX: busca productos en el catálogo de almacén"""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'resultados': []})
    from modulos.almacen.models import ProductoAlmacen
    productos = ProductoAlmacen.objects.filter(activo=True).filter(
        Q(descripcion__icontains=q) | Q(sku__icontains=q)
    ).order_by('descripcion')[:10]
    return JsonResponse({'resultados': [
        {
            'id': p.id,
            'descripcion': p.descripcion,
            'sku': p.sku,
            'cantidad': float(p.cantidad),
            'disponible': float(p.cantidad) > 0,
        }
        for p in productos
    ]})


@login_required
@permission_required('taller.change_ordentrabajo', raise_exception=True)
def agregar_pieza(request, folio):
    """Agregar pieza requerida a una orden (con búsqueda en almacén)"""
    orden = get_object_or_404(OrdenTrabajo, folio=folio)

    if request.method == 'POST':
        try:
            from modulos.almacen.models import ProductoAlmacen

            producto_almacen_id = request.POST.get('producto_almacen_id', '').strip()
            nombre_pieza = request.POST.get('nombre_pieza', '').strip()
            cantidad = request.POST.get('cantidad')

            if not cantidad:
                messages.error(request, 'La cantidad es requerida.')
                return redirect('taller:detalle_orden', folio=folio)

            kwargs = {
                'orden_trabajo': orden,
                'cantidad': cantidad,
                'descripcion_uso': '',
                'costo_estimado': 0,
                'agregada_por': request.user,
            }

            if producto_almacen_id:
                prod_alm = get_object_or_404(ProductoAlmacen, id=producto_almacen_id)
                kwargs['producto_almacen'] = prod_alm
                # Si el producto de almacén tiene vínculo con compras, aprovecharlo
                if prod_alm.producto_compra:
                    kwargs['producto'] = prod_alm.producto_compra
            elif nombre_pieza:
                kwargs['nombre_pieza'] = nombre_pieza
            else:
                messages.error(request, 'Debes seleccionar un producto o ingresar el nombre de la pieza.')
                return redirect('taller:detalle_orden', folio=folio)

            PiezaRequerida.objects.create(**kwargs)
            messages.success(request, 'Pieza agregada exitosamente.')

            # Si la orden está en diagnóstico, cambiar a esperando piezas
            if orden.estado == 'EN_DIAGNOSTICO':
                orden.estado = 'ESPERANDO_PIEZAS'
                orden.save()
                SeguimientoOrden.objects.create(
                    orden_trabajo=orden,
                    usuario=request.user,
                    estado_anterior='EN_DIAGNOSTICO',
                    estado_nuevo='ESPERANDO_PIEZAS',
                    comentario='Piezas agregadas, esperando surtido o compra'
                )

        except Exception as e:
            messages.error(request, f'Error al agregar pieza: {str(e)}')

    return redirect('taller:detalle_orden', folio=folio)


@login_required
@permission_required('taller.diagnosticar_orden', raise_exception=True)
def actualizar_diagnostico(request, folio):
    """Actualizar diagnóstico de la orden"""
    orden = get_object_or_404(OrdenTrabajo, folio=folio)

    if request.method == 'POST':
        estado_anterior = orden.estado

        orden.diagnostico = request.POST.get('diagnostico')
        orden.fecha_diagnostico = timezone.now()
        orden.costo_estimado_mano_obra = request.POST.get('costo_estimado_mano_obra', 0)

        # Determinar nuevo estado
        if orden.piezas_requeridas.exists():
            orden.estado = 'ESPERANDO_PIEZAS'
        else:
            orden.estado = 'EN_REPARACION'

        orden.save()

        # Registrar seguimiento
        SeguimientoOrden.objects.create(
            orden_trabajo=orden,
            usuario=request.user,
            estado_anterior=estado_anterior,
            estado_nuevo=orden.estado,
            comentario=f'Diagnóstico completado'
        )

        messages.success(request, 'Diagnóstico actualizado exitosamente.')

    return redirect('taller:detalle_orden', folio=folio)


@login_required
@permission_required('compras.add_requisicion', raise_exception=True)
def generar_requisicion(request, folio):
    """
    Genera automáticamente:
    - SolicitudSalida en almacén para piezas con stock suficiente
    - Requisición de compra para piezas sin stock o no catalogadas
    """
    orden = get_object_or_404(OrdenTrabajo, folio=folio)
    piezas_pendientes = list(orden.piezas_requeridas.filter(estado='PENDIENTE'))

    if not piezas_pendientes:
        messages.warning(request, 'No hay piezas pendientes para solicitar.')
        return redirect('taller:detalle_orden', folio=folio)

    try:
        from modulos.almacen.models import SolicitudSalida, ItemSolicitudSalida
        from modulos.compras.models import Producto

        # Separar piezas según disponibilidad en almacén
        piezas_almacen = [p for p in piezas_pendientes if p.disponible_en_almacen]
        piezas_compra = [p for p in piezas_pendientes if not p.disponible_en_almacen]

        folios_generados = []

        # --- Piezas disponibles en almacén → SolicitudSalida ---
        if piezas_almacen:
            solicitud = SolicitudSalida.objects.create(
                tipo='ORDEN_TRABAJO',
                orden_trabajo=orden,
                solicitante=request.user,
                justificacion=f"Piezas para OT {orden.folio}: {orden.descripcion_problema}",
                requiere_autorizacion=True,
            )
            for pieza in piezas_almacen:
                ItemSolicitudSalida.objects.create(
                    solicitud=solicitud,
                    producto_almacen=pieza.producto_almacen,
                    cantidad_solicitada=pieza.cantidad,
                )
                pieza.marcar_como_solicitada(None)
            folios_generados.append(f'Almacén: {solicitud.folio}')

        # --- Piezas sin stock o no catalogadas → Requisición de compra ---
        if piezas_compra:
            requisicion = Requisicion.objects.create(
                solicitante=request.user,
                fecha_requerida=orden.fecha_programada or timezone.now().date(),
                justificacion=f"Piezas para OT {orden.folio}: {orden.descripcion_problema}",
                estado='PENDIENTE',
            )
            for pieza in piezas_compra:
                # Resolver el producto de compras
                if pieza.producto:
                    producto = pieza.producto
                elif pieza.producto_almacen and pieza.producto_almacen.producto_compra:
                    producto = pieza.producto_almacen.producto_compra
                else:
                    # Crear producto en catálogo de compras a partir del nombre libre
                    nombre = pieza.nombre_display or 'Pieza sin nombre'
                    producto, _ = Producto.objects.get_or_create(
                        nombre=nombre,
                        defaults={
                            'descripcion': f'Creado desde OT {orden.folio}',
                            'unidad_medida': 'Pieza',
                            'categoria': 'Taller',
                        }
                    )
                    pieza.producto = producto
                    pieza.save(update_fields=['producto'])

                item = ItemRequisicion.objects.create(
                    requisicion=requisicion,
                    producto=producto,
                    cantidad=pieza.cantidad,
                    descripcion_adicional=f"OT: {orden.folio}",
                )
                pieza.marcar_como_solicitada(item)
            folios_generados.append(f'Compras: {requisicion.folio}')

        # Seguimiento de la orden
        resumen = ' | '.join(folios_generados)
        if orden.estado == 'EN_DIAGNOSTICO':
            estado_anterior = orden.estado
            orden.estado = 'ESPERANDO_PIEZAS'
            orden.save()
            SeguimientoOrden.objects.create(
                orden_trabajo=orden,
                usuario=request.user,
                estado_anterior=estado_anterior,
                estado_nuevo='ESPERANDO_PIEZAS',
                comentario=f'Generado: {resumen}',
            )
        else:
            SeguimientoOrden.objects.create(
                orden_trabajo=orden,
                usuario=request.user,
                estado_anterior=orden.estado,
                estado_nuevo=orden.estado,
                comentario=f'Generado: {resumen}',
            )

        messages.success(request, f'Generado exitosamente — {resumen}')

    except Exception as e:
        messages.error(request, f'Error al procesar piezas: {str(e)}')

    return redirect('taller:detalle_orden', folio=folio)


@login_required
@permission_required('taller.change_ordentrabajo', raise_exception=True)
def cambiar_estado_orden(request, folio):
    """Cambiar estado de la orden de trabajo"""
    orden = get_object_or_404(OrdenTrabajo, folio=folio)

    if request.method == 'POST':
        estado_anterior = orden.estado
        nuevo_estado = request.POST.get('nuevo_estado')
        comentario = request.POST.get('comentario', '')

        orden.estado = nuevo_estado

        # Actualizar fechas según el estado
        if nuevo_estado == 'EN_REPARACION' and not orden.fecha_inicio_real:
            orden.fecha_inicio_real = timezone.now()
        elif nuevo_estado == 'COMPLETADA':
            orden.fecha_finalizacion = timezone.now()
            orden.costo_real_mano_obra = request.POST.get('costo_real_mano_obra', orden.costo_estimado_mano_obra)
            orden.trabajo_realizado = request.POST.get('trabajo_realizado', '')
            orden.kilometraje_salida = request.POST.get('kilometraje_salida', orden.unidad.kilometraje_actual)

            # Crear historial
            HistorialMantenimiento.objects.create(
                unidad=orden.unidad,
                orden_trabajo=orden,
                fecha_servicio=orden.fecha_finalizacion.date(),
                kilometraje_ingreso=orden.kilometraje_ingreso,
                kilometraje_salida=orden.kilometraje_salida,
                tipo_servicio=str(orden.tipo_mantenimiento) if orden.tipo_mantenimiento else 'Reparación',
                descripcion_breve=orden.descripcion_problema[:200],
                costo_total=orden.costo_total_real,
                tiempo_fuera_servicio_dias=orden.dias_en_taller,
                tiempo_fuera_servicio_horas=orden.horas_en_taller
            )

        orden.save()

        # Registrar seguimiento
        SeguimientoOrden.objects.create(
            orden_trabajo=orden,
            usuario=request.user,
            estado_anterior=estado_anterior,
            estado_nuevo=nuevo_estado,
            comentario=comentario
        )

        messages.success(request, f'Estado cambiado a {orden.get_estado_display()}')

    return redirect('taller:detalle_orden', folio=folio)


@login_required
def historial_unidad(request, unidad_id):
    """Historial de mantenimientos de una unidad"""
    unidad = get_object_or_404(Unidad, id=unidad_id)

    historial = HistorialMantenimiento.objects.filter(
        unidad=unidad
    ).select_related('orden_trabajo')

    # Estadísticas
    total_ordenes = historial.count()
    costo_total = historial.aggregate(Sum('costo_total'))['costo_total__sum'] or 0
    dias_promedio = historial.aggregate(
        Avg('tiempo_fuera_servicio_dias')
    )['tiempo_fuera_servicio_dias__avg'] or 0

    context = {
        'unidad': unidad,
        'historial': historial,
        'total_ordenes': total_ordenes,
        'costo_total': costo_total,
        'dias_promedio': round(dias_promedio, 1),
    }

    return render(request, 'taller/historial_unidad.html', context)


@login_required
def api_ordenes_activas(request):
    """API para obtener órdenes activas (para dashboards)"""
    ordenes = OrdenTrabajo.objects.exclude(
        estado__in=['COMPLETADA', 'CANCELADA']
    ).values(
        'folio', 'estado', 'prioridad',
        'unidad__numero_economico', 'dias_en_taller'
    )

    return JsonResponse(list(ordenes), safe=False)


# ─────────────────────────────────────────────────────────────────────────────
# Reportes de Falla (vía QR)
# ─────────────────────────────────────────────────────────────────────────────

def reportar_falla(request, unidad_pk):
    """Vista pública (sin login) para que el operador reporte una falla vía QR."""
    unidad = get_object_or_404(Unidad, pk=unidad_pk, activa=True)
    categorias = CategoriaFalla.objects.filter(activo=True).order_by('nombre')

    if request.method == 'POST':
        categoria_id = request.POST.get('categoria_falla') or None
        descripcion = request.POST.get('descripcion', '').strip()
        operador_nombre = request.POST.get('operador_nombre', '').strip()
        foto = request.FILES.get('foto')

        reporte = ReporteFalla.objects.create(
            unidad=unidad,
            operador_nombre=operador_nombre,
            categoria_falla_id=categoria_id,
            descripcion=descripcion,
            foto=foto,
        )
        return redirect('taller:reporte_enviado', folio=reporte.folio)

    return render(request, 'taller/reportar_falla.html', {
        'unidad': unidad,
        'categorias': categorias,
    })


def reporte_enviado(request, folio):
    """Confirmación pública tras enviar un reporte de falla."""
    reporte = get_object_or_404(ReporteFalla, folio=folio)
    return render(request, 'taller/reporte_enviado.html', {'reporte': reporte})


@login_required
def bandeja_reportes(request):
    """Bandeja de reportes de falla para el personal de taller."""
    reportes = ReporteFalla.objects.select_related(
        'unidad', 'categoria_falla', 'atendido_por'
    )

    estado = request.GET.get('estado')
    if estado:
        # Filtro explícito: mostrar exactamente lo que pidió
        reportes = reportes.filter(estado=estado)
    else:
        # Por defecto: ocultar resueltos y cancelados
        reportes = reportes.exclude(estado__in=['RESUELTO', 'CANCELADO'])

    unidad_id = request.GET.get('unidad')
    if unidad_id:
        reportes = reportes.filter(unidad_id=unidad_id)

    return render(request, 'taller/bandeja_reportes.html', {
        'reportes': reportes,
        'estados': ReporteFalla.ESTADO_CHOICES,
        'unidades': Unidad.objects.filter(activa=True),
        'nuevos_count': ReporteFalla.objects.filter(estado='NUEVO').count(),
        'mostrando_activos': not estado,
    })


@login_required
def detalle_reporte(request, folio):
    """Detalle de un reporte de falla."""
    reporte = get_object_or_404(
        ReporteFalla.objects.select_related(
            'unidad', 'categoria_falla', 'atendido_por', 'orden_trabajo'
        ),
        folio=folio
    )
    from modulos.almacen.models import ProductoAlmacen
    productos_almacen = ProductoAlmacen.objects.filter(activo=True).order_by('descripcion')
    tipos_mantenimiento = TipoMantenimiento.objects.filter(activo=True)

    return render(request, 'taller/detalle_reporte.html', {
        'reporte': reporte,
        'productos_almacen': productos_almacen,
        'tipos_mantenimiento': tipos_mantenimiento,
    })


@login_required
def atender_reporte(request, folio):
    """Marca el reporte como EN_ATENCION."""
    reporte = get_object_or_404(ReporteFalla, folio=folio)
    if reporte.estado == 'NUEVO':
        reporte.estado = 'EN_ATENCION'
        reporte.atendido_por = request.user
        reporte.fecha_atencion = timezone.now()
        reporte.save()
        messages.success(request, f'Reporte {folio} tomado. En atención.')
    return redirect('taller:detalle_reporte', folio=folio)


@login_required
def resolver_reporte(request, folio):
    """
    Resuelve el reporte directamente. Opcionalmente genera una
    AsignacionDirectaAlmacen si se indicaron piezas usadas.
    """
    reporte = get_object_or_404(ReporteFalla, folio=folio)

    if request.method == 'POST':
        notas = request.POST.get('notas_taller', '').strip()
        producto_id = request.POST.get('producto_id', '').strip()
        cantidad = request.POST.get('cantidad', '').strip()
        motivo_asignacion = request.POST.get('motivo_asignacion', '').strip()

        reporte.notas_taller = notas
        reporte.estado = 'RESUELTO'
        reporte.fecha_resolucion = timezone.now()
        if not reporte.atendido_por:
            reporte.atendido_por = request.user
        reporte.save()

        # Si se indicó pieza, crear AsignacionDirectaAlmacen
        if producto_id and cantidad:
            try:
                from modulos.almacen.models import AsignacionDirectaAlmacen, ProductoAlmacen
                producto = get_object_or_404(ProductoAlmacen, pk=producto_id)
                AsignacionDirectaAlmacen.objects.create(
                    producto=producto,
                    unidad=reporte.unidad,
                    cantidad=cantidad,
                    motivo=motivo_asignacion or f'Reporte {reporte.folio}: {reporte.descripcion[:100]}',
                    entregado_por=request.user,
                )
                messages.success(
                    request,
                    f'Reporte {folio} resuelto y pieza asignada a la unidad.'
                )
            except Exception as e:
                messages.warning(
                    request,
                    f'Reporte resuelto pero error al registrar pieza: {e}'
                )
        else:
            messages.success(request, f'Reporte {folio} marcado como resuelto.')

    return redirect('taller:bandeja_reportes')


@login_required
def convertir_reporte_a_ot(request, folio):
    """Convierte un reporte de falla en una OrdenTrabajo completa."""
    reporte = get_object_or_404(ReporteFalla, folio=folio)

    if request.method == 'POST':
        try:
            orden = OrdenTrabajo.objects.create(
                unidad=reporte.unidad,
                tipo_mantenimiento_id=request.POST.get('tipo_mantenimiento') or None,
                categoria_falla=reporte.categoria_falla,
                descripcion_problema=reporte.descripcion or str(reporte.categoria_falla or 'Sin descripción'),
                sintomas=request.POST.get('sintomas', ''),
                prioridad=request.POST.get('prioridad', 'MEDIA'),
                kilometraje_ingreso=request.POST.get('kilometraje_ingreso', reporte.unidad.kilometraje_actual),
                observaciones=f'Generada desde reporte {reporte.folio}',
                creada_por=request.user,
            )

            # Vincular OT al reporte y cerrarlo
            reporte.orden_trabajo = orden
            reporte.estado = 'EN_ATENCION'
            if not reporte.atendido_por:
                reporte.atendido_por = request.user
                reporte.fecha_atencion = timezone.now()
            reporte.save()

            messages.success(
                request,
                f'Orden de trabajo {orden.folio} creada desde reporte {folio}.'
            )
            return redirect('taller:detalle_orden', folio=orden.folio)

        except Exception as e:
            messages.error(request, f'Error al crear la orden: {e}')

    return redirect('taller:detalle_reporte', folio=folio)


@login_required
def cancelar_reporte(request, folio):
    """Cancela un reporte de falla."""
    reporte = get_object_or_404(ReporteFalla, folio=folio)
    if request.method == 'POST' and reporte.estado not in ('RESUELTO', 'CANCELADO'):
        reporte.estado = 'CANCELADO'
        reporte.notas_taller += f"\nCANCELADO por {request.user.get_full_name() or request.user.username}"
        reporte.save()
        messages.info(request, f'Reporte {folio} cancelado.')
    return redirect('taller:bandeja_reportes')


@login_required
def qr_todas_unidades(request):
    """Vista para imprimir los QR de todas las unidades activas en una sola hoja."""
    tipo = request.GET.get('tipo', '')
    unidades = Unidad.objects.filter(activa=True).order_by('numero_economico')
    if tipo:
        unidades = unidades.filter(tipo=tipo)

    unidades_data = [
        {
            'pk': u.pk,
            'numero_economico': u.numero_economico,
            'placa': u.placa,
            'marca': u.marca,
            'modelo': u.modelo,
            'tipo': u.get_tipo_display(),
            'url': request.build_absolute_uri(f'/taller/reportar/{u.pk}/'),
        }
        for u in unidades
    ]

    return render(request, 'taller/qr_todas_unidades.html', {
        'unidades': unidades,
        'unidades_data': unidades_data,
        'tipo_seleccionado': tipo,
        'tipo_choices': Unidad.TIPO_CHOICES,
    })


@login_required
def qr_unidad(request, unidad_pk):
    """Muestra el QR de reporte de falla para una unidad (para imprimir)."""
    unidad = get_object_or_404(Unidad, pk=unidad_pk, activa=True)
    url_reporte = request.build_absolute_uri(
        f'/taller/reportar/{unidad.pk}/'
    )
    return render(request, 'taller/qr_unidad.html', {
        'unidad': unidad,
        'url_reporte': url_reporte,
    })