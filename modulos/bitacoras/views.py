from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Sum
from django.http import JsonResponse
from .models import BitacoraViaje, Cliente
from .forms import BitacoraViajeForm, BitacoraViajeCompletarForm, ClienteForm
from decimal import Decimal
from datetime import datetime
import os


class BitacoraListView(LoginRequiredMixin, ListView):
    model = BitacoraViaje
    template_name = 'bitacoras/bitacora_list.html'
    context_object_name = 'bitacoras'
    paginate_by = 20

    def get_queryset(self):
        queryset = BitacoraViaje.objects.select_related(
            'operador', 'unidad', 'cliente'
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

        cliente_id = self.request.GET.get('cliente')
        if cliente_id:
            queryset = queryset.filter(cliente_id=cliente_id)

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
        context['clientes_list'] = Cliente.objects.filter(activo=True).order_by('nombre')
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
        bitacora = form.save(commit=False)

        unidad = bitacora.unidad
        if unidad:
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

        bitacora.save()

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


# ============================================================================
# CLIENTES
# ============================================================================

class ClienteListView(LoginRequiredMixin, ListView):
    model = Cliente
    template_name = 'bitacoras/cliente_list.html'
    context_object_name = 'clientes'

    def get_queryset(self):
        qs = Cliente.objects.all()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(email__icontains=q) | Q(celular__icontains=q))
        return qs


