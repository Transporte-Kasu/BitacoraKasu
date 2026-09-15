import datetime
import json
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView,
)

from config.services.whatsapp_service import enviar_mensaje
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
from .mensajes_whatsapp import construir_mensajes_whatsapp
from .models import (
    Agencia, ESTADOS_EN_SEGUIMIENTO, Modulacion, TerminalPortuaria, TransicionInvalida,
)
from .models import ImportacionProgramacionLCTPC
from .reportes import construir_programa_despacho
from .services_importacion import importar_programaciones_lctpc
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
        'importaciones_lctpc': ImportacionProgramacionLCTPC.objects.all()[:10],
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
        modulacion.save()
        messages.success(self.request, f'Modulación {modulacion.folio} creada exitosamente.')
        return redirect(reverse('modulacion:detail', kwargs={'pk': modulacion.pk}))


class ModulacionUpdateView(LoginRequiredMixin, UpdateView):
    model = Modulacion
    form_class = ModulacionForm
    template_name = 'modulacion/modulacion_form.html'

    def form_valid(self, form):
        modulacion = form.save(commit=False)
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
        # Al quedar unidad + operador sobre una Modulación aún pendiente, el
        # flujo avanza solo a ASIGNADO (dejando historial). Si ya avanzó
        # (reasignación), el estado no se toca.
        if (modulacion.estado == 'PENDIENTE'
                and modulacion.unidad_id and modulacion.operador_id):
            modulacion.transicionar('ASIGNADO', usuario=self.request.user)
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
                modulacion.fecha_retiro = timezone.now()
                modulacion.save()
                modulacion.transicionar('ENVIADO_BITACORA', usuario=request.user)
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
        modulacion.fecha_retiro = timezone.now()
        modulacion.save()
        modulacion.transicionar('ENVIADO_BITACORA', usuario=request.user)

        messages.success(
            request,
            f'Modulación {modulacion.folio} enviada a Bitácora de Viajes (viaje #{bitacora.pk}).'
        )
        return redirect(reverse('bitacoras:detail', kwargs={'pk': bitacora.pk}))


@login_required
@require_POST
def enviar_a_patio_esperanza(request, pk):
    modulacion = get_object_or_404(Modulacion, pk=pk)
    try:
        modulacion.transicionar('EN_PATIO_ESPERANZA', usuario=request.user)
    except TransicionInvalida as exc:
        messages.error(request, str(exc))
    else:
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
        # No se persiste el transportista si la transición no procede:
        # transicionar() hace su propio save() al validar el estado.
        modulacion.transportista_externo = form.cleaned_data['transportista_externo']
        try:
            modulacion.transicionar('RETIRADO_TERCERO', usuario=request.user)
        except TransicionInvalida as exc:
            messages.error(request, str(exc))
        else:
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


# ============================================================================
# IMPORTACIÓN DE PROGRAMACIÓN DE CITAS DE LCTPC (Graph API)
# ============================================================================

@login_required
@require_POST
def importar_programacion_lctpc(request):
    """Dispara el import de programación de citas de LCTPC bajo demanda."""
    r = importar_programaciones_lctpc()
    if r.error_listado:
        messages.error(request, f'No se pudo consultar el buzón: {r.error_listado}')
        return redirect('modulacion:dashboard')
    texto = (
        f'{r.correos_procesados} correo(s) procesado(s), {r.correos_saltados} sin cambios, '
        f'{r.correos_con_error} con error · {r.creadas} modulación(es) creada(s), '
        f'{r.actualizadas} actualizada(s).'
    )
    if r.correos_con_error or r.ambiguas:
        messages.warning(request, f'Importación LCTPC con avisos: {texto}')
    else:
        messages.success(request, f'Importación LCTPC: {texto}')
    return redirect('modulacion:dashboard')


class ImportacionProgramacionLCTPCListView(LoginRequiredMixin, ListView):
    model = ImportacionProgramacionLCTPC
    template_name = 'modulacion/importacion_lctpc_list.html'
    context_object_name = 'importaciones'
    paginate_by = 30


class ImportacionProgramacionLCTPCDetailView(LoginRequiredMixin, DetailView):
    model = ImportacionProgramacionLCTPC
    template_name = 'modulacion/importacion_lctpc_detail.html'
    context_object_name = 'importacion'


# ============================================================================
# ATENCIÓN A CLIENTES (seguimiento aduanal)
# ============================================================================

