import json
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from modulos.bitacoras.models import BitacoraViaje
from modulos.operadores.models import Operador

from .forms import (
    AgenciaForm,
    AsignarUnidadOperadorForm,
    DatosTerminalForm,
    ModulacionForm,
    PromoverBitacoraForm,
    RetiroExternoForm,
    TerminalPortuariaForm,
)
from .models import Agencia, Modulacion, TerminalPortuaria
from .tokens import resolver_modulacion


def _mapear_tipo_contenedor(tipo_contenedor):
    """Mapea el tipo crudo (ej. '40HC', '20DC') al choice de BitacoraViaje ('20'/'40')."""
    valor = (tipo_contenedor or '').strip().upper()
    if valor.startswith('20'):
        return '20'
    return '40'


def _crear_bitacora_desde_modulacion(modulacion, datos):
    """
    Crea (sin guardar) un BitacoraViaje modalidad SENCILLO (foráneo) con los
    datos del contenedor tomados de la Modulación y los datos operativos
    (operador, unidad, destino, fechas) capturados en `datos` (cleaned_data
    del form).
    """
    bitacora = BitacoraViaje(
        cliente=modulacion.cliente,
        modalidad='SENCILLO',
        operador=datos['operador'],
        unidad=datos['unidad'],
        contenedor=modulacion.contenedor,
        peso=modulacion.peso_toneladas,
        tipo_contenedor=_mapear_tipo_contenedor(modulacion.tipo_contenedor),
        fecha_carga=datos['fecha_carga'],
        fecha_salida=datos['fecha_salida'],
        destino=datos['destino'],
        cp_destino=datos.get('cp_destino', ''),
        observaciones=(
            f'Generado desde Modulación {modulacion.folio}'
            + (f' · Pedimento {modulacion.num_pedimento}' if modulacion.num_pedimento else '')
        ),
    )

    unidad = bitacora.unidad
    if unidad.kilometraje_actual:
        bitacora.kilometraje_salida = unidad.kilometraje_actual
    try:
        from modulos.combustible.models import CargaCombustible
        ultima_carga = (
            CargaCombustible.objects
            .filter(unidad=unidad, estado='COMPLETADO')
            .order_by('-fecha_hora_fin')
            .first()
        )
        if ultima_carga and ultima_carga.cantidad_litros:
            bitacora.diesel_cargado = ultima_carga.cantidad_litros
    except Exception:
        pass

    return bitacora


@login_required
def modulacion_dashboard(request):
    context = {
        'total': Modulacion.objects.count(),
        'pendientes': Modulacion.objects.filter(estado='PENDIENTE').count(),
        'modulados': Modulacion.objects.filter(estado='MODULADO').count(),
        'en_patio_esperanza': Modulacion.objects.filter(estado='EN_PATIO_ESPERANZA').count(),
        'enviados_bitacora': Modulacion.objects.filter(estado='ENVIADO_BITACORA').count(),
        'retirados_tercero': Modulacion.objects.filter(estado='RETIRADO_TERCERO').count(),
        'recientes': Modulacion.objects.select_related('agencia', 'terminal_portuaria', 'cliente')[:10],
    }
    return render(request, 'modulacion/dashboard.html', context)


