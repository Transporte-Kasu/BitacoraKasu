from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from django.http import JsonResponse
import json
from datetime import timedelta

from .models import (
    ProductoAlmacen, EntradaAlmacen, ItemEntradaAlmacen,
    SolicitudSalida, ItemSolicitudSalida, SalidaAlmacen,
    ItemSalidaAlmacen, MovimientoAlmacen, AlertaStock,
    SalidaRapidaConsumible, AsignacionSalida, ItemAsignacionSalida
)
from .forms import (
    ProductoAlmacenForm, EntradaAlmacenForm, ItemEntradaAlmacenForm,
    SolicitudSalidaForm, ItemSolicitudSalidaForm, AutorizarSolicitudForm,
    SalidaAlmacenForm, ItemSalidaAlmacenForm, FiltroProductosForm,
    FiltroEntradasForm, FiltroSolicitudesForm, ResolverAlertaForm,
    SalidaRapidaConsumibleForm, AsignacionConsumibleUnidadForm,
    EntradaDirectaForm, AltaExpressProductoForm, UNIDADES_MEDIDA_CHOICES
)


# ========== Dashboard ==========

@login_required
def dashboard_almacen(request):
    """Dashboard principal del almacén"""
    # Estadísticas generales
    total_productos = ProductoAlmacen.objects.filter(activo=True).count()
    productos_stock_bajo = ProductoAlmacen.objects.filter(
        activo=True,
        cantidad__lte=F('stock_minimo')
    ).count()
    productos_agotados = ProductoAlmacen.objects.filter(
        activo=True,
        cantidad=0
    ).count()
    
    # Alertas activas
    alertas_activas = AlertaStock.objects.filter(resuelta=False).order_by('-fecha_generacion')[:10]
    total_alertas = AlertaStock.objects.filter(resuelta=False).count()
    
    # Solicitudes pendientes
    solicitudes_pendientes = SolicitudSalida.objects.filter(
        estado='PENDIENTE'
    ).order_by('-fecha_solicitud')[:5]
    
    # Valor total del inventario
    valor_inventario = ProductoAlmacen.objects.filter(activo=True).aggregate(
        total=Sum(F('cantidad') * F('costo_unitario'))
    )['total'] or 0
    
    # Productos próximos a caducar
    fecha_limite = timezone.now().date() + timedelta(days=30)
    productos_caducar = ProductoAlmacen.objects.filter(
        activo=True,
        tiene_caducidad=True,
        fecha_caducidad__lte=fecha_limite,
        fecha_caducidad__gte=timezone.now().date()
    ).order_by('fecha_caducidad')[:5]
    
    # Movimientos recientes
    movimientos_recientes = MovimientoAlmacen.objects.select_related(
        'producto_almacen', 'usuario'
    ).order_by('-fecha_movimiento')[:10]
    
    context = {
        'total_productos': total_productos,
        'productos_stock_bajo': productos_stock_bajo,
        'productos_agotados': productos_agotados,
        'alertas_activas': alertas_activas,
        'total_alertas': total_alertas,
        'solicitudes_pendientes': solicitudes_pendientes,
        'valor_inventario': valor_inventario,
        'productos_caducar': productos_caducar,
        'movimientos_recientes': movimientos_recientes,
    }
    return render(request, 'almacen/dashboard.html', context)


# ========== ProductoAlmacen Views ==========

class ProductoAlmacenListView(LoginRequiredMixin, ListView):
    """Lista de productos en almacén"""
    model = ProductoAlmacen
    template_name = 'almacen/producto_list.html'
    context_object_name = 'productos'
    paginate_by = 20

    def get_queryset(self):
        queryset = ProductoAlmacen.objects.select_related(
            'producto_compra', 'proveedor_principal'
        ).all()

        # Filtros
        buscar = self.request.GET.get('buscar')
        categoria = self.request.GET.get('categoria')
        subcategoria = self.request.GET.get('subcategoria')
        stock_bajo = self.request.GET.get('stock_bajo')
        proximo_caducar = self.request.GET.get('proximo_caducar')
        activo = self.request.GET.get('activo')

        if buscar:
            queryset = queryset.filter(
                Q(sku__icontains=buscar) |
                Q(descripcion__icontains=buscar) |
                Q(codigo_barras__icontains=buscar)
            )
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        if subcategoria:
            queryset = queryset.filter(subcategoria=subcategoria)
        if stock_bajo:
            queryset = queryset.filter(cantidad__lte=F('stock_minimo'))
        if proximo_caducar:
            fecha_limite = timezone.now().date() + timedelta(days=30)
            queryset = queryset.filter(
                tiene_caducidad=True,
                fecha_caducidad__lte=fecha_limite,
                fecha_caducidad__gte=timezone.now().date()
            )
        if activo:
            queryset = queryset.filter(activo=(activo == 'True'))

        return queryset.order_by('categoria', 'subcategoria', 'descripcion')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filtro_form'] = FiltroProductosForm(self.request.GET)
        # Categorías y subcategorías únicas para los selects
        context['categorias'] = (
            ProductoAlmacen.objects.values_list('categoria', flat=True)
            .distinct().order_by('categoria')
        )
        context['subcategorias_json'] = self._get_subcategorias_map()
        # Preservar filtros en paginación
        params = self.request.GET.copy()
        params.pop('page', None)
        context['filtro_params'] = params.urlencode()
        return context

    def _get_subcategorias_map(self):
        """Retorna un dict JSON con subcategorías agrupadas por categoría"""
        import json
        subcats = (
            ProductoAlmacen.objects.exclude(subcategoria='')
            .values_list('categoria', 'subcategoria').distinct()
            .order_by('categoria', 'subcategoria')
        )
        mapa = {}
        for cat, subcat in subcats:
            mapa.setdefault(cat, []).append(subcat)
        return json.dumps(mapa)


