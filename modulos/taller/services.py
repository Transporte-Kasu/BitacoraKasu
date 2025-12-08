"""
Servicios y funciones utilitarias para el módulo de taller
Incluye lógica de negocio y cálculos relacionados con mantenimiento
"""

from django.db.models import Sum, Avg, Count, Q, Max, Min
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

from .models import (
    OrdenTrabajo, HistorialMantenimiento, TipoMantenimiento,
    PiezaRequerida
)
from modulos.unidades.models import Unidad


class ServicioMantenimiento:
    """Servicio para gestión de mantenimiento de unidades"""

    @staticmethod
    def obtener_unidades_requieren_mantenimiento():
        """
        Retorna unidades que requieren mantenimiento basado en:
        - Fecha de próximo mantenimiento
        - Kilometraje desde último servicio
        """
        hoy = timezone.now().date()
        unidades_mantenimiento = []

        # Unidades con fecha de mantenimiento vencida
        por_fecha = Unidad.objects.filter(
            activa=True,
            proximo_mantenimiento__lte=hoy
        )

        for unidad in por_fecha:
            unidades_mantenimiento.append({
                'unidad': unidad,
                'razon': 'Fecha de mantenimiento vencida',
                'urgencia': 'ALTA' if unidad.proximo_mantenimiento < hoy else 'MEDIA',
                'dias_vencido': (hoy - unidad.proximo_mantenimiento).days if unidad.proximo_mantenimiento else 0
            })

        # Unidades con kilometraje alto desde último servicio
        todas_activas = Unidad.objects.filter(activa=True)

        for unidad in todas_activas:
            ultimo_historial = HistorialMantenimiento.objects.filter(
                unidad=unidad
            ).order_by('-fecha_servicio').first()

            if ultimo_historial:
                km_desde_servicio = unidad.kilometraje_actual - ultimo_historial.kilometraje_salida

                # Si han pasado más de 10,000 km sin servicio
                if km_desde_servicio >= 10000:
                    unidades_mantenimiento.append({
                        'unidad': unidad,
                        'razon': f'{km_desde_servicio:,} km desde último servicio',
                        'urgencia': 'ALTA' if km_desde_servicio >= 15000 else 'MEDIA',
                        'kilometros_desde_servicio': km_desde_servicio
                    })

        return unidades_mantenimiento

    @staticmethod
    def calcular_costo_total_mantenimiento(unidad, fecha_inicio=None, fecha_fin=None):
        """
        Calcula el costo total de mantenimiento de una unidad
        en un periodo específico
        """
        historial = HistorialMantenimiento.objects.filter(unidad=unidad)

        if fecha_inicio:
            historial = historial.filter(fecha_servicio__gte=fecha_inicio)
        if fecha_fin:
            historial = historial.filter(fecha_servicio__lte=fecha_fin)

        total = historial.aggregate(Sum('costo_total'))['costo_total__sum'] or Decimal('0')

        return {
            'total': total,
            'cantidad_servicios': historial.count(),
            'promedio_por_servicio': total / historial.count() if historial.count() > 0 else Decimal('0')
        }

    @staticmethod
    def calcular_estadisticas_unidad(unidad):
        """Calcula estadísticas completas de mantenimiento de una unidad"""
        historial = HistorialMantenimiento.objects.filter(unidad=unidad)
        ordenes = OrdenTrabajo.objects.filter(unidad=unidad)

        # Costos
        costo_total = historial.aggregate(Sum('costo_total'))['costo_total__sum'] or Decimal('0')

        # Tiempos
        tiempo_total_dias = historial.aggregate(Sum('tiempo_fuera_servicio_dias'))['tiempo_fuera_servicio_dias__sum'] or 0
        tiempo_promedio = historial.aggregate(Avg('tiempo_fuera_servicio_dias'))['tiempo_fuera_servicio_dias__avg'] or 0

        # Frecuencia
        servicios_preventivos = historial.filter(tipo_servicio__icontains='preventivo').count()
        servicios_correctivos = historial.filter(
            Q(tipo_servicio__icontains='correctivo') | Q(tipo_servicio__icontains='reparación')
        ).count()

        # Órdenes activas
        ordenes_activas = ordenes.exclude(estado__in=['COMPLETADA', 'CANCELADA']).count()

        # Último servicio
        ultimo_servicio = historial.order_by('-fecha_servicio').first()

        return {
            'total_servicios': historial.count(),
            'servicios_preventivos': servicios_preventivos,
            'servicios_correctivos': servicios_correctivos,
            'costo_total': costo_total,
            'costo_promedio_servicio': costo_total / historial.count() if historial.count() > 0 else Decimal('0'),
            'tiempo_total_fuera_servicio_dias': tiempo_total_dias,
            'tiempo_promedio_servicio_dias': round(tiempo_promedio, 1),
            'ordenes_activas': ordenes_activas,
            'ultimo_servicio': ultimo_servicio,
            'dias_desde_ultimo_servicio': (
                (timezone.now().date() - ultimo_servicio.fecha_servicio).days
                if ultimo_servicio else None
            )
        }

    @staticmethod
    def obtener_unidades_en_taller():
        """Retorna unidades que actualmente están en taller"""
        ordenes_activas = OrdenTrabajo.objects.filter(
            estado__in=['EN_DIAGNOSTICO', 'EN_REPARACION', 'ESPERANDO_PIEZAS', 'EN_PRUEBAS']
        ).select_related('unidad', 'mecanico_asignado', 'tipo_mantenimiento')

        unidades_en_taller = []

        for orden in ordenes_activas:
            unidades_en_taller.append({
                'unidad': orden.unidad,
                'orden': orden,
                'dias_en_taller': orden.dias_en_taller,
                'estado': orden.get_estado_display(),
                'mecanico': orden.mecanico_asignado,
                'prioridad': orden.get_prioridad_display(),
                'costo_estimado': orden.costo_total_estimado
            })

        return unidades_en_taller

    @staticmethod
    def generar_pronostico_mantenimiento(unidad, meses=6):
        """
        Genera un pronóstico de mantenimiento basado en historial
        y kilometraje promedio
        """
        # Calcular kilometraje promedio mensual
        historial = HistorialMantenimiento.objects.filter(
            unidad=unidad
        ).order_by('fecha_servicio')

        if historial.count() < 2:
            return None

        primer_servicio = historial.first()
        ultimo_servicio = historial.last()

        dias_transcurridos = (ultimo_servicio.fecha_servicio - primer_servicio.fecha_servicio).days

        if dias_transcurridos == 0:
            return None

        km_recorridos = ultimo_servicio.kilometraje_salida - primer_servicio.kilometraje_ingreso
        km_por_dia = km_recorridos / dias_transcurridos
        km_por_mes = km_por_dia * 30

        # Calcular costo promedio mensual
        costo_total = historial.aggregate(Sum('costo_total'))['costo_total__sum'] or Decimal('0')
        meses_transcurridos = dias_transcurridos / 30
        costo_promedio_mensual = costo_total / Decimal(str(meses_transcurridos)) if meses_transcurridos > 0 else Decimal('0')

        # Generar pronóstico
        pronostico = {
            'km_promedio_mensual': round(km_por_mes, 2),
            'costo_promedio_mensual': costo_promedio_mensual,
            'pronostico_meses': []
        }

        fecha_actual = timezone.now().date()
        km_actual = unidad.kilometraje_actual

        for mes in range(1, meses + 1):
            fecha_estimada = fecha_actual + timedelta(days=30 * mes)
            km_estimado = int(km_actual + (km_por_mes * mes))
            costo_estimado = costo_promedio_mensual * mes

            # Determinar si requiere servicio
            requiere_servicio = False
            tipo_servicio = None

            if km_estimado - km_actual >= 10000:
                requiere_servicio = True
                tipo_servicio = "Servicio A"

            if km_estimado - km_actual >= 40000:
                requiere_servicio = True
                tipo_servicio = "Servicio B"

            pronostico['pronostico_meses'].append({
                'mes': mes,
                'fecha': fecha_estimada,
                'kilometraje_estimado': km_estimado,
                'costo_acumulado_estimado': costo_estimado,
                'requiere_servicio': requiere_servicio,
                'tipo_servicio': tipo_servicio
            })

        return pronostico


