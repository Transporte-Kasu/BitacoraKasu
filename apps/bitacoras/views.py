from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q, Count, Sum, Avg
from django.http import JsonResponse
from .models import BitacoraViaje
from .forms import BitacoraViajeForm, BitacoraViajeCompletarForm
import os


class BitacoraListView(LoginRequiredMixin, ListView):
    """Vista para listar todas las bitácoras de viaje"""
    model = BitacoraViaje
    template_name = 'bitacoras/bitacora_list.html'
    context_object_name = 'bitacoras'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = BitacoraViaje.objects.select_related(
            'operador', 'unidad'
        ).order_by('-fecha_salida')
        
        # Filtro por búsqueda
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(contenedor__icontains=search) |
                Q(destino__icontains=search) |
                Q(operador__nombre__icontains=search) |
                Q(unidad__numero_economico__icontains=search)
            )
        
        # Filtro por modalidad
        modalidad = self.request.GET.get('modalidad')
        if modalidad:
            queryset = queryset.filter(modalidad=modalidad)
        
        # Filtro por estado
        completado = self.request.GET.get('completado')
        if completado == 'true':
            queryset = queryset.filter(completado=True)
        elif completado == 'false':
            queryset = queryset.filter(completado=False)
        
        # Filtro por operador
        operador_id = self.request.GET.get('operador')
        if operador_id:
            queryset = queryset.filter(operador_id=operador_id)
        
        # Filtro por unidad
        unidad_id = self.request.GET.get('unidad')
        if unidad_id:
            queryset = queryset.filter(unidad_id=unidad_id)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_bitacoras'] = BitacoraViaje.objects.count()
        context['viajes_completados'] = BitacoraViaje.objects.filter(completado=True).count()
        context['viajes_en_curso'] = BitacoraViaje.objects.filter(completado=False).count()
        context['modalidad_choices'] = BitacoraViaje.MODALIDAD_CHOICES
        return context


class BitacoraDetailView(LoginRequiredMixin, DetailView):
    """Vista de detalle de una bitácora de viaje"""
    model = BitacoraViaje
    template_name = 'bitacoras/bitacora_detail.html'
    context_object_name = 'bitacora'


class BitacoraCreateView(LoginRequiredMixin, CreateView):
    """Vista para crear una nueva bitácora de viaje"""
    model = BitacoraViaje
    form_class = BitacoraViajeForm
    template_name = 'bitacoras/bitacora_form.html'
    success_url = reverse_lazy('bitacoras:list')
    
    def form_valid(self, form):
        bitacora = form.save()
        
        # Intentar calcular distancia con Google Maps si hay código postal destino
        if bitacora.cp_destino:
            api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
            if api_key:
                resultado = bitacora.calcular_distancia_google(api_key)
                if resultado['status'] == 'success':
                    messages.success(
                        self.request,
                        f'Bitácora creada. Distancia calculada: {resultado["distancia_km"]} km'
                    )
                else:
                    messages.warning(
                        self.request,
                        f'Bitácora creada, pero no se pudo calcular la distancia: {resultado.get("message", "Error desconocido")}'
                    )
            else:
                messages.success(self.request, 'Bitácora creada exitosamente.')
        else:
            messages.success(self.request, 'Bitácora creada exitosamente.')
        
        return redirect(self.success_url)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Error al crear la bitácora. Verifique los datos.')
        return super().form_invalid(form)


class BitacoraUpdateView(LoginRequiredMixin, UpdateView):
    """Vista para actualizar una bitácora de viaje"""
    model = BitacoraViaje
    form_class = BitacoraViajeForm
    template_name = 'bitacoras/bitacora_form.html'
    success_url = reverse_lazy('bitacoras:list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Bitácora actualizada exitosamente.')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Error al actualizar la bitácora. Verifique los datos.')
        return super().form_invalid(form)


class BitacoraDeleteView(LoginRequiredMixin, DeleteView):
    """Vista para eliminar una bitácora de viaje"""
    model = BitacoraViaje
    template_name = 'bitacoras/bitacora_confirm_delete.html'
    success_url = reverse_lazy('bitacoras:list')
    
    def delete(self, request, *args, **kwargs):
        bitacora = self.get_object()
        messages.success(request, f'Bitácora #{bitacora.id} eliminada exitosamente.')
        return super().delete(request, *args, **kwargs)


# Vista funcional para completar viaje
def completar_viaje(request, pk):
    """Vista para completar un viaje (agregar datos de llegada)"""
    bitacora = get_object_or_404(BitacoraViaje, pk=pk)
    
    if request.method == 'POST':
        form = BitacoraViajeCompletarForm(request.POST, instance=bitacora)
        if form.is_valid():
            form.save()
            messages.success(request, f'Viaje completado exitosamente.')
            return redirect('bitacoras:detail', pk=pk)
    else:
        form = BitacoraViajeCompletarForm(instance=bitacora)
    
    return render(request, 'bitacoras/completar_viaje.html', {
        'form': form,
        'bitacora': bitacora
    })


# Vista funcional para dashboard
def bitacora_dashboard(request):
    """Dashboard de bitácoras con estadísticas generales"""
    bitacoras = BitacoraViaje.objects.select_related('operador', 'unidad')
    completadas = bitacoras.filter(completado=True)
    
    # Estadísticas de rendimiento
    total_diesel = completadas.aggregate(total=Sum('diesel_cargado'))['total'] or 0
    total_km = sum(b.kilometros_recorridos for b in completadas if b.kilometros_recorridos)
    
    context = {
        'total_bitacoras': bitacoras.count(),
        'viajes_completados': completadas.count(),
        'viajes_en_curso': bitacoras.filter(completado=False).count(),
        'bitacoras_por_modalidad': {
            modalidad[0]: bitacoras.filter(modalidad=modalidad[0]).count()
            for modalidad in BitacoraViaje.MODALIDAD_CHOICES
        },
        'bitacoras_recientes': bitacoras.order_by('-fecha_salida')[:10],
        'total_diesel_consumido': total_diesel,
        'total_km_recorridos': total_km,
        'rendimiento_promedio': round(total_km / total_diesel, 2) if total_diesel > 0 else 0,
        'alertas_bajo_rendimiento': [
            b for b in completadas if b.alerta_bajo_rendimiento
        ][:5],
    }
    return render(request, 'bitacoras/bitacora_dashboard.html', context)


# Vista AJAX para calcular distancia
def calcular_distancia_ajax(request, pk):
    """Endpoint AJAX para calcular distancia con Google Maps"""
    if request.method == 'POST':
        bitacora = get_object_or_404(BitacoraViaje, pk=pk)
        api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
        
        if not api_key:
            return JsonResponse({
                'success': False,
                'error': 'API key de Google Maps no configurada'
            })
        
        resultado = bitacora.calcular_distancia_google(api_key)
        
        if resultado['status'] == 'success':
            return JsonResponse({
                'success': True,
                'distancia_km': resultado['distancia_km'],
                'duracion_min': resultado['duracion_min'],
                'distancia_texto': resultado.get('distancia_texto', ''),
                'duracion_texto': resultado.get('duracion_texto', '')
            })
        else:
            return JsonResponse({
                'success': False,
                'error': resultado.get('message', 'Error desconocido')
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})