class ProductoAlmacenDetailView(LoginRequiredMixin, DetailView):
    """Detalle de producto"""
    model = ProductoAlmacen
    template_name = 'almacen/producto_detail.html'
    context_object_name = 'producto'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        producto = self.object
        
        # Movimientos recientes del producto
        context['movimientos'] = MovimientoAlmacen.objects.filter(
            producto_almacen=producto
        ).select_related('usuario', 'entrada_almacen', 'salida_almacen').order_by(
            '-fecha_movimiento'
        )[:20]
        
        # Alertas del producto
        context['alertas'] = AlertaStock.objects.filter(
            producto_almacen=producto,
            resuelta=False
        ).order_by('-fecha_generacion')
        
        return context


class ProductoAlmacenCreateView(LoginRequiredMixin, CreateView):
    """Crear producto"""
    model = ProductoAlmacen
    form_class = ProductoAlmacenForm
    template_name = 'almacen/producto_form.html'
    success_url = reverse_lazy('almacen:producto_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Producto creado exitosamente.')
        return super().form_valid(form)


class ProductoAlmacenUpdateView(LoginRequiredMixin, UpdateView):
    """Actualizar producto"""
    model = ProductoAlmacen
    form_class = ProductoAlmacenForm
    template_name = 'almacen/producto_form.html'

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse('almacen:producto_list')

    def form_valid(self, form):
        messages.success(self.request, 'Producto actualizado exitosamente.')
        return super().form_valid(form)


class ProductoAlmacenDeleteView(LoginRequiredMixin, DeleteView):
    """Eliminar producto"""
    model = ProductoAlmacen
    template_name = 'almacen/producto_confirm_delete.html'

    def get_success_url(self):
        url = reverse('almacen:producto_list')
        page = self.request.GET.get('page') or self.request.POST.get('page')
        if page:
            url += f'?page={page}'
        return url

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Producto eliminado exitosamente.')
        return super().delete(request, *args, **kwargs)


@login_required
def api_subcategorias(request):
    """API endpoint para obtener subcategorías filtradas por categoría"""
    categoria = request.GET.get('categoria', '')
    subcategorias = (
        ProductoAlmacen.objects.filter(categoria=categoria)
        .exclude(subcategoria='')
        .values_list('subcategoria', flat=True)
        .distinct().order_by('subcategoria')
    )
    return JsonResponse({'subcategorias': list(subcategorias)})


# ========== EntradaAlmacen Views ==========

class EntradaAlmacenListView(LoginRequiredMixin, ListView):
    """Lista de entradas"""
    model = EntradaAlmacen
    template_name = 'almacen/entrada_list.html'
    context_object_name = 'entradas'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = EntradaAlmacen.objects.select_related(
            'recibido_por', 'orden_compra', 'orden_trabajo'
        ).all()
        
        # Filtros
        tipo = self.request.GET.get('tipo')
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        if fecha_desde:
            queryset = queryset.filter(fecha_entrada__date__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha_entrada__date__lte=fecha_hasta)
        
        return queryset.order_by('-fecha_entrada')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filtro_form'] = FiltroEntradasForm(self.request.GET)
        return context


class EntradaAlmacenDetailView(LoginRequiredMixin, DetailView):
    """Detalle de entrada"""
    model = EntradaAlmacen
    template_name = 'almacen/entrada_detail.html'
    context_object_name = 'entrada'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.select_related('producto_almacen').all()
        return context


class EntradaAlmacenCreateView(LoginRequiredMixin, CreateView):
    """Crear entrada"""
    model = EntradaAlmacen
    form_class = EntradaAlmacenForm
    template_name = 'almacen/entrada_form.html'
    success_url = reverse_lazy('almacen:entrada_list')

    def form_valid(self, form):
        form.instance.recibido_por = self.request.user
        messages.success(self.request, f'Entrada {form.instance.folio} creada exitosamente.')
        return super().form_valid(form)


