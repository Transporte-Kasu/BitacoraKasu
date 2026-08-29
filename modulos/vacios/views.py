import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, DeleteView, UpdateView

from .forms import (
    AsignarUnidadOperadorVacioForm,
    NavieraForm,
    ReasignarOperadorVacioForm,
    RetrasoVacioForm,
    VacioUpdateForm,
)
from .models import CambioOperadorVacio, Naviera, RetrasoVacio, Vacio
from .notificaciones import notificar_retraso_agencia

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
        context['reasignar_form'] = ReasignarOperadorVacioForm(vacio=self.object)
        return context


def _map_unidad_operador():
    """JSON {unidad_id: operador_id} para auto-llenar el operador en el navegador."""
    from modulos.operadores.models import Operador
    pares = (
        Operador.objects
        .filter(tipo='LOCAL', activo=True, unidad_asignada__isnull=False)
        .values_list('unidad_asignada_id', 'id')
    )
    return json.dumps({str(u): o for u, o in pares})


class VacioUpdateView(LoginRequiredMixin, UpdateView):
    model = Vacio
    form_class = VacioUpdateForm
    template_name = 'vacios/vacio_form.html'

    def get_success_url(self):
        messages.success(self.request, 'Datos del vacío actualizados.')
        return reverse('vacios:detail', kwargs={'pk': self.object.pk})


class VacioDeleteView(LoginRequiredMixin, DeleteView):
    model = Vacio
    template_name = 'vacios/vacio_confirm_delete.html'
    success_url = reverse_lazy('vacios:list')

    def post(self, request, *args, **kwargs):
        messages.success(request, 'Vacío eliminado.')
        return super().post(request, *args, **kwargs)


class AsignarUnidadOperadorVacioView(LoginRequiredMixin, UpdateView):
    model = Vacio
    form_class = AsignarUnidadOperadorVacioForm
    template_name = 'vacios/asignar_unidad_operador.html'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.estado != 'EN_PATIO_ESPERANZA':
            messages.warning(request, 'El vacío debe estar en Patio Esperanza para asignarse.')
            return redirect(reverse('vacios:detail', kwargs={'pk': self.object.pk}))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unidad_operador_map'] = _map_unidad_operador()
        return context

    def form_valid(self, form):
        vacio = form.save(commit=False)
        vacio.estado = 'ASIGNADO'
        if vacio.fecha_asignacion is None:
            vacio.fecha_asignacion = timezone.now()
        vacio.save()
        messages.success(self.request, f'Unidad y operador asignados a {vacio.folio}.')
        return redirect(reverse('vacios:detail', kwargs={'pk': vacio.pk}))


@login_required
@require_POST
def registrar_retorno_patio(request, pk):
    vacio = get_object_or_404(Vacio, pk=pk)
    if vacio.estado != 'POR_VACIAR':
        messages.warning(request, 'Solo un vacío "por vaciar" puede registrar retorno a patio.')
        return redirect(reverse('vacios:detail', kwargs={'pk': pk}))
    vacio.estado = 'EN_PATIO_ESPERANZA'
    if vacio.fecha_retorno_patio is None:
        vacio.fecha_retorno_patio = timezone.now()
    vacio.save()
    messages.success(request, f'{vacio.folio} en Patio Esperanza.')
    return redirect(reverse('vacios:detail', kwargs={'pk': pk}))


@login_required
@require_POST
def reasignar_operador(request, pk):
    vacio = get_object_or_404(Vacio, pk=pk)
    if vacio.estado != 'ASIGNADO':
        messages.warning(request, 'Solo un vacío asignado puede reasignarse.')
        return redirect(reverse('vacios:detail', kwargs={'pk': pk}))

    form = ReasignarOperadorVacioForm(request.POST, vacio=vacio)
    if not form.is_valid():
        messages.error(request, 'Revisa los datos de la reasignación.')
        return redirect(reverse('vacios:detail', kwargs={'pk': pk}))

    CambioOperadorVacio.objects.create(
        vacio=vacio,
        unidad_saliente=vacio.unidad,
        unidad_entrante=form.cleaned_data['unidad_entrante'],
        operador_saliente=vacio.operador,
        operador_entrante=form.cleaned_data['operador_entrante'],
        causa=form.cleaned_data['causa'],
        motivo=form.cleaned_data.get('motivo', ''),
        creado_por=request.user,
    )
    vacio.unidad = form.cleaned_data['unidad_entrante']
    vacio.operador = form.cleaned_data['operador_entrante']
    vacio.save()
    messages.success(request, f'Operador reasignado en {vacio.folio}.')
    return redirect(reverse('vacios:detail', kwargs={'pk': pk}))


