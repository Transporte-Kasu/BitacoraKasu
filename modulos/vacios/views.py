from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import DetailView, ListView

from .models import Naviera, Vacio

_MESES = [
    (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
    (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
    (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre'),
]


@login_required
def vacios_dashboard(request):
    qs = Vacio.objects.all()
    context = {
        'total': qs.count(),
        'por_vaciar': qs.filter(estado='POR_VACIAR').count(),
        'en_patio_esperanza': qs.filter(estado='EN_PATIO_ESPERANZA').count(),
        'asignados': qs.filter(estado='ASIGNADO').count(),
        'entregados_naviera': qs.filter(estado='ENTREGADO_NAVIERA').count(),
        'retrasos_abiertos': qs.filter(tiene_retraso=True).exclude(estado='ENTREGADO_NAVIERA').count(),
        'recientes': qs.select_related('cliente', 'naviera', 'operador')[:10],
    }
    return render(request, 'vacios/dashboard.html', context)


class VacioListView(LoginRequiredMixin, ListView):
    """Lista de vacíos filtrada por mes/año de fecha_entrega_cliente."""
    model = Vacio
    template_name = 'vacios/vacio_list.html'
    context_object_name = 'vacios'
    paginate_by = 25

    def get_queryset(self):
        qs = Vacio.objects.select_related('cliente', 'naviera', 'operador', 'unidad', 'bitacora_viaje')

        hoy = timezone.localdate()
        anio = int(self.request.GET.get('anio') or hoy.year)
        mes = int(self.request.GET.get('mes') or hoy.month)
        qs = qs.filter(fecha_entrega_cliente__year=anio, fecha_entrega_cliente__month=mes)

        estado = self.request.GET.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        naviera_id = self.request.GET.get('naviera')
        if naviera_id:
            qs = qs.filter(naviera_id=naviera_id)

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(folio__icontains=search) |
                Q(contenedor__icontains=search) |
                Q(cliente__nombre__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        context['estado_choices'] = Vacio.ESTADO_CHOICES
        context['navieras_list'] = Naviera.objects.filter(activo=True)
        context['anio_actual'] = int(self.request.GET.get('anio') or hoy.year)
        context['mes_actual'] = int(self.request.GET.get('mes') or hoy.month)
        context['anios_disponibles'] = range(hoy.year - 3, hoy.year + 1)
        context['meses_disponibles'] = _MESES
        return context


class VacioDetailView(LoginRequiredMixin, DetailView):
    model = Vacio
    template_name = 'vacios/vacio_detail.html'
    context_object_name = 'vacio'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['retrasos'] = self.object.retrasos.all()
        context['cambios_operador'] = self.object.cambios_operador.select_related(
            'operador_saliente', 'operador_entrante', 'unidad_saliente', 'unidad_entrante'
        )
        return context