@login_required
def entrada_directa(request):
    """Entrada directa al almacén sin orden de compra ni de trabajo."""
    from django.db import transaction

    categorias = list(
        ProductoAlmacen.objects.values_list('categoria', flat=True)
        .distinct().order_by('categoria')
    )

    if request.method == 'POST':
        form = EntradaDirectaForm(request.POST)
        items_raw = request.POST.get('items_json', '[]')

        try:
            items = json.loads(items_raw)
        except (ValueError, TypeError):
            items = []

        errores_items = []

        if form.is_valid():
            if not items:
                form.add_error(None, 'Debes agregar al menos un producto.')
            else:
                # Validar alta express inline antes de guardar nada
                for idx, item in enumerate(items):
                    if item.get('tipo') == 'nuevo':
                        sku = (item.get('sku') or '').upper()
                        if not sku:
                            errores_items.append(f'Fila {idx + 1}: el SKU es obligatorio.')
                        elif ProductoAlmacen.objects.filter(sku=sku).exists():
                            errores_items.append(
                                f'Fila {idx + 1}: el SKU "{sku}" ya existe, búscalo en el catálogo.'
                            )
                        if not item.get('descripcion'):
                            errores_items.append(f'Fila {idx + 1}: la descripción es obligatoria.')
                        if not item.get('unidad_medida'):
                            errores_items.append(f'Fila {idx + 1}: la unidad de medida es obligatoria.')
                        if not item.get('categoria'):
                            errores_items.append(f'Fila {idx + 1}: la categoría es obligatoria.')

                    try:
                        cantidad = float(item.get('cantidad', 0))
                    except (ValueError, TypeError):
                        cantidad = 0
                    if cantidad <= 0:
                        errores_items.append(f'Fila {idx + 1}: la cantidad debe ser mayor a 0.')

        if form.is_valid() and not errores_items and items:
            try:
                with transaction.atomic():
                    entrada = EntradaAlmacen.objects.create(
                        tipo='ENTRADA_DIRECTA',
                        fecha_entrada=form.cleaned_data['fecha_entrada'],
                        observaciones=form.cleaned_data.get('observaciones', ''),
                        recibido_por=request.user,
                    )

                    for item in items:
                        if item.get('tipo') == 'nuevo':
                            sku = (item.get('sku') or '').upper()
                            producto = ProductoAlmacen.objects.create(
                                sku=sku,
                                descripcion=item.get('descripcion', ''),
                                unidad_medida=item.get('unidad_medida', 'Pieza'),
                                categoria=item.get('categoria', 'General'),
                                localidad='Por asignar',
                                cantidad=0,
                                stock_minimo=0,
                                stock_maximo=0,
                                costo_unitario=float(item.get('costo_unitario') or 0),
                                activo=True,
                            )
                        else:
                            producto = get_object_or_404(ProductoAlmacen, pk=item.get('producto_id'))

                        ItemEntradaAlmacen.objects.create(
                            entrada=entrada,
                            producto_almacen=producto,
                            cantidad=float(item.get('cantidad', 1)),
                            costo_unitario=float(item.get('costo_unitario') or 0),
                        )

                messages.success(
                    request,
                    f'Entrada directa {entrada.folio} registrada con {len(items)} producto(s).'
                )
                return redirect('almacen:entrada_detail', pk=entrada.pk)

            except Exception as exc:
                messages.error(request, f'Error al guardar la entrada: {exc}')

    else:
        from django.utils import timezone as tz
        form = EntradaDirectaForm(initial={'fecha_entrada': tz.localtime().strftime('%Y-%m-%dT%H:%M')})
        items = []
        errores_items = []

    return render(request, 'almacen/entrada_directa.html', {
        'form': form,
        'items_json': json.dumps(items) if items else '[]',
        'errores_items': errores_items,
        'categorias': categorias,
        'unidades_medida': UNIDADES_MEDIDA_CHOICES,
    })