class ReporteTaller:
    """Generador de reportes del taller"""

    @staticmethod
    def reporte_mensual(mes, anio):
        """Genera reporte mensual del taller"""
        fecha_inicio = date(anio, mes, 1)

        if mes == 12:
            fecha_fin = date(anio + 1, 1, 1) - timedelta(days=1)
        else:
            fecha_fin = date(anio, mes + 1, 1) - timedelta(days=1)

        # Órdenes del mes
        ordenes = OrdenTrabajo.objects.filter(
            fecha_creacion__date__range=[fecha_inicio, fecha_fin]
        )

        # Órdenes completadas
        completadas = ordenes.filter(estado='COMPLETADA')

        # Costos
        costo_total = completadas.aggregate(
            total_mano_obra=Sum('costo_real_mano_obra')
        )

        # Calcular costo de piezas
        piezas_usadas = PiezaRequerida.objects.filter(
            orden_trabajo__in=completadas,
            estado='INSTALADA'
        )

        costo_piezas = sum(
            pieza.subtotal_real for pieza in piezas_usadas
        )

        return {
            'periodo': f"{fecha_inicio.strftime('%B %Y')}",
            'total_ordenes': ordenes.count(),
            'ordenes_completadas': completadas.count(),
            'ordenes_pendientes': ordenes.exclude(estado__in=['COMPLETADA', 'CANCELADA']).count(),
            'ordenes_canceladas': ordenes.filter(estado='CANCELADA').count(),
            'costo_total_mano_obra': costo_total['total_mano_obra'] or Decimal('0'),
            'costo_total_piezas': costo_piezas,
            'costo_total': (costo_total['total_mano_obra'] or Decimal('0')) + costo_piezas,
            'tiempo_promedio_reparacion': completadas.aggregate(
                Avg('tiempo_fuera_servicio_dias')
            )['tiempo_fuera_servicio_dias__avg'] or 0,
            'unidades_atendidas': completadas.values('unidad').distinct().count()
        }

    @staticmethod
    def reporte_por_unidad(unidad, fecha_inicio=None, fecha_fin=None):
        """Genera reporte detallado por unidad"""
        historial = HistorialMantenimiento.objects.filter(unidad=unidad)

        if fecha_inicio:
            historial = historial.filter(fecha_servicio__gte=fecha_inicio)
        if fecha_fin:
            historial = historial.filter(fecha_servicio__lte=fecha_fin)

        # Agrupar por tipo de servicio
        servicios_por_tipo = {}

        for item in historial:
            tipo = item.tipo_servicio
            if tipo not in servicios_por_tipo:
                servicios_por_tipo[tipo] = {
                    'cantidad': 0,
                    'costo_total': Decimal('0'),
                    'tiempo_total': 0
                }

            servicios_por_tipo[tipo]['cantidad'] += 1
            servicios_por_tipo[tipo]['costo_total'] += item.costo_total
            servicios_por_tipo[tipo]['tiempo_total'] += item.tiempo_fuera_servicio_dias

        return {
            'unidad': unidad,
            'total_servicios': historial.count(),
            'costo_total': historial.aggregate(Sum('costo_total'))['costo_total__sum'] or Decimal('0'),
            'tiempo_total_fuera_servicio': historial.aggregate(
                Sum('tiempo_fuera_servicio_dias')
            )['tiempo_fuera_servicio_dias__sum'] or 0,
            'servicios_por_tipo': servicios_por_tipo,
            'primer_servicio': historial.order_by('fecha_servicio').first(),
            'ultimo_servicio': historial.order_by('-fecha_servicio').first()
        }

    @staticmethod
    def top_unidades_costosas(limite=10, fecha_inicio=None, fecha_fin=None):
        """Retorna las unidades con mayores costos de mantenimiento"""
        historial = HistorialMantenimiento.objects.all()

        if fecha_inicio:
            historial = historial.filter(fecha_servicio__gte=fecha_inicio)
        if fecha_fin:
            historial = historial.filter(fecha_servicio__lte=fecha_fin)

        # Agrupar por unidad y sumar costos
        unidades_costos = historial.values('unidad').annotate(
            costo_total=Sum('costo_total'),
            cantidad_servicios=Count('id'),
            tiempo_total=Sum('tiempo_fuera_servicio_dias')
        ).order_by('-costo_total')[:limite]

        # Enriquecer con información de unidad
        resultado = []
        for item in unidades_costos:
            unidad = Unidad.objects.get(pk=item['unidad'])
            resultado.append({
                'unidad': unidad,
                'costo_total': item['costo_total'],
                'cantidad_servicios': item['cantidad_servicios'],
                'tiempo_total_dias': item['tiempo_total'],
                'costo_promedio_servicio': item['costo_total'] / item['cantidad_servicios']
            })

        return resultado