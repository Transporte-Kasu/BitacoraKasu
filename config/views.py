from django.views.generic import TemplateView
from django.utils import timezone
from django.db.models import Sum, F, Count, Avg
from datetime import timedelta

from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad
from modulos.bitacoras.models import BitacoraViaje
from modulos.combustible.models import CargaCombustible
from modulos.compras.models import Requisicion, OrdenCompra, Proveedor
from modulos.almacen.models import ProductoAlmacen, AlertaStock
from modulos.taller.models import OrdenTrabajo


class IndexView(TemplateView):
    """Vista principal con dashboard de estadísticas"""
    template_name = 'index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoy = timezone.now().date()
        hace_30_dias = hoy - timedelta(days=30)
        hace_7_dias = hoy - timedelta(days=7)

        # ========== Estadísticas de Operadores ==========
        context['total_operadores'] = Operador.objects.count()
        context['operadores_activos'] = Operador.objects.filter(activo=True).count()

        # ========== Estadísticas de Unidades ==========
        context['total_unidades'] = Unidad.objects.count()
        context['unidades_activas'] = Unidad.objects.filter(activa=True).count()
        unidades_mantenimiento = Unidad.objects.filter(
            proximo_mantenimiento__lte=hoy + timedelta(days=7)
        ).count()
        context['unidades_mantenimiento_proximo'] = unidades_mantenimiento

        # ========== Estadísticas de Bitácoras ==========
        context['total_bitacoras'] = BitacoraViaje.objects.count()
        context['viajes_completados'] = BitacoraViaje.objects.filter(completado=True).count()
        context['viajes_en_curso'] = BitacoraViaje.objects.filter(completado=False).count()
        viajes_mes = BitacoraViaje.objects.filter(
            fecha_salida__gte=hace_30_dias
        ).count()
        context['viajes_ultimo_mes'] = viajes_mes

        # ========== Estadísticas de Combustible ==========
        cargas_hoy = CargaCombustible.objects.filter(fecha_hora_inicio__date=hoy)
        context['cargas_hoy'] = cargas_hoy.count()
        context['cargas_completadas_hoy'] = cargas_hoy.filter(estado='COMPLETADO').count()
        context['cargas_en_proceso'] = CargaCombustible.objects.filter(estado='EN_PROCESO').count()

        # Alertas de candados
        context['alertas_candado'] = CargaCombustible.objects.filter(
            estado_candado_anterior__in=['ALTERADO', 'VIOLADO', 'SIN_CANDADO'],
            fecha_hora_inicio__date=hoy
        ).count()

        # Total de litros cargados
        litros_hoy = cargas_hoy.filter(estado='COMPLETADO').aggregate(
            total=Sum('cantidad_litros')
        )['total'] or 0
        context['total_litros_hoy'] = round(float(litros_hoy), 2)

        litros_mes = CargaCombustible.objects.filter(
            fecha_hora_inicio__date__gte=hace_30_dias,
            estado='COMPLETADO'
        ).aggregate(total=Sum('cantidad_litros'))['total'] or 0
        context['total_litros_mes'] = round(float(litros_mes), 2)

        # ========== Estadísticas de Taller ==========
        context['ordenes_taller_pendientes'] = OrdenTrabajo.objects.filter(
            estado__in=['PENDIENTE', 'EN_DIAGNOSTICO', 'EN_REPARACION']
        ).count()
        context['ordenes_taller_completadas_mes'] = OrdenTrabajo.objects.filter(
            estado='COMPLETADA',
            fecha_finalizacion__gte=hace_30_dias
        ).count()
        context['unidades_en_taller'] = OrdenTrabajo.objects.filter(
            estado__in=['EN_DIAGNOSTICO', 'EN_REPARACION', 'EN_PRUEBAS']
        ).values('unidad').distinct().count()

        # ========== Estadísticas de Compras ==========
        context['requisiciones_pendientes'] = Requisicion.objects.filter(
            estado='PENDIENTE'
        ).count()
        context['ordenes_compra_activas'] = OrdenCompra.objects.exclude(
            estado__in=['RECIBIDA', 'CANCELADA']
        ).count()
        context['proveedores_activos'] = Proveedor.objects.filter(activo=True).count()

        # ========== Estadísticas de Almacén ==========
        context['productos_almacen'] = ProductoAlmacen.objects.filter(activo=True).count()
        context['productos_stock_bajo'] = ProductoAlmacen.objects.filter(
            activo=True,
            cantidad__lte=F('stock_minimo')
        ).count()
        context['alertas_almacen'] = AlertaStock.objects.filter(resuelta=False).count()

        # Valor del inventario
        valor_inventario = ProductoAlmacen.objects.filter(activo=True).aggregate(
            total=Sum(F('cantidad') * F('costo_unitario'))
        )['total'] or 0
        context['valor_inventario'] = round(float(valor_inventario), 2)

        # ========== Datos para Gráficas ==========

        # Gráfica: Viajes por día (últimos 7 días)
        viajes_por_dia = []
        labels_dias = []
        for i in range(6, -1, -1):
            dia = hoy - timedelta(days=i)
            count = BitacoraViaje.objects.filter(
                fecha_salida__date=dia
            ).count()
            viajes_por_dia.append(count)
            labels_dias.append(dia.strftime('%d/%m'))
        context['viajes_por_dia'] = viajes_por_dia
        context['labels_dias'] = labels_dias

        # Gráfica: Combustible por día (últimos 7 días)
        combustible_por_dia = []
        for i in range(6, -1, -1):
            dia = hoy - timedelta(days=i)
            litros = CargaCombustible.objects.filter(
                fecha_hora_inicio__date=dia,
                estado='COMPLETADO'
            ).aggregate(total=Sum('cantidad_litros'))['total'] or 0
            combustible_por_dia.append(round(float(litros), 2))
        context['combustible_por_dia'] = combustible_por_dia

        # Gráfica: Estado de unidades (activas vs inactivas)
        context['unidades_activas_count'] = Unidad.objects.filter(activa=True).count()
        context['unidades_inactivas_count'] = Unidad.objects.filter(activa=False).count()

        # Gráfica: Distribución de operadores por tipo
        operadores_por_tipo = Operador.objects.filter(activo=True).values('tipo').annotate(
            count=Count('id')
        ).order_by('tipo')
        context['operadores_tipos'] = list(operadores_por_tipo)

        # Gráfica: Top 5 categorías de productos en almacén
        top_categorias = ProductoAlmacen.objects.filter(activo=True).values(
            'categoria'
        ).annotate(
            count=Count('id'),
            total_valor=Sum(F('cantidad') * F('costo_unitario'))
        ).order_by('-count')[:5]
        context['top_categorias_almacen'] = list(top_categorias)

        # Gráfica: Órdenes de taller por estado
        ordenes_por_estado = OrdenTrabajo.objects.values('estado').annotate(
            count=Count('id')
        ).order_by('-count')
        context['ordenes_taller_estados'] = list(ordenes_por_estado)

        # Alertas críticas
        context['alertas_criticas'] = AlertaStock.objects.filter(
            resuelta=False,
            tipo_alerta__in=['STOCK_AGOTADO', 'CADUCADO']
        ).select_related('producto_almacen')[:5]

        return context