@login_required
def api_buscar_producto_almacen(request):
    """Busca productos en el catálogo por SKU o descripción (para entrada directa)."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'resultados': []})

    productos = ProductoAlmacen.objects.filter(
        activo=True
    ).filter(
        Q(sku__icontains=q) | Q(descripcion__icontains=q)
    ).order_by('descripcion')[:10]

    resultados = [
        {
            'id': p.pk,
            'sku': p.sku,
            'descripcion': p.descripcion,
            'unidad_medida': p.unidad_medida,
            'cantidad': float(p.cantidad),
            'costo_unitario': float(p.costo_unitario),
        }
        for p in productos
    ]
    return JsonResponse({'resultados': resultados})


# ========== SolicitudSalida Views ==========

class SolicitudSalidaListView(LoginRequiredMixin, ListView):
    """Lista de solicitudes de salida"""
    model = SolicitudSalida
    template_name = 'almacen/solicitud_list.html'
    context_object_name = 'solicitudes'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = SolicitudSalida.objects.select_related(
            'solicitante', 'orden_trabajo', 'autorizado_por'
        ).all()
        
        # Filtros
        tipo = self.request.GET.get('tipo')
        estado = self.request.GET.get('estado')
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        if estado:
            queryset = queryset.filter(estado=estado)
        if fecha_desde:
            queryset = queryset.filter(fecha_solicitud__date__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha_solicitud__date__lte=fecha_hasta)
        
        return queryset.order_by('-fecha_solicitud')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filtro_form'] = FiltroSolicitudesForm(self.request.GET)
        return context


class SolicitudSalidaDetailView(LoginRequiredMixin, DetailView):
    """Detalle de solicitud"""
    model = SolicitudSalida
    template_name = 'almacen/solicitud_detail.html'
    context_object_name = 'solicitud'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.select_related('producto_almacen').all()
        context['salidas'] = self.object.salidas.all()
        if self.object.estado == 'PENDIENTE':
            context['item_form'] = ItemSolicitudSalidaForm()
            productos_data = {
                str(p.id): {
                    'stock': float(p.cantidad),
                    'unidad': p.unidad_medida,
                    'stock_bajo': p.stock_bajo,
                    'stock_agotado': p.stock_agotado,
                }
                for p in ProductoAlmacen.objects.filter(activo=True)
            }
            context['productos_json'] = json.dumps(productos_data)
        return context


class SolicitudSalidaCreateView(LoginRequiredMixin, CreateView):
    """Crear solicitud de salida"""
    model = SolicitudSalida
    form_class = SolicitudSalidaForm
    template_name = 'almacen/solicitud_form.html'

    def form_valid(self, form):
        form.instance.solicitante = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Solicitud {self.object.folio} creada. Agrega los productos a continuacion.'
        )
        return response

    def get_success_url(self):
        return reverse('almacen:solicitud_detail', kwargs={'pk': self.object.pk})


@login_required
def enviar_notificacion_solicitud(request, pk):
    """Envía notificación por correo a los autorizadores para revisar la solicitud"""
    from django.core.mail import send_mail
    from django.conf import settings as django_settings

    solicitud = get_object_or_404(SolicitudSalida, pk=pk)

    if solicitud.estado != 'PENDIENTE':
        messages.error(request, 'Solo se pueden notificar solicitudes pendientes.')
        return redirect('almacen:solicitud_detail', pk=pk)

    if not solicitud.items.exists():
        messages.error(request, 'Agrega al menos un producto antes de enviar la notificación.')
        return redirect('almacen:solicitud_detail', pk=pk)

    if request.method == 'POST':
        items = solicitud.items.select_related('producto_almacen').all()
        solicitante = solicitud.solicitante.get_full_name() or solicitud.solicitante.username

        # URLs absolutas
        detalle_url = request.build_absolute_uri(
            reverse('almacen:solicitud_detail', kwargs={'pk': pk})
        )
        autorizar_url = request.build_absolute_uri(
            reverse('almacen:solicitud_autorizar', kwargs={'pk': pk})
        )

        # Líneas de productos
        productos_lista = '\n'.join(
            f'  - {item.producto_almacen.descripcion}: '
            f'{item.cantidad_solicitada} {item.producto_almacen.unidad_medida}'
            for item in items
        )

        asunto = f'[Almacén] Solicitud {solicitud.folio} requiere autorización'
        cuerpo = (
            f'Se ha generado una solicitud de salida de almacén que requiere su autorización.\n\n'
            f'Folio:        {solicitud.folio}\n'
            f'Tipo:         {solicitud.get_tipo_display()}\n'
            f'Solicitante:  {solicitante}\n'
            f'Fecha:        {solicitud.fecha_solicitud.strftime("%d/%m/%Y %H:%M")}\n'
            f'Justificación: {solicitud.justificacion}\n\n'
            f'Productos solicitados:\n{productos_lista}\n\n'
            f'— Ver detalle:\n{detalle_url}\n\n'
            f'— Autorizar / Rechazar:\n{autorizar_url}\n\n'
            f'---\nSistema BitacoraKasu - Transportes Kasu'
        )

        destinatarios = getattr(django_settings, 'ALMACEN_AUTORIZACION_EMAILS', [])

        if not destinatarios:
            messages.warning(request, 'No hay destinatarios configurados (ALMACEN_AUTORIZACION_EMAILS).')
            return redirect('almacen:solicitud_detail', pk=pk)

        try:
            send_mail(
                subject=asunto,
                message=cuerpo,
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=destinatarios,
                fail_silently=False,
            )
            messages.success(
                request,
                f'Notificación enviada a {len(destinatarios)} destinatario(s).'
            )
        except Exception as e:
            messages.error(request, f'Error al enviar el correo: {e}')

    return redirect('almacen:solicitud_detail', pk=pk)


@login_required
def agregar_item_solicitud(request, pk):
    """Agregar un producto a una solicitud de salida pendiente"""
    solicitud = get_object_or_404(SolicitudSalida, pk=pk)

    if solicitud.estado != 'PENDIENTE':
        messages.error(request, 'Solo se pueden agregar productos a solicitudes pendientes.')
        return redirect('almacen:solicitud_detail', pk=pk)

    if request.method == 'POST':
        form = ItemSolicitudSalidaForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.solicitud = solicitud
            item.save()
            messages.success(
                request,
                f'Producto "{item.producto_almacen.descripcion}" agregado.'
            )
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)

    return redirect('almacen:solicitud_detail', pk=pk)


@login_required
def eliminar_item_solicitud(request, pk, item_pk):
    """Eliminar un producto de una solicitud de salida pendiente"""
    solicitud = get_object_or_404(SolicitudSalida, pk=pk)
    item = get_object_or_404(ItemSolicitudSalida, pk=item_pk, solicitud=solicitud)

    if solicitud.estado != 'PENDIENTE':
        messages.error(request, 'No se pueden modificar solicitudes que ya fueron procesadas.')
        return redirect('almacen:solicitud_detail', pk=pk)

    if request.method == 'POST':
        descripcion = item.producto_almacen.descripcion
        item.delete()
        messages.success(request, f'Producto "{descripcion}" eliminado de la solicitud.')

    return redirect('almacen:solicitud_detail', pk=pk)


@login_required
@permission_required('almacen.autorizar_salida_almacen', raise_exception=True)
def autorizar_solicitud(request, pk):
    """Autorizar o rechazar una solicitud de salida"""
    solicitud = get_object_or_404(SolicitudSalida, pk=pk)
    
    # Validar que la solicitud esté pendiente
    if solicitud.estado != 'PENDIENTE':
        messages.error(request, 'Esta solicitud ya fue procesada.')
        return redirect('almacen:solicitud_detail', pk=pk)
    
    if request.method == 'POST':
        form = AutorizarSolicitudForm(request.POST)
        if form.is_valid():
            accion = form.cleaned_data['accion']
            comentarios = form.cleaned_data['comentarios']
            
            if accion == 'autorizar':
                solicitud.autorizar(request.user, comentarios)
                messages.success(request, 'Solicitud autorizada exitosamente.')
            else:
                solicitud.rechazar(request.user, comentarios)
                messages.warning(request, 'Solicitud rechazada.')
            
            return redirect('almacen:solicitud_detail', pk=pk)
    else:
        form = AutorizarSolicitudForm()
    
    context = {
        'solicitud': solicitud,
        'form': form,
    }
    return render(request, 'almacen/autorizar_solicitud.html', context)


@login_required
def procesar_entrega(request, pk):
    """Procesar la entrega de una solicitud autorizada"""
    solicitud = get_object_or_404(SolicitudSalida, pk=pk)
    
    # Validar que la solicitud esté autorizada
    if solicitud.estado != 'AUTORIZADA':
        messages.error(request, 'Solo se pueden entregar solicitudes autorizadas.')
        return redirect('almacen:solicitud_detail', pk=pk)
    
    if request.method == 'POST':
        # Crear la salida
        salida = SalidaAlmacen.objects.create(
            solicitud_salida=solicitud,
            entregado_a=solicitud.solicitante,
            entregado_por=request.user,
            observaciones=request.POST.get('observaciones', '')
        )
        
        # Procesar cada item
        items_procesados = 0
        for item_solicitud in solicitud.items.all():
            cantidad_key = f'cantidad_{item_solicitud.pk}'
            cantidad = request.POST.get(cantidad_key)
            
            if cantidad and float(cantidad) > 0:
                # Crear item de salida
                ItemSalidaAlmacen.objects.create(
                    salida=salida,
                    item_solicitud=item_solicitud,
                    producto_almacen=item_solicitud.producto_almacen,
                    cantidad_entregada=cantidad,
                    lote=request.POST.get(f'lote_{item_solicitud.pk}', ''),
                    ubicacion_origen=item_solicitud.producto_almacen.localidad
                )
                items_procesados += 1
        
        if items_procesados > 0:
            messages.success(request, f'Entrega procesada exitosamente. Folio: {salida.folio}')
            return redirect('almacen:salida_detail', pk=salida.pk)
        else:
            salida.delete()
            messages.error(request, 'No se procesó ningún item.')
    
    context = {
        'solicitud': solicitud,
        'items': solicitud.items.select_related('producto_almacen').all(),
    }
    return render(request, 'almacen/procesar_entrega.html', context)


# ========== SalidaAlmacen Views ==========

class SalidaAlmacenListView(LoginRequiredMixin, ListView):
    """Lista de salidas"""
    model = SalidaAlmacen
    template_name = 'almacen/salida_list.html'
    context_object_name = 'salidas'
    paginate_by = 20
    
    def get_queryset(self):
        return SalidaAlmacen.objects.select_related(
            'solicitud_salida', 'entregado_a', 'entregado_por'
        ).order_by('-fecha_salida')


class SalidaAlmacenDetailView(LoginRequiredMixin, DetailView):
    """Detalle de salida"""
    model = SalidaAlmacen
    template_name = 'almacen/salida_detail.html'
    context_object_name = 'salida'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.select_related(
            'producto_almacen', 'item_solicitud'
        ).all()
        return context


# ========== MovimientoAlmacen Views ==========

class MovimientoAlmacenListView(LoginRequiredMixin, ListView):
    """Historial de movimientos"""
    model = MovimientoAlmacen
    template_name = 'almacen/movimiento_list.html'
    context_object_name = 'movimientos'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = MovimientoAlmacen.objects.select_related(
            'producto_almacen', 'usuario', 'entrada_almacen', 'salida_almacen'
        )
        
        # Filtro por producto
        producto_id = self.request.GET.get('producto')
        if producto_id:
            queryset = queryset.filter(producto_almacen_id=producto_id)
        
        # Filtro por tipo
        tipo = self.request.GET.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        
        return queryset.order_by('-fecha_movimiento')


# ========== AlertaStock Views ==========

class AlertaStockListView(LoginRequiredMixin, ListView):
    """Lista de alertas"""
    model = AlertaStock
    template_name = 'almacen/alerta_list.html'
    context_object_name = 'alertas'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = AlertaStock.objects.select_related('producto_almacen')
        
        # Mostrar solo alertas no resueltas por defecto
        mostrar_resueltas = self.request.GET.get('resueltas', 'false')
        if mostrar_resueltas != 'true':
            queryset = queryset.filter(resuelta=False)
        
        return queryset.order_by('resuelta', '-fecha_generacion')


@login_required
def resolver_alerta(request, pk):
    """Resolver una alerta"""
    alerta = get_object_or_404(AlertaStock, pk=pk)
    
    if request.method == 'POST':
        form = ResolverAlertaForm(request.POST)
        if form.is_valid():
            alerta.resolver(request.user)
            messages.success(request, 'Alerta resuelta exitosamente.')
            return redirect('almacen:alerta_list')
    else:
        form = ResolverAlertaForm()
    
    context = {
        'alerta': alerta,
        'form': form,
    }
    return render(request, 'almacen/resolver_alerta.html', context)


# ========== Salida Rápida de Consumibles ==========

@login_required
def salida_rapida_consumible(request):
    """Formulario de salida rápida para productos consumibles"""
    if request.method == 'POST':
        form = SalidaRapidaConsumibleForm(request.POST)
        if form.is_valid():
            salida = form.save(commit=False)
            salida.entregado_por = request.user
            salida.save()

            # Reducir stock y crear movimiento
            producto = salida.producto
            cantidad_anterior = producto.cantidad
            producto.reducir_stock(salida.cantidad)

            MovimientoAlmacen.objects.create(
                tipo='SALIDA',
                producto_almacen=producto,
                cantidad=-salida.cantidad,
                cantidad_anterior=cantidad_anterior,
                cantidad_posterior=producto.cantidad,
                usuario=request.user,
                observaciones=f"Salida rápida consumible {salida.folio} - {salida.motivo}"
            )

            messages.success(
                request,
                f'Salida rápida registrada. Folio: {salida.folio} - '
                f'{salida.cantidad} {producto.unidad_medida} de {producto.descripcion}'
            )
            return redirect('almacen:salida_rapida_consumible')
    else:
        form = SalidaRapidaConsumibleForm()

    # Salidas recientes de consumibles
    salidas_recientes = SalidaRapidaConsumible.objects.select_related(
        'producto', 'entregado_por'
    ).order_by('-fecha_salida')[:20]

    # Datos de productos para validación en frontend
    productos_data = {
        str(p.id): {
            'stock': float(p.cantidad),
            'unidad': p.unidad_medida,
            'descripcion': p.descripcion,
        }
        for p in ProductoAlmacen.objects.filter(es_consumible=True, activo=True, cantidad__gt=0)
    }

    context = {
        'form': form,
        'salidas_recientes': salidas_recientes,
        'productos_json': json.dumps(productos_data),
    }
    return render(request, 'almacen/salida_rapida_consumible.html', context)


# ========== Asignación Rápida de Consumible a Unidad ==========

@login_required
def asignar_consumible_unidad(request, pk):
    """Formulario de asignación rápida para QR/NFC: solo selecciona la unidad"""
    producto = get_object_or_404(
        ProductoAlmacen, pk=pk, es_consumible=True, activo=True
    )

    if request.method == 'POST':
        form = AsignacionConsumibleUnidadForm(request.POST, producto=producto)
        if form.is_valid():
            unidad = form.cleaned_data['unidad']
            cantidad = 1

            salida = SalidaRapidaConsumible.objects.create(
                producto=producto,
                cantidad=cantidad,
                unidad=unidad,
                solicitante=str(unidad),
                motivo=f'Asignación directa a {unidad}',
                entregado_por=request.user,
            )

            cantidad_anterior = producto.cantidad
            producto.reducir_stock(cantidad)

            MovimientoAlmacen.objects.create(
                tipo='SALIDA',
                producto_almacen=producto,
                cantidad=-cantidad,
                cantidad_anterior=cantidad_anterior,
                cantidad_posterior=producto.cantidad,
                usuario=request.user,
                observaciones=f'Asignación rápida {salida.folio} a {unidad}',
            )

            messages.success(
                request,
                f'Registrado: {cantidad} {producto.unidad_medida} de '
                f'{producto.descripcion} asignado a {unidad}. Folio: {salida.folio}'
            )
            return redirect('almacen:asignar_consumible_unidad', pk=pk)
    else:
        form = AsignacionConsumibleUnidadForm(producto=producto)

    asignaciones_recientes = SalidaRapidaConsumible.objects.filter(
        producto=producto,
        unidad__isnull=False,
    ).select_related('unidad', 'entregado_por').order_by('-fecha_salida')[:10]

    context = {
        'producto': producto,
        'form': form,
        'asignaciones_recientes': asignaciones_recientes,
    }
    return render(request, 'almacen/asignar_consumible_unidad.html', context)


# ========== Reportes ==========

@login_required
def reporte_inventario(request):
    """Reporte de inventario actual"""
    productos = ProductoAlmacen.objects.filter(activo=True).select_related(
        'proveedor_principal'
    ).order_by('categoria', 'subcategoria', 'descripcion')
    
    # Aplicar filtros si existen
    categoria = request.GET.get('categoria')
    if categoria:
        productos = productos.filter(categoria__icontains=categoria)
    
    # Calcular totales
    total_valor = sum(p.costo_total for p in productos)
    total_items = productos.count()
    
    context = {
        'productos': productos,
        'total_valor': total_valor,
        'total_items': total_items,
    }
    return render(request, 'almacen/reporte_inventario.html', context)


@login_required
def reporte_stock_critico(request):
    """Reporte de productos con stock crítico"""
    productos_stock_bajo = ProductoAlmacen.objects.filter(
        activo=True,
        cantidad__lte=F('stock_minimo')
    ).select_related('proveedor_principal').order_by('cantidad')
    
    context = {
        'productos': productos_stock_bajo,
    }
    return render(request, 'almacen/reporte_stock_critico.html', context)


@login_required
def reporte_proximos_caducar(request):
    """Reporte de productos próximos a caducar"""
    fecha_limite = timezone.now().date() + timedelta(days=30)
    productos = ProductoAlmacen.objects.filter(
        activo=True,
        tiene_caducidad=True,
        fecha_caducidad__lte=fecha_limite
    ).order_by('fecha_caducidad')
    
    context = {
        'productos': productos,
        'fecha_limite': fecha_limite,
    }
    return render(request, 'almacen/reporte_caducidad.html', context)


# ========== Asignación de Salida ==========

@login_required
def asignacion_salida_create(request):
    from modulos.unidades.models import Unidad
    from modulos.equipos.models import Equipo
    from modulos.dollys.models import Dolly
    from modulos.caja_seca.models import CajaSeca

    if request.method == 'POST':
        fecha = request.POST.get('fecha')
        solicitante = request.POST.get('solicitante', '').strip()
        tipo_destino = request.POST.get('tipo_destino', '')
        unidad_id = request.POST.get('unidad') or None
        equipo_id = request.POST.get('equipo') or None
        dolly_id = request.POST.get('dolly') or None
        caja_seca_id = request.POST.get('caja_seca') or None
        otro_destino = request.POST.get('otro_destino', '').strip()
        justificacion = request.POST.get('justificacion', '').strip()
        items_raw = request.POST.get('items_json', '[]')

        try:
            items = json.loads(items_raw)
        except (json.JSONDecodeError, ValueError):
            items = []

        errors = []
        if not solicitante:
            errors.append('El solicitante es requerido.')
        if not tipo_destino:
            errors.append('El tipo de destino es requerido.')
        if not justificacion:
            errors.append('La justificación es requerida.')
        if not items:
            errors.append('Agrega al menos un producto.')

        if not errors:
            asignacion = AsignacionSalida(
                fecha=fecha,
                solicitante=solicitante,
                tipo_destino=tipo_destino,
                otro_destino=otro_destino,
                justificacion=justificacion,
                entregado_por=request.user,
            )
            if tipo_destino == 'UNIDAD' and unidad_id:
                asignacion.unidad_id = unidad_id
            elif tipo_destino == 'EQUIPO' and equipo_id:
                asignacion.equipo_id = equipo_id
            elif tipo_destino == 'DOLLY' and dolly_id:
                asignacion.dolly_id = dolly_id
            elif tipo_destino == 'CAJA_SECA' and caja_seca_id:
                asignacion.caja_seca_id = caja_seca_id
            asignacion.save()

            for it in items:
                try:
                    producto = ProductoAlmacen.objects.get(pk=it['id'])
                    ItemAsignacionSalida.objects.create(
                        asignacion=asignacion,
                        producto=producto,
                        cantidad=it['cantidad'],
                        observaciones=it.get('observaciones', ''),
                    )
                except (ProductoAlmacen.DoesNotExist, KeyError):
                    pass

            messages.success(request, f'Asignación {asignacion.folio} registrada correctamente.')
            return redirect('almacen:asignacion_salida_list')

        context = {
            'errors': errors,
            'post': request.POST,
            'unidades': Unidad.objects.filter(activa=True).order_by('numero_economico'),
            'equipos': Equipo.objects.filter(activo=True).order_by('numero_economico'),
            'dollys': Dolly.objects.filter(activo=True).order_by('numero_economico'),
            'cajas': CajaSeca.objects.filter(activo=True).order_by('numero_economico'),
            'tipo_choices': AsignacionSalida.TIPO_CHOICES,
        }
        return render(request, 'almacen/asignacion_salida_form.html', context)

    from modulos.unidades.models import Unidad
    from modulos.equipos.models import Equipo
    from modulos.dollys.models import Dolly
    from modulos.caja_seca.models import CajaSeca

    context = {
        'unidades': Unidad.objects.filter(activa=True).order_by('numero_economico'),
        'equipos': Equipo.objects.filter(activo=True).order_by('numero_economico'),
        'dollys': Dolly.objects.filter(activo=True).order_by('numero_economico'),
        'cajas': CajaSeca.objects.filter(activo=True).order_by('numero_economico'),
        'tipo_choices': AsignacionSalida.TIPO_CHOICES,
    }
    return render(request, 'almacen/asignacion_salida_form.html', context)


class AsignacionSalidaListView(LoginRequiredMixin, ListView):
    model = AsignacionSalida
    template_name = 'almacen/asignacion_salida_list.html'
    context_object_name = 'asignaciones'
    paginate_by = 25

    def get_queryset(self):
        qs = AsignacionSalida.objects.select_related(
            'unidad', 'equipo', 'dolly', 'caja_seca', 'entregado_por'
        )
        tipo = self.request.GET.get('tipo', '')
        buscar = self.request.GET.get('buscar', '').strip()
        if tipo:
            qs = qs.filter(tipo_destino=tipo)
        if buscar:
            qs = qs.filter(
                Q(folio__icontains=buscar) |
                Q(solicitante__icontains=buscar) |
                Q(otro_destino__icontains=buscar)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tipo_choices'] = AsignacionSalida.TIPO_CHOICES
        ctx['tipo_sel'] = self.request.GET.get('tipo', '')
        ctx['buscar'] = self.request.GET.get('buscar', '')
        return ctx


class AsignacionSalidaDetailView(LoginRequiredMixin, DetailView):
    model = AsignacionSalida
    template_name = 'almacen/asignacion_salida_detail.html'
    context_object_name = 'asignacion'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = self.object.items.select_related('producto')
        return ctx


@login_required
def api_activos_por_tipo(request):
    tipo = request.GET.get('tipo', '')
    data = []
    if tipo == 'UNIDAD':
        from modulos.unidades.models import Unidad
        data = list(Unidad.objects.filter(activa=True).order_by('numero_economico').values('id', 'numero_economico'))
    elif tipo == 'EQUIPO':
        from modulos.equipos.models import Equipo
        data = list(Equipo.objects.filter(activo=True).order_by('numero_economico').values('id', 'numero_economico'))
    elif tipo == 'DOLLY':
        from modulos.dollys.models import Dolly
        data = list(Dolly.objects.filter(activo=True).order_by('numero_economico').values('id', 'numero_economico'))
    elif tipo == 'CAJA_SECA':
        from modulos.caja_seca.models import CajaSeca
        data = list(CajaSeca.objects.filter(activo=True).order_by('numero_economico').values('id', 'numero_economico'))
    return JsonResponse({'activos': data})
