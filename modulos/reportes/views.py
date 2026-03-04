from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages

from .models import ConfiguracionReporte, ReporteGenerado
from .forms import ConfiguracionReporteForm


class HistorialReportesView(LoginRequiredMixin, ListView):
    """Lista el historial de reportes generados, del más reciente al más antiguo."""
    model = ReporteGenerado
    template_name = 'reportes/historial.html'
    context_object_name = 'reportes'
    paginate_by = 30

    def get_queryset(self):
        qs = ReporteGenerado.objects.select_related('configuracion').order_by('-fecha_generacion')
        modulo = self.request.GET.get('modulo')
        if modulo:
            qs = qs.filter(configuracion__modulo=modulo)
        estado = self.request.GET.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['modulo_choices'] = ConfiguracionReporte.MODULO_CHOICES
        ctx['estado_choices'] = ReporteGenerado.ESTADO_CHOICES
        ctx['modulo_filtro'] = self.request.GET.get('modulo', '')
        ctx['estado_filtro'] = self.request.GET.get('estado', '')
        return ctx


class DetalleReporteGeneradoView(LoginRequiredMixin, DetailView):
    """Muestra el resumen completo de un reporte generado."""
    model = ReporteGenerado
    template_name = 'reportes/detalle.html'
    context_object_name = 'reporte'


class ConfiguracionListView(LoginRequiredMixin, ListView):
    """Lista todas las configuraciones de reportes programados."""
    model = ConfiguracionReporte
    template_name = 'reportes/configuracion_list.html'
    context_object_name = 'configs'
    ordering = ['modulo', 'nombre']


class ConfiguracionCreateView(LoginRequiredMixin, CreateView):
    model = ConfiguracionReporte
    form_class = ConfiguracionReporteForm
    template_name = 'reportes/configuracion_form.html'
    success_url = reverse_lazy('reportes:configuracion_list')

    def form_valid(self, form):
        form.instance.creado_por = self.request.user
        messages.success(self.request, 'Configuración de reporte creada correctamente.')
        return super().form_valid(form)


class ConfiguracionUpdateView(LoginRequiredMixin, UpdateView):
    model = ConfiguracionReporte
    form_class = ConfiguracionReporteForm
    template_name = 'reportes/configuracion_form.html'
    success_url = reverse_lazy('reportes:configuracion_list')

    def form_valid(self, form):
        messages.success(self.request, 'Configuración actualizada correctamente.')
        return super().form_valid(form)


class ConfiguracionDeleteView(LoginRequiredMixin, DeleteView):
    model = ConfiguracionReporte
    template_name = 'reportes/configuracion_confirm_delete.html'
    success_url = reverse_lazy('reportes:configuracion_list')

    def form_valid(self, form):
        messages.success(self.request, 'Configuración eliminada.')
        return super().form_valid(form)