class ClienteCreateView(LoginRequiredMixin, CreateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'bitacoras/cliente_form.html'
    success_url = reverse_lazy('bitacoras:cliente_list')

    def form_valid(self, form):
        messages.success(self.request, 'Cliente creado exitosamente.')
        return super().form_valid(form)


class ClienteUpdateView(LoginRequiredMixin, UpdateView):
    model = Cliente
    form_class = ClienteForm
    template_name = 'bitacoras/cliente_form.html'
    success_url = reverse_lazy('bitacoras:cliente_list')

    def form_valid(self, form):
        messages.success(self.request, 'Cliente actualizado exitosamente.')
        return super().form_valid(form)


class ClienteDeleteView(LoginRequiredMixin, DeleteView):
    model = Cliente
    template_name = 'bitacoras/cliente_confirm_delete.html'
    success_url = reverse_lazy('bitacoras:cliente_list')

    def post(self, request, *args, **kwargs):
        messages.success(request, 'Cliente eliminado.')
        return super().post(request, *args, **kwargs)


def enviar_notificacion_cliente(request, pk):
    """Envía WhatsApp + email al cliente asignado a la bitácora."""
    bitacora = get_object_or_404(BitacoraViaje, pk=pk)

    if not bitacora.cliente:
        messages.error(request, 'Esta bitácora no tiene cliente asignado.')
        return redirect('bitacoras:detail', pk=pk)

    from config.services.twilio_service import enviar_notificacion_bitacora
    resultado = enviar_notificacion_bitacora(bitacora, bitacora.cliente)

    partes = []
    if resultado['wa_ok']:
        partes.append('WhatsApp enviado')
    if resultado['email_ok']:
        partes.append('correo enviado')

    if partes:
        messages.success(request, f"Notificación a {bitacora.cliente.nombre}: {', '.join(partes)}.")
    else:
        messages.error(request, f"No se pudo enviar la notificación a {bitacora.cliente.nombre}. Verifica celular, email y configuración de Twilio.")

    return redirect('bitacoras:detail', pk=pk)


# ============================================================================
# CARGA MASIVA DESDE EXCEL
# ============================================================================

@login_required
def carga_masiva_upload(request):
    clientes = list(Cliente.objects.filter(activo=True).order_by('nombre'))
    context  = {
        'tipo_contenedor_choices': BitacoraViaje.TIPO_CONTENEDOR_CHOICES,
        'clientes': clientes,
    }

    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        if not archivo:
            messages.error(request, 'Selecciona un archivo Excel (.xlsx).')
            return render(request, 'bitacoras/carga_masiva.html', context)

        hora_salida     = request.POST.get('hora_salida', '06:00')
        hora_carga      = request.POST.get('hora_carga', '05:00')
        tipo_contenedor = request.POST.get('tipo_contenedor', '40')
        cliente_id      = request.POST.get('cliente', '').strip()

        try:
            from .excel_parser import parse_confirmacion_excel
            viajes = parse_confirmacion_excel(archivo, hora_salida, hora_carga, tipo_contenedor)
        except Exception as e:
            messages.error(request, f'Error al leer el archivo: {e}')
            return render(request, 'bitacoras/carga_masiva.html', context)

        if not viajes:
            messages.warning(request, 'No se encontraron viajes válidos en el archivo.')
            return render(request, 'bitacoras/carga_masiva.html', context)

        request.session['carga_masiva_viajes']    = viajes
        request.session['carga_masiva_cliente_id'] = cliente_id
        return redirect('bitacoras:carga_masiva_preview')

    return render(request, 'bitacoras/carga_masiva.html', context)


@login_required
def carga_masiva_preview(request):
    import json as _json
    from modulos.operadores.models import Operador
    from modulos.unidades.models import Unidad

    # Solo unidades foráneas activas sin viaje en curso
    unidades_en_viaje = set(
        BitacoraViaje.objects.filter(completado=False).values_list('unidad_id', flat=True)
    )
    unidades = list(
        Unidad.objects.filter(activa=True, tipo__in=['FORANEA', 'ESPERANZA'])
                      .order_by('numero_economico')
    )
    unidades_disponibles = [u for u in unidades if u.id not in unidades_en_viaje]

    # Mapa unidad_id → operador asignado
    unidad_op_map = {}
    for u in unidades_disponibles:
        op = Operador.objects.filter(unidad_asignada=u, activo=True).first()
        if op:
            unidad_op_map[str(u.id)] = {'id': str(op.id), 'nombre': op.nombre}

    operadores = list(
        Operador.objects.filter(activo=True, tipo__in=['FORANEO', 'ESPERANZA']).order_by('nombre')
    )
    clientes = list(Cliente.objects.filter(activo=True).order_by('nombre'))

    if request.method == 'GET':
        viajes = request.session.get('carga_masiva_viajes')
        if not viajes:
            messages.warning(request, 'No hay datos pendientes. Sube un archivo primero.')
            return redirect('bitacoras:carga_masiva')

        cliente_id  = request.session.get('carga_masiva_cliente_id', '')
        cliente_obj = None
        if cliente_id:
            try:
                cliente_obj = Cliente.objects.get(pk=cliente_id)
            except Cliente.DoesNotExist:
                pass

        return render(request, 'bitacoras/carga_masiva_preview.html', {
            'viajes':             viajes,
            'total_viajes':       len(viajes),
            'operadores':         operadores,
            'unidades':           unidades_disponibles,
            'cliente':            cliente_obj,
            'unidad_op_map_json': _json.dumps(unidad_op_map),
        })

    # POST → crear registros
    total      = int(request.POST.get('total_viajes', 0))
    cliente_id = request.session.get('carga_masiva_cliente_id', '')
    creados    = 0
    errores    = []

    for i in range(total):
        p          = f'v{i}_'
        contenedor = request.POST.get(f'{p}contenedor', '').strip()
        try:
            modalidad     = request.POST.get(f'{p}modalidad', '')
            contenedor_2  = request.POST.get(f'{p}contenedor_2', '').strip()
            peso_raw      = request.POST.get(f'{p}peso', '').strip()
            peso_2_raw    = request.POST.get(f'{p}peso_2', '').strip()
            destino               = request.POST.get(f'{p}destino', '').strip()
            domicilio_carta_porte = request.POST.get(f'{p}domicilio_carta_porte', '').strip()
            cp_destino            = request.POST.get(f'{p}cp_destino', '').strip()
            observaciones         = request.POST.get(f'{p}observaciones', '').strip()
            fecha_sal_str = request.POST.get(f'{p}fecha_salida', '')
            fecha_car_str = request.POST.get(f'{p}fecha_carga', '')
            tipo_cont     = request.POST.get(f'{p}tipo_contenedor', '40')
            operador_id   = request.POST.get(f'{p}operador', '').strip()
            unidad_id     = request.POST.get(f'{p}unidad', '').strip()

            if not operador_id or not unidad_id:
                errores.append(f'Viaje {i + 1} ({contenedor}): falta operador o unidad.')
                continue
            if not fecha_sal_str or not fecha_car_str:
                errores.append(f'Viaje {i + 1} ({contenedor}): falta fecha de salida o carga.')
                continue

            bitacora = BitacoraViaje(
                cliente_id            = int(cliente_id) if cliente_id else None,
                modalidad             = modalidad,
                contenedor            = contenedor,
                contenedor_2          = contenedor_2,
                peso                  = Decimal(peso_raw)   if peso_raw   else None,
                peso_2                = Decimal(peso_2_raw) if peso_2_raw else None,
                destino               = destino,
                domicilio_carta_porte = domicilio_carta_porte,
                cp_destino            = cp_destino,
                cp_origen             = '40812',
                observaciones         = observaciones,
                fecha_salida  = datetime.fromisoformat(fecha_sal_str),
                fecha_carga   = datetime.fromisoformat(fecha_car_str),
                tipo_contenedor = tipo_cont,
                operador_id   = int(operador_id),
                unidad_id     = int(unidad_id),
            )
            bitacora.save()
            creados += 1

        except Exception as e:
            errores.append(f'Viaje {i + 1} ({contenedor}): {e}')

    request.session.pop('carga_masiva_viajes', None)
    request.session.pop('carga_masiva_cliente_id', None)

    if creados:
        s = 's' if creados != 1 else ''
        messages.success(request, f'{creados} bitácora{s} importada{s} exitosamente.')
    for err in errores:
        messages.error(request, err)

    return redirect('bitacoras:list')


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
