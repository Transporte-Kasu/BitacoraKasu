from django.views.generic import TemplateView
from apps.operadores.models import Operador
from apps.unidades.models import Unidad
from apps.bitacoras.models import BitacoraViaje


class IndexView(TemplateView):
    """Vista principal con dashboard de estadísticas"""
    template_name = 'index.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Estadísticas generales
        context['total_operadores'] = Operador.objects.count()
        context['total_unidades'] = Unidad.objects.count()
        context['total_bitacoras'] = BitacoraViaje.objects.count()
        
        # Estadísticas activos
        context['operadores_activos'] = Operador.objects.filter(activo=True).count()
        context['unidades_activas'] = Unidad.objects.filter(activa=True).count()
        context['viajes_completados'] = BitacoraViaje.objects.filter(completado=True).count()
        context['viajes_en_curso'] = BitacoraViaje.objects.filter(completado=False).count()
        
        return context
