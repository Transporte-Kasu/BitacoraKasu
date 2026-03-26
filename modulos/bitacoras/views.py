from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Sum
from django.http import JsonResponse
from .models import BitacoraViaje
from .forms import BitacoraViajeForm, BitacoraViajeCompletarForm
import os


class BitacoraListView(LoginRequiredMixin, ListView):
    model = BitacoraViaje
    template_name = 'bitacoras/bitacora_list.html'
    context_object_name = 'bitacoras'
    paginate_by = 20

    def get_queryset(self):
        queryset = BitacoraViaje.objects.select_related(
            'operador', 'unidad'
        ).order_by('-fecha_salida')

        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(contenedor__icontains=search) |
                Q(contenedor_2__icontains=search) |
                Q(destino__icontains=search) |
                Q(operador__nombre__icontains=search) |
                Q(unidad__numero_economico__icontains=search)
            )

        modalidad = self.request.GET.get('modalidad')
        if modalidad:
            queryset = queryset.filter(modalidad=modalidad)

        completado = self.request.GET.get('completado')
        if completado == 'true':
            queryset = queryset.filter(completado=True)
        elif completado == 'false':
            queryset = queryset.filter(completado=False)

        operador_id = self.request.GET.get('operador')
        if operador_id:
            queryset = queryset.filter(operador_id=operador_id)

        unidad_id = self.request.GET.get('unidad')
        if unidad_id:
            queryset = queryset.filter(unidad_id=unidad_id)

        fecha_desde = self.request.GET.get('fecha_desde')
        if fecha_desde:
            queryset = queryset.filter(fecha_salida__date__gte=fecha_desde)

        fecha_hasta = self.request.GET.get('fecha_hasta')
        if fecha_hasta:
            queryset = queryset.filter(fecha_salida__date__lte=fecha_hasta)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from modulos.operadores.models import Operador
        from modulos.unidades.models import Unidad
        context['total_bitacoras'] = BitacoraViaje.objects.count()
        context['viajes_completados'] = BitacoraViaje.objects.filter(completado=True).count()
        context['viajes_en_curso'] = BitacoraViaje.objects.filter(completado=False).count()
        context['modalidad_choices'] = BitacoraViaje.MODALIDAD_CHOICES
        context['operadores_list'] = Operador.objects.filter(activo=True).order_by('nombre')
        context['unidades_list'] = Unidad.objects.filter(activa=True).order_by('numero_economico')
        return context


class BitacoraDetailView(LoginRequiredMixin, DetailView):
    model = BitacoraViaje
    template_name = 'bitacoras/bitacora_detail.html'
    context_object_name = 'bitacora'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        bitacora = self.object
        context['es_full'] = bitacora.modalidad in ('FULL', 'LOCAL_FULL')
        context['tiene_distancia'] = bool(bitacora.distancia_calculada)
        context['tiene_distancia_2'] = bool(bitacora.distancia_calculada_2)
        return context


def _form_context():
    """Contexto compartido entre Create y Update: listas de unidades y operadores."""
    from modulos.operadores.models import Operador
    from modulos.unidades.models import Unidad
    return {
        'unidades_form': Unidad.objects.filter(activa=True).order_by('numero_economico'),
        'operadores_form': Operador.objects.filter(activo=True).order_by('nombre'),
    }


class BitacoraCreateView(LoginRequiredMixin, CreateView):
    model = BitacoraViaje
    form_class = BitacoraViajeForm
    template_name = 'bitacoras/bitacora_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_form_context())
        return context

    def form_valid(self, form):
        bitacora = form.save()

        if bitacora.cp_destino:
            api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
            if api_key:
                resultado = bitacora.calcular_distancia_google(api_key)
                if resultado['status'] == 'success':
                    messages.success(
                        self.request,
                        f'Bitácora creada. Distancia calculada: {resultado["distancia_texto"]} '
                        f'· {resultado["duracion_texto"]}'
                    )
                else:
                    messages.warning(
                        self.request,
                        f'Bitácora creada, pero no se pudo calcular la distancia: '
                        f'{resultado.get("message", "Error desconocido")}'
                    )
            else:
                messages.success(self.request, 'Bitácora creada exitosamente.')
        else:
            messages.success(self.request, 'Bitácora creada exitosamente.')

        return redirect(reverse('bitacoras:detail', kwargs={'pk': bitacora.pk}))

    def form_invalid(self, form):
        messages.error(self.request, 'Error al crear la bitácora. Verifique los datos.')
        return super().form_invalid(form)


class BitacoraUpdateView(LoginRequiredMixin, UpdateView):
    model = BitacoraViaje
    form_class = BitacoraViajeForm
    template_name = 'bitacoras/bitacora_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_form_context())
        return context

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse('bitacoras:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'Bitácora actualizada exitosamente.')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Error al actualizar la bitácora. Verifique los datos.')
        return super().form_invalid(form)


