from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Q, Count
from .models import Operador
from .forms import OperadorForm


class OperadorListView(LoginRequiredMixin, ListView):
    """Vista para listar todos los operadores"""
    model = Operador
    template_name = 'operadores/operador_list.html'
    context_object_name = 'operadores'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Operador.objects.select_related('unidad_asignada').annotate(
            total_viajes=Count('bitacoras')
        )
        
        # Filtro por búsqueda
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(nombre__icontains=search) |
                Q(licencia__icontains=search) |
                Q(telefono__icontains=search)
            )
        
        # Filtro por tipo
        tipo = self.request.GET.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        
        # Filtro por estado
        activo = self.request.GET.get('activo')
        if activo == 'true':
            queryset = queryset.filter(activo=True)
        elif activo == 'false':
            queryset = queryset.filter(activo=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_operadores'] = Operador.objects.count()
        context['operadores_activos'] = Operador.objects.filter(activo=True).count()
        context['tipos_choices'] = Operador.TIPO_CHOICES
        return context


class OperadorDetailView(LoginRequiredMixin, DetailView):
    """Vista de detalle de un operador"""
    model = Operador
    template_name = 'operadores/operador_detail.html'
    context_object_name = 'operador'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        operador = self.get_object()
        
        # Obtener últimos viajes
        context['ultimos_viajes'] = operador.bitacoras.select_related(
            'unidad'
        ).order_by('-fecha_salida')[:10]
        
        # Estadísticas
        context['viajes_completados'] = operador.viajes_completados()
        context['rendimiento_promedio'] = operador.promedio_rendimiento()
        
        return context


class OperadorCreateView(LoginRequiredMixin, CreateView):
    """Vista para crear un nuevo operador"""
    model = Operador
    form_class = OperadorForm
    template_name = 'operadores/operador_form.html'
    success_url = reverse_lazy('operadores:list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Operador {form.instance.nombre} creado exitosamente.')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Error al crear el operador. Verifique los datos.')
        return super().form_invalid(form)


class OperadorUpdateView(LoginRequiredMixin, UpdateView):
    """Vista para actualizar un operador"""
    model = Operador
    form_class = OperadorForm
    template_name = 'operadores/operador_form.html'
    success_url = reverse_lazy('operadores:list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Operador {form.instance.nombre} actualizado exitosamente.')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Error al actualizar el operador. Verifique los datos.')
        return super().form_invalid(form)


class OperadorDeleteView(LoginRequiredMixin, DeleteView):
    """Vista para eliminar un operador"""
    model = Operador
    template_name = 'operadores/operador_confirm_delete.html'
    success_url = reverse_lazy('operadores:list')
    
    def delete(self, request, *args, **kwargs):
        operador = self.get_object()
        messages.success(request, f'Operador {operador.nombre} eliminado exitosamente.')
        return super().delete(request, *args, **kwargs)


# Vista funcional para dashboard
def operador_dashboard(request):
    """Dashboard de operadores con estadísticas generales"""
    context = {
        'total_operadores': Operador.objects.count(),
        'operadores_activos': Operador.objects.filter(activo=True).count(),
        'operadores_inactivos': Operador.objects.filter(activo=False).count(),
        'operadores_por_tipo': {
            tipo[0]: Operador.objects.filter(tipo=tipo[0]).count()
            for tipo in Operador.TIPO_CHOICES
        },
        'operadores_recientes': Operador.objects.order_by('-created_at')[:5],
    }
    return render(request, 'operadores/operador_dashboard.html', context)
