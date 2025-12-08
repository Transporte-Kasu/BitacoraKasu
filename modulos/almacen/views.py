from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta

from .models import (
    ProductoAlmacen, EntradaAlmacen, ItemEntradaAlmacen,
    SolicitudSalida, ItemSolicitudSalida, SalidaAlmacen,
    ItemSalidaAlmacen, MovimientoAlmacen, AlertaStock
)
from .forms import (
    ProductoAlmacenForm, EntradaAlmacenForm, ItemEntradaAlmacenForm,
    SolicitudSalidaForm, ItemSolicitudSalidaForm, AutorizarSolicitudForm,
    SalidaAlmacenForm, ItemSalidaAlmacenForm, FiltroProductosForm,
    FiltroEntradasForm, FiltroSolicitudesForm, ResolverAlertaForm
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
        categoria = self.request.GET.get('categoria')
        subcategoria = self.request.GET.get('subcategoria')
        sku = self.request.GET.get('sku')
        stock_bajo = self.request.GET.get('stock_bajo')
        proximo_caducar = self.request.GET.get('proximo_caducar')
        activo = self.request.GET.get('activo')
        
        if categoria:
            queryset = queryset.filter(categoria__icontains=categoria)
        if subcategoria:
            queryset = queryset.filter(subcategoria__icontains=subcategoria)
        if sku:
            queryset = queryset.filter(sku__icontains=sku)
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
        return context


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
    success_url = reverse_lazy('almacen:producto_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Producto actualizado exitosamente.')
        return super().form_valid(form)


class ProductoAlmacenDeleteView(LoginRequiredMixin, DeleteView):
    """Eliminar producto"""
    model = ProductoAlmacen
    template_name = 'almacen/producto_confirm_delete.html'
    success_url = reverse_lazy('almacen:producto_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Producto eliminado exitosamente.')
        return super().delete(request, *args, **kwargs)


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
        return context


class SolicitudSalidaCreateView(LoginRequiredMixin, CreateView):
    """Crear solicitud de salida"""
    model = SolicitudSalida
    form_class = SolicitudSalidaForm
    template_name = 'almacen/solicitud_form.html'
    success_url = reverse_lazy('almacen:solicitud_list')
    
    def form_valid(self, form):
        form.instance.solicitante = self.request.user
        messages.success(self.request, f'Solicitud {form.instance.folio} creada exitosamente.')
        return super().form_valid(form)


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