@login_required
@require_POST
def registrar_salida_naviera(request, pk):
    vacio = get_object_or_404(Vacio, pk=pk)
    if vacio.estado != 'ASIGNADO':
        messages.warning(request, 'El vacío debe estar asignado para registrar la salida.')
        return redirect(reverse('vacios:detail', kwargs={'pk': pk}))
    if vacio.fecha_salida_naviera is None:
        vacio.fecha_salida_naviera = timezone.now()
        vacio.save()
    messages.success(request, f'Salida a naviera registrada para {vacio.folio}.')
    return redirect(reverse('vacios:detail', kwargs={'pk': pk}))


@login_required
@require_POST
def registrar_entrega_naviera(request, pk):
    vacio = get_object_or_404(Vacio, pk=pk)
    if vacio.estado != 'ASIGNADO':
        messages.warning(request, 'El vacío debe estar asignado para registrar la entrega.')
        return redirect(reverse('vacios:detail', kwargs={'pk': pk}))
    vacio.estado = 'ENTREGADO_NAVIERA'
    vacio.fecha_entrega_naviera = timezone.now()
    vacio.save()
    messages.success(request, f'{vacio.folio} entregado a la naviera.')
    return redirect(reverse('vacios:detail', kwargs={'pk': pk}))


class RegistrarRetrasoView(LoginRequiredMixin, UpdateView):
    model = Vacio
    form_class = RetrasoVacioForm
    template_name = 'vacios/registrar_retraso.html'
    context_object_name = 'vacio'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop('instance', None)  # el form es de RetrasoVacio, no de Vacio
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.estado == 'ENTREGADO_NAVIERA':
            messages.warning(request, 'El vacío ya fue entregado; no se registran retrasos.')
            return redirect(reverse('vacios:detail', kwargs={'pk': self.object.pk}))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        retraso = form.save(commit=False)
        retraso.vacio = self.object
        retraso.creado_por = self.request.user
        retraso.save()

        self.object.tiene_retraso = True
        self.object.save(update_fields=['tiene_retraso'])

        if notificar_retraso_agencia(retraso):
            messages.success(self.request, 'Retraso registrado y agencia notificada por correo.')
        else:
            messages.warning(
                self.request,
                'Retraso registrado, pero no se pudo notificar a la agencia '
                '(sin correo de contacto o falló el envío). Captura el correo en '
                '"Editar datos" y usa "Reenviar aviso".',
            )
        return redirect(reverse('vacios:detail', kwargs={'pk': self.object.pk}))


@login_required
@require_POST
def reenviar_aviso_retraso(request, pk, rid):
    vacio = get_object_or_404(Vacio, pk=pk)
    retraso = get_object_or_404(RetrasoVacio, pk=rid, vacio=vacio)
    if notificar_retraso_agencia(retraso):
        messages.success(request, 'Aviso reenviado a la agencia.')
    else:
        messages.error(request, 'No se pudo enviar el aviso. Revisa el correo de la agencia.')
    return redirect(reverse('vacios:detail', kwargs={'pk': pk}))


# ============================================================================
# CATÁLOGO: NAVIERA
# ============================================================================

class NavieraListView(LoginRequiredMixin, ListView):
    model = Naviera
    template_name = 'vacios/naviera_list.html'
    context_object_name = 'navieras'


class NavieraCreateView(LoginRequiredMixin, CreateView):
    model = Naviera
    form_class = NavieraForm
    template_name = 'vacios/naviera_form.html'
    success_url = reverse_lazy('vacios:naviera_list')

    def form_valid(self, form):
        messages.success(self.request, 'Naviera creada.')
        return super().form_valid(form)


class NavieraUpdateView(LoginRequiredMixin, UpdateView):
    model = Naviera
    form_class = NavieraForm
    template_name = 'vacios/naviera_form.html'
    success_url = reverse_lazy('vacios:naviera_list')

    def form_valid(self, form):
        messages.success(self.request, 'Naviera actualizada.')
        return super().form_valid(form)


class NavieraDeleteView(LoginRequiredMixin, DeleteView):
    model = Naviera
    template_name = 'vacios/naviera_confirm_delete.html'
    success_url = reverse_lazy('vacios:naviera_list')

    def post(self, request, *args, **kwargs):
        messages.success(request, 'Naviera eliminada.')
        return super().post(request, *args, **kwargs)
