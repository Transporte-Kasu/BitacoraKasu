from datetime import datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils import timezone

from .models import ConfiguracionReporte, ReporteGenerado
from .forms import ConfiguracionReporteForm
from .generadores.modulacion import generar_contenedores_por_operador
from .generadores.vacios import generar_entregas_por_operador


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


class ContenedoresPorOperadorView(LoginRequiredMixin, TemplateView):
    """Vista bajo demanda del reporte de contenedores extraídos por operador.

    Reutiliza el mismo generador que el reporte programado del módulo
    reportes; sólo cambia el rango, que aquí lo elige el usuario.
    """
    template_name = 'reportes/contenedores_por_operador.html'

    def _parse_fecha(self, valor):
        try:
            return datetime.strptime(valor, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        hoy = timezone.localdate()
        default_hasta = hoy - timedelta(days=1)
        default_desde = default_hasta - timedelta(days=6)

        desde = self._parse_fecha(self.request.GET.get('desde'))
        hasta = self._parse_fecha(self.request.GET.get('hasta'))

        if self.request.GET and (desde is None or hasta is None):
            messages.warning(self.request, 'Rango de fechas inválido; se muestra la última semana.')

        if desde is None:
            desde = default_desde
        if hasta is None:
            hasta = default_hasta
        if desde > hasta:
            desde, hasta = hasta, desde

        ctx['datos'] = generar_contenedores_por_operador(desde, hasta)
        ctx['desde'] = desde
        ctx['hasta'] = hasta
        return ctx


class EntregasVaciosPorOperadorView(LoginRequiredMixin, TemplateView):
    """Vista bajo demanda del reporte de entregas de vacíos por operador."""
    template_name = 'reportes/entregas_vacios_por_operador.html'

    def _parse_fecha(self, valor):
        try:
            return datetime.strptime(valor, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        default_hasta = hoy - timedelta(days=1)
        default_desde = default_hasta - timedelta(days=6)

        desde = self._parse_fecha(self.request.GET.get('desde'))
        hasta = self._parse_fecha(self.request.GET.get('hasta'))

        if self.request.GET and (desde is None or hasta is None):
            messages.warning(self.request, 'Rango de fechas inválido; se muestra la última semana.')

        if desde is None:
            desde = default_desde
        if hasta is None:
            hasta = default_hasta
        if desde > hasta:
            desde, hasta = hasta, desde

        ctx['datos'] = generar_entregas_por_operador(desde, hasta)
        ctx['desde'] = desde
        ctx['hasta'] = hasta
        return ctx


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
