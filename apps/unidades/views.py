from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q, Count, Avg
from .models import Unidad
from .forms import UnidadForm


class UnidadListView(LoginRequiredMixin, ListView):
    """Vista para listar todas las unidades"""
    model = Unidad
    template_name = 'unidades/unidad_list.html'
    context_object_name = 'unidades'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Unidad.objects.annotate(
            total_viajes=Count('bitacoras')
        )
        
        # Filtro por búsqueda
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(numero_economico__icontains=search) |
                Q(placa__icontains=search) |
                Q(marca__icontains=search) |
                Q(modelo__icontains=search)
            )
        
        # Filtro por tipo
        tipo = self.request.GET.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        
        # Filtro por estado
        activa = self.request.GET.get('activa')
        if activa == 'true':
            queryset = queryset.filter(activa=True)
        elif activa == 'false':
            queryset = queryset.filter(activa=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_unidades'] = Unidad.objects.count()
        context['unidades_activas'] = Unidad.objects.filter(activa=True).count()
        context['tipos_choices'] = Unidad.TIPO_CHOICES
        return context


class UnidadDetailView(LoginRequiredMixin, DetailView):
    """Vista de detalle de una unidad"""
    model = Unidad
    template_name = 'unidades/unidad_detail.html'
    context_object_name = 'unidad'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        unidad = self.get_object()
        
        # Obtener últimos viajes
        context['ultimos_viajes'] = unidad.bitacoras.select_related(
            'operador'
        ).order_by('-fecha_salida')[:10]
        
        # Estadísticas
        context['viajes_completados'] = unidad.viajes_completados()
        context['rendimiento_promedio'] = unidad.rendimiento_promedio_real()
        context['eficiencia'] = unidad.eficiencia_combustible()
        context['requiere_mantenimiento'] = unidad.requiere_mantenimiento()
        
        # Operadores asignados
        context['operadores_asignados'] = unidad.operadores.filter(activo=True)
        
        return context


class UnidadCreateView(LoginRequiredMixin, CreateView):
    """Vista para crear una nueva unidad"""
    model = Unidad
    form_class = UnidadForm
    template_name = 'unidades/unidad_form.html'
    success_url = reverse_lazy('unidades:list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Unidad {form.instance.numero_economico} creada exitosamente.')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Error al crear la unidad. Verifique los datos.')
        return super().form_invalid(form)


class UnidadUpdateView(LoginRequiredMixin, UpdateView):
    """Vista para actualizar una unidad"""
    model = Unidad
    form_class = UnidadForm
    template_name = 'unidades/unidad_form.html'
    success_url = reverse_lazy('unidades:list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Unidad {form.instance.numero_economico} actualizada exitosamente.')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Error al actualizar la unidad. Verifique los datos.')
        return super().form_invalid(form)


class UnidadDeleteView(LoginRequiredMixin, DeleteView):
    """Vista para eliminar una unidad"""
    model = Unidad
    template_name = 'unidades/unidad_confirm_delete.html'
    success_url = reverse_lazy('unidades:list')
    
    def delete(self, request, *args, **kwargs):
        unidad = self.get_object()
        messages.success(request, f'Unidad {unidad.numero_economico} eliminada exitosamente.')
        return super().delete(request, *args, **kwargs)


# Vista funcional para dashboard
def unidad_dashboard(request):
    """Dashboard de unidades con estadísticas generales"""
    unidades = Unidad.objects.all()
    
    context = {
        'total_unidades': unidades.count(),
        'unidades_activas': unidades.filter(activa=True).count(),
        'unidades_inactivas': unidades.filter(activa=False).count(),
        'unidades_por_tipo': {
            tipo[0]: unidades.filter(tipo=tipo[0]).count()
            for tipo in Unidad.TIPO_CHOICES
        },
        'unidades_recientes': unidades.order_by('-created_at')[:5],
        'unidades_mantenimiento': [
            u for u in unidades.filter(activa=True) 
            if u.requiere_mantenimiento()
        ],
    }
    return render(request, 'unidades/unidad_dashboard.html', context)
