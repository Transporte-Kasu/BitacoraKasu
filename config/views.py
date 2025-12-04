from django.views.generic import TemplateView
from django.utils import timezone
from django.db.models import Sum
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad
from modulos.bitacoras.models import BitacoraViaje
from modulos.combustible.models import CargaCombustible


class IndexView(TemplateView):
    """Vista principal con dashboard de estadísticas"""
    template_name = 'index.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoy = timezone.now().date()
        
        # Estadísticas generales
        context['total_operadores'] = Operador.objects.count()
        context['total_unidades'] = Unidad.objects.count()
        context['total_bitacoras'] = BitacoraViaje.objects.count()
        context['total_cargas_combustible'] = CargaCombustible.objects.count()
        
        # Estadísticas activos
        context['operadores_activos'] = Operador.objects.filter(activo=True).count()
        context['unidades_activas'] = Unidad.objects.filter(activa=True).count()
        context['viajes_completados'] = BitacoraViaje.objects.filter(completado=True).count()
        context['viajes_en_curso'] = BitacoraViaje.objects.filter(completado=False).count()
        
        # Estadísticas de combustible
        cargas_hoy = CargaCombustible.objects.filter(fecha_hora_inicio__date=hoy)
        context['cargas_hoy'] = cargas_hoy.count()
        context['cargas_completadas_hoy'] = cargas_hoy.filter(estado='COMPLETADO').count()
        context['cargas_en_proceso'] = CargaCombustible.objects.filter(estado='EN_PROCESO').count()
        
        # Alertas de candados
        context['alertas_candado'] = CargaCombustible.objects.filter(
            estado_candado_anterior__in=['ALTERADO', 'VIOLADO', 'SIN_CANDADO'],
            fecha_hora_inicio__date=hoy
        ).count()
        
        # Total de litros cargados hoy
        litros_hoy = cargas_hoy.filter(estado='COMPLETADO').aggregate(
            total=Sum('cantidad_litros')
        )['total'] or 0
        context['total_litros_hoy'] = round(float(litros_hoy), 2)
        
        return context