class AtencionClientesView(LoginRequiredMixin, TemplateView):
    """Tablero de seguimiento aduanal: modulaciones desde ASIGNADO hasta
    EN_PATIO_ESPERANZA, agrupadas por estado, con botones de avance."""
    template_name = 'modulacion/atencion_clientes.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = (
            Modulacion.objects
            .filter(estado__in=ESTADOS_EN_SEGUIMIENTO)
            .select_related('cliente', 'unidad', 'operador', 'agencia', 'terminal_portuaria')
            .order_by('fecha_recepcion')
        )
        estado = self.request.GET.get('estado') or ''
        cliente = self.request.GET.get('cliente') or ''
        if estado in ESTADOS_EN_SEGUIMIENTO:
            qs = qs.filter(estado=estado)
        if cliente.isdigit():
            qs = qs.filter(cliente_id=cliente)

        por_estado = []
        for clave in ESTADOS_EN_SEGUIMIENTO:
            grupo = [m for m in qs if m.estado == clave]
            if grupo:
                por_estado.append({
                    'clave': clave,
                    'label': dict(Modulacion.ESTADO_CHOICES)[clave],
                    'modulaciones': grupo,
                })
        ctx['grupos'] = por_estado
        ctx['estados_choices'] = [
            (c, dict(Modulacion.ESTADO_CHOICES)[c]) for c in ESTADOS_EN_SEGUIMIENTO
        ]
        ctx['filtro_estado'] = estado
        ctx['filtro_cliente'] = cliente
        ctx['querystring'] = self.request.GET.urlencode()
        return ctx


@login_required
@require_POST
def avanzar_estado_modulacion(request, pk):
    modulacion = get_object_or_404(Modulacion, pk=pk)
    nuevo_estado = request.POST.get('nuevo_estado', '')
    nota = request.POST.get('nota', '').strip()

    destino = request.POST.get('next') or ''
    if not url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        destino = reverse('modulacion:atencion_clientes')

    # Solo se aceptan las transiciones "de botón": las de flujo dedicado
    # (ENVIADO_BITACORA / RETIRADO_TERCERO) se hacen por sus vistas propias.
    validas = {clave for clave, _ in modulacion.transiciones_validas}
    if nuevo_estado not in validas:
        messages.error(
            request, f'{modulacion.folio}: transición no permitida por esta vía.'
        )
        return redirect(destino)

    try:
        modulacion.transicionar(nuevo_estado, usuario=request.user, nota=nota)
    except TransicionInvalida as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f'{modulacion.folio}: {modulacion.get_estado_display()}.',
        )
    return redirect(destino)


class ReporteProgramaDespachoView(LoginRequiredMixin, TemplateView):
    """Form con selector de fecha para descargar el Programa de despacho (.xlsx)."""
    template_name = 'modulacion/reporte_despacho.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['fecha'] = timezone.localdate().isoformat()
        return ctx


def _parse_fecha(texto):
    try:
        return datetime.date.fromisoformat(texto or '')
    except (TypeError, ValueError):
        return None


@login_required
def descargar_programa_despacho(request):
    fecha = _parse_fecha(request.GET.get('fecha')) or timezone.localdate()
    wb = construir_programa_despacho(fecha)
    resp = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    resp['Content-Disposition'] = (
        f'attachment; filename="programa_despacho_{fecha.isoformat()}.xlsx"'
    )
    wb.save(resp)
    return resp


@login_required
def previsualizar_whatsapp_despacho(request):
    fecha = _parse_fecha(request.GET.get('fecha')) or timezone.localdate()
    mensajes = construir_mensajes_whatsapp(fecha)
    return render(request, 'modulacion/whatsapp_preview.html', {
        'fecha': fecha.isoformat(),
        'mensajes': [{'cliente': c, 'texto': t} for c, t in mensajes],
        'numero_configurado': bool(settings.WA_PROGRAMA_DESPACHO_NUMERO),
    })


@login_required
@require_POST
def enviar_whatsapp_despacho(request):
    fecha = _parse_fecha(request.POST.get('fecha')) or timezone.localdate()
    destino = f"{reverse('modulacion:reporte_despacho')}?fecha={fecha.isoformat()}"

    numero = settings.WA_PROGRAMA_DESPACHO_NUMERO
    if not numero:
        messages.error(request, 'WA_PROGRAMA_DESPACHO_NUMERO no está configurado. No se envió nada.')
        return redirect(destino)

    mensajes = construir_mensajes_whatsapp(fecha)
    if not mensajes:
        messages.warning(request, 'No hay maniobras con cliente asignado para esta fecha.')
        return redirect(destino)

    enviados = 0
    fallidos = []
    for cliente, texto in mensajes:
        if enviar_mensaje(texto, numeros=[numero]):
            enviados += 1
        else:
            fallidos.append(str(cliente))

    if enviados:
        messages.success(request, f'{enviados} mensaje(s) de WhatsApp enviado(s).')
    if fallidos:
        messages.error(
            request,
            f'No se pudo enviar a: {", ".join(fallidos)}. Reintenta desde la vista previa.',
        )

    return redirect(destino)