class BitacoraDeleteView(LoginRequiredMixin, DeleteView):
    model = BitacoraViaje
    template_name = 'bitacoras/bitacora_confirm_delete.html'

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse_lazy('bitacoras:list')

    def post(self, request, *args, **kwargs):
        bitacora = self.get_object()
        messages.success(request, f'Bitácora #{bitacora.id} eliminada exitosamente.')
        return super().post(request, *args, **kwargs)


# ============================================================================
# VISTAS FUNCIONALES
# ============================================================================

def completar_viaje(request, pk):
    bitacora = get_object_or_404(BitacoraViaje, pk=pk)

    if request.method == 'POST':
        form = BitacoraViajeCompletarForm(request.POST, instance=bitacora)
        if form.is_valid():
            form.save()
            messages.success(request, 'Viaje completado exitosamente.')
            return redirect('bitacoras:detail', pk=pk)
    else:
        form = BitacoraViajeCompletarForm(instance=bitacora)

    return render(request, 'bitacoras/completar_viaje.html', {
        'form': form,
        'bitacora': bitacora,
    })


def bitacora_dashboard(request):
    bitacoras = BitacoraViaje.objects.select_related('operador', 'unidad')
    completadas = bitacoras.filter(completado=True)

    total_diesel = completadas.aggregate(total=Sum('diesel_cargado'))['total'] or 0
    total_km = sum(b.kilometros_recorridos for b in completadas if b.kilometros_recorridos)

    context = {
        'total_bitacoras': bitacoras.count(),
        'viajes_completados': completadas.count(),
        'viajes_en_curso': bitacoras.filter(completado=False).count(),
        'bitacoras_por_modalidad': {
            m[0]: bitacoras.filter(modalidad=m[0]).count()
            for m in BitacoraViaje.MODALIDAD_CHOICES
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


# ============================================================================
# ENDPOINTS AJAX
# ============================================================================

def calcular_distancia_ajax(request, pk):
    """Recalcula distancia para una bitácora ya guardada."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})

    bitacora = get_object_or_404(BitacoraViaje, pk=pk)
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')

    if not api_key:
        return JsonResponse({'success': False, 'error': 'API key de Google Maps no configurada'})

    resultado = bitacora.calcular_distancia_google(api_key)

    if resultado['status'] == 'success':
        return JsonResponse({
            'success': True,
            'distancia_km': resultado['distancia_km'],
            'duracion_min': resultado['duracion_min'],
            'distancia_texto': resultado.get('distancia_texto', ''),
            'duracion_texto': resultado.get('duracion_texto', ''),
        })
    return JsonResponse({'success': False, 'error': resultado.get('message', 'Error desconocido')})


def calcular_distancia_preview_ajax(request):
    """
    Calcula distancia en tiempo real para preview en el form (sin pk).
    GET /bitacoras/ajax/calcular-distancia/?cp_origen=40812&cp_destino=06600
    """
    cp_origen = request.GET.get('cp_origen', '40812').strip()
    cp_destino = request.GET.get('cp_destino', '').strip()

    if not cp_destino:
        return JsonResponse({'success': False, 'error': 'Falta el código postal destino'})

    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        return JsonResponse({'success': False, 'error': 'API key no configurada'})

    from config.services.google_maps import GoogleMapsService
    maps_service = GoogleMapsService(api_key)
    resultado = maps_service.calcular_distancia(cp_origen, cp_destino)

    if resultado['success']:
        return JsonResponse({
            'success': True,
            'distancia_km': round(resultado['distancia_km'], 1),
            'duracion_min': int(resultado['duracion_min']),
            'distancia_texto': resultado['distancia_texto'],
            'duracion_texto': resultado['duracion_texto'],
            'origen_formateado': resultado.get('origen_formateado', ''),
            'destino_formateado': resultado.get('destino_formateado', ''),
        })
    return JsonResponse({'success': False, 'error': resultado.get('error', 'No se pudo calcular la ruta')})


def unidad_info_ajax(request):
    """
    Devuelve placa, kilometraje, tipo y operador asignado de una unidad.
    GET /bitacoras/ajax/unidad-info/?unidad_id=X
    """
    unidad_id = request.GET.get('unidad_id', '').strip()
    if not unidad_id:
        return JsonResponse({'success': False, 'error': 'Falta unidad_id'})

    from modulos.unidades.models import Unidad
    from modulos.operadores.models import Operador
    try:
        u = Unidad.objects.get(pk=unidad_id)
        # Buscar el operador activo asignado a esta unidad
        operador = Operador.objects.filter(
            unidad_asignada=u, activo=True
        ).first()
        return JsonResponse({
            'success': True,
            'placa': u.placa,
            'kilometraje_actual': u.kilometraje_actual,
            'numero_economico': u.numero_economico,
            'tipo': u.tipo,
            'operador_id': operador.pk if operador else None,
            'operador_nombre': operador.nombre if operador else None,
        })
    except Unidad.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Unidad no encontrada'})