class ModulacionListView(LoginRequiredMixin, ListView):
    """
    Lista de Modulaciones con DODA. Por default solo muestra las que tienen
    número de DODA asignado y cuya fecha de recepción cae en el mes/año en
    curso; `mes`/`anio` en el querystring permiten navegar a otros periodos.
    """
    model = Modulacion
    template_name = 'modulacion/modulacion_list.html'
    context_object_name = 'modulaciones'
    paginate_by = 25

    def get_queryset(self):
        qs = Modulacion.objects.select_related('agencia', 'terminal_portuaria', 'cliente', 'bitacora_viaje')
        qs = qs.exclude(num_doda='')

        hoy = timezone.localdate()
        anio = int(self.request.GET.get('anio') or hoy.year)
        mes = int(self.request.GET.get('mes') or hoy.month)
        qs = qs.filter(fecha_recepcion__year=anio, fecha_recepcion__month=mes)

        estado = self.request.GET.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        agencia_id = self.request.GET.get('agencia')
        if agencia_id:
            qs = qs.filter(agencia_id=agencia_id)

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(contenedor__icontains=search) |
                Q(folio__icontains=search) |
                Q(num_pedimento__icontains=search) |
                Q(num_doda__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        context['estado_choices'] = Modulacion.ESTADO_CHOICES
        context['agencias_list'] = Agencia.objects.filter(activo=True)
        context['anio_actual'] = int(self.request.GET.get('anio') or hoy.year)
        context['mes_actual'] = int(self.request.GET.get('mes') or hoy.month)
        context['anios_disponibles'] = range(hoy.year - 3, hoy.year + 1)
        context['meses_disponibles'] = [
            (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
            (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
            (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre'),
        ]
        return context


class ModulacionDetailView(LoginRequiredMixin, DetailView):
    model = Modulacion
    template_name = 'modulacion/modulacion_detail.html'
    context_object_name = 'modulacion'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['retiro_externo_form'] = RetiroExternoForm()
        return context


class ModulacionCreateView(LoginRequiredMixin, CreateView):
    model = Modulacion
    form_class = ModulacionForm
    template_name = 'modulacion/modulacion_form.html'

    def form_valid(self, form):
        modulacion = form.save(commit=False)
        modulacion.origen = 'MANUAL'
        modulacion.estado = 'MODULADO'
        modulacion.save()
        messages.success(self.request, f'Modulación {modulacion.folio} creada exitosamente.')
        return redirect(reverse('modulacion:detail', kwargs={'pk': modulacion.pk}))


class ModulacionUpdateView(LoginRequiredMixin, UpdateView):
    model = Modulacion
    form_class = ModulacionForm
    template_name = 'modulacion/modulacion_form.html'

    def form_valid(self, form):
        modulacion = form.save(commit=False)
        if modulacion.estado == 'PENDIENTE':
            modulacion.estado = 'MODULADO'
        modulacion.save()
        messages.success(self.request, f'Modulación {modulacion.folio} actualizada.')
        return redirect(reverse('modulacion:detail', kwargs={'pk': modulacion.pk}))


class AsignarUnidadOperadorView(LoginRequiredMixin, UpdateView):
    """
    Asigna (o reasigna) unidad y operador local a una Modulación. Se llega
    desde un botón en el detalle. Es independiente de "Enviar a Bitácora":
    aquí sólo se registran los datos en la Modulación (para el reporte de
    contenedores por operador), no se crea ningún viaje.
    """
    model = Modulacion
    form_class = AsignarUnidadOperadorForm
    template_name = 'modulacion/asignar_unidad_operador.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Mapa unidad -> operador ligado, para auto-llenar el operador en el
        # navegador al elegir una unidad (Operador.unidad_asignada).
        pares = (
            Operador.objects
            .filter(tipo='LOCAL', activo=True, unidad_asignada__isnull=False)
            .values_list('unidad_asignada_id', 'id')
        )
        context['unidad_operador_map'] = json.dumps({str(u): o for u, o in pares})
        return context

    def form_valid(self, form):
        modulacion = form.save(commit=False)
        if modulacion.fecha_asignacion is None:
            modulacion.fecha_asignacion = timezone.now()
        modulacion.save()
        messages.success(self.request, f'Unidad y operador asignados a {modulacion.folio}.')
        return redirect(reverse('modulacion:detail', kwargs={'pk': modulacion.pk}))


class ModulacionDeleteView(LoginRequiredMixin, DeleteView):
    model = Modulacion
    template_name = 'modulacion/modulacion_confirm_delete.html'
    success_url = reverse_lazy('modulacion:list')

    def post(self, request, *args, **kwargs):
        messages.success(request, 'Modulación eliminada.')
        return super().post(request, *args, **kwargs)


class EnviarABitacoraView(LoginRequiredMixin, View):
    """
    Formulario dedicado para promover una Modulación a Bitácora de Viajes.
    BitacoraViaje requiere operador/unidad/destino/fechas (no admiten NULL),
    así que se capturan aquí antes de crear el viaje — no se crean bitácoras
    incompletas.
    """
    template_name = 'modulacion/enviar_a_bitacora.html'

    def _redirige_si_no_esta_en_patio(self, request, modulacion):
        """El flujo es lineal: solo se envía a Bitácora desde Patio Esperanza."""
        if modulacion.estado != 'EN_PATIO_ESPERANZA':
            messages.warning(
                request,
                'El contenedor debe estar en Patio Esperanza para enviarse a Bitácora.',
            )
            return redirect(reverse('modulacion:detail', kwargs={'pk': modulacion.pk}))
        return None

    def get(self, request, pk):
        modulacion = get_object_or_404(Modulacion, pk=pk)
        redir = self._redirige_si_no_esta_en_patio(request, modulacion)
        if redir:
            return redir
        ahora = timezone.now()
        form = PromoverBitacoraForm(initial={'fecha_carga': ahora, 'fecha_salida': ahora})
        return render(request, self.template_name, {'modulacion': modulacion, 'form': form})

    def post(self, request, pk):
        modulacion = get_object_or_404(Modulacion, pk=pk)
        redir = self._redirige_si_no_esta_en_patio(request, modulacion)
        if redir:
            return redir
        form = PromoverBitacoraForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'modulacion': modulacion, 'form': form})

        # ¿La unidad + operador ya tienen un sencillo en curso? Ofrecer/forzar Full.
        from django.db import transaction
        from modulos.bitacoras.services_full import evaluar_fusion, fusionar_en_full

        cd = form.cleaned_data
        res = evaluar_fusion(
            cd['unidad'], cd['operador'], modulacion.cliente, cd.get('cp_destino') or '',
        )

        if res['accion'] == 'bloqueo':
            messages.warning(request, res['mensaje'])
            return render(request, self.template_name, {'modulacion': modulacion, 'form': form})

        if res['accion'] == 'ofrecer_full' and request.POST.get('confirmar_full') == '1':
            datos_segundo = {
                'contenedor': modulacion.contenedor,
                'peso': modulacion.peso_toneladas,
                'sellos': '',
                'cliente': modulacion.cliente,
                'cp_destino': cd.get('cp_destino') or '',
            }
            with transaction.atomic():
                full = fusionar_en_full(
                    res['sencillo'], datos_segundo, tipo_full=res['tipo_full'])
                modulacion.bitacora_viaje = full
                modulacion.estado = 'ENVIADO_BITACORA'
                modulacion.fecha_retiro = timezone.now()
                modulacion.save()
            messages.success(
                request,
                f'Modulación {modulacion.folio} unida al Full #{full.pk} (2 contenedores).')
            return redirect(reverse('bitacoras:detail', kwargs={'pk': full.pk}))

        if res['accion'] == 'ofrecer_full':
            messages.warning(
                request,
                'Esta unidad ya tiene un viaje sencillo en curso con este operador. '
                'Confirme la generación del Full para continuar.')
            return render(request, self.template_name, {'modulacion': modulacion, 'form': form})

        bitacora = _crear_bitacora_desde_modulacion(modulacion, form.cleaned_data)
        bitacora.full_clean()
        bitacora.save()

        if bitacora.cp_destino:
            api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
            if api_key:
                bitacora.calcular_distancia_google(api_key)

        modulacion.bitacora_viaje = bitacora
        modulacion.estado = 'ENVIADO_BITACORA'
        modulacion.fecha_retiro = timezone.now()
        modulacion.save()

        messages.success(
            request,
            f'Modulación {modulacion.folio} enviada a Bitácora de Viajes (viaje #{bitacora.pk}).'
        )
        return redirect(reverse('bitacoras:detail', kwargs={'pk': bitacora.pk}))


@login_required
@require_POST
def enviar_a_patio_esperanza(request, pk):
    modulacion = get_object_or_404(Modulacion, pk=pk)
    modulacion.estado = 'EN_PATIO_ESPERANZA'
    if modulacion.fecha_patio_esperanza is None:
        modulacion.fecha_patio_esperanza = timezone.now()
    modulacion.save()
    messages.success(request, f'Modulación {modulacion.folio} enviada al Patio Esperanza.')
    return redirect(reverse('modulacion:detail', kwargs={'pk': modulacion.pk}))


@login_required
@require_POST
def retirar_de_patio(request, pk):
    modulacion = get_object_or_404(Modulacion, pk=pk)
    modo = request.POST.get('modo')

    if modo == 'kasu':
        return redirect(reverse('modulacion:enviar_a_bitacora', kwargs={'pk': modulacion.pk}))

    form = RetiroExternoForm(request.POST)
    if form.is_valid():
        modulacion.transportista_externo = form.cleaned_data['transportista_externo']
        modulacion.estado = 'RETIRADO_TERCERO'
        modulacion.fecha_retiro = timezone.now()
        modulacion.save()
        messages.success(request, f'Modulación {modulacion.folio} marcada como retirada por transporte externo.')
    else:
        messages.error(request, 'Indique el nombre del transportista externo.')

    return redirect(reverse('modulacion:detail', kwargs={'pk': modulacion.pk}))


# ============================================================================
# CATÁLOGOS: AGENCIA
# ============================================================================

class AgenciaListView(LoginRequiredMixin, ListView):
    model = Agencia
    template_name = 'modulacion/agencia_list.html'
    context_object_name = 'agencias'


class AgenciaCreateView(LoginRequiredMixin, CreateView):
    model = Agencia
    form_class = AgenciaForm
    template_name = 'modulacion/agencia_form.html'
    success_url = reverse_lazy('modulacion:agencia_list')

    def form_valid(self, form):
        messages.success(self.request, 'Agencia creada exitosamente.')
        return super().form_valid(form)


class AgenciaUpdateView(LoginRequiredMixin, UpdateView):
    model = Agencia
    form_class = AgenciaForm
    template_name = 'modulacion/agencia_form.html'
    success_url = reverse_lazy('modulacion:agencia_list')

    def form_valid(self, form):
        messages.success(self.request, 'Agencia actualizada exitosamente.')
        return super().form_valid(form)


class AgenciaDeleteView(LoginRequiredMixin, DeleteView):
    model = Agencia
    template_name = 'modulacion/agencia_confirm_delete.html'
    success_url = reverse_lazy('modulacion:agencia_list')

    def post(self, request, *args, **kwargs):
        messages.success(request, 'Agencia eliminada.')
        return super().post(request, *args, **kwargs)


# ============================================================================
# CATÁLOGOS: TERMINAL PORTUARIA
# ============================================================================

class TerminalPortuariaListView(LoginRequiredMixin, ListView):
    model = TerminalPortuaria
    template_name = 'modulacion/terminal_list.html'
    context_object_name = 'terminales'


class TerminalPortuariaCreateView(LoginRequiredMixin, CreateView):
    model = TerminalPortuaria
    form_class = TerminalPortuariaForm
    template_name = 'modulacion/terminal_form.html'
    success_url = reverse_lazy('modulacion:terminal_list')

    def form_valid(self, form):
        messages.success(self.request, 'Terminal portuaria creada exitosamente.')
        return super().form_valid(form)


class TerminalPortuariaUpdateView(LoginRequiredMixin, UpdateView):
    model = TerminalPortuaria
    form_class = TerminalPortuariaForm
    template_name = 'modulacion/terminal_form.html'
    success_url = reverse_lazy('modulacion:terminal_list')

    def form_valid(self, form):
        messages.success(self.request, 'Terminal portuaria actualizada exitosamente.')
        return super().form_valid(form)


class TerminalPortuariaDeleteView(LoginRequiredMixin, DeleteView):
    model = TerminalPortuaria
    template_name = 'modulacion/terminal_confirm_delete.html'
    success_url = reverse_lazy('modulacion:terminal_list')

    def post(self, request, *args, **kwargs):
        messages.success(request, 'Terminal portuaria eliminada.')
        return super().post(request, *args, **kwargs)


def completar_datos_terminal(request, token):
    """Vista pública (sin login): el capturista de HAL9MIL completa carril
    y horarios de terminal de un contenedor ya recibido. El token firmado
    (tokens.py) apunta a un único registro; el acceso se cierra en cuanto
    Modulacion.estado deja de ser 'PENDIENTE'."""
    try:
        modulacion = resolver_modulacion(token)
    except Modulacion.DoesNotExist:
        return render(request, 'modulacion/completar_datos_mensaje.html',
                      {'tipo': 'invalido'}, status=404)

    if not modulacion.terminal_portuaria.requiere_datos_extra:
        return render(request, 'modulacion/completar_datos_mensaje.html',
                      {'tipo': 'invalido'}, status=404)

    if modulacion.estado != 'PENDIENTE':
        return render(request, 'modulacion/completar_datos_mensaje.html',
                       {'tipo': 'cerrado', 'modulacion': modulacion})

    if request.method == 'POST':
        form = DatosTerminalForm(request.POST, instance=modulacion, terminal=modulacion.terminal_portuaria)
        if form.is_valid():
            modulacion = form.save(commit=False)
            modulacion.save(update_fields=list(form.fields.keys()))
            return render(request, 'modulacion/completar_datos_mensaje.html',
                           {'tipo': 'gracias', 'modulacion': modulacion})
    else:
        form = DatosTerminalForm(instance=modulacion, terminal=modulacion.terminal_portuaria)

    return render(request, 'modulacion/completar_datos_terminal.html', {
        'form': form, 'modulacion': modulacion,
    })
