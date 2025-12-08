from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.contrib import messages
from django.urls import reverse_lazy
from datetime import timedelta

from .models import (
    Proveedor, Producto, Requisicion, ItemRequisicion, 
    OrdenCompra, RecepcionAlmacen, Inventario
)
from .forms import (
    ProveedorForm, ProductoForm, RequisicionForm, 
    ItemRequisicionForm, OrdenCompraForm
)


@login_required
def dashboard_compras(request):
    """Dashboard principal del módulo de compras"""
    # Estadísticas generales
    total_proveedores = Proveedor.objects.filter(activo=True).count()
    total_productos = Producto.objects.filter(activo=True).count()
    
    # Requisiciones pendientes
    requisiciones_pendientes = Requisicion.objects.filter(
        estado='PENDIENTE'
    ).count()
    
    # Órdenes de compra activas
    ordenes_activas = OrdenCompra.objects.exclude(
        estado__in=['RECIBIDA', 'CANCELADA']
    ).count()
    
    # Últimas requisiciones
    ultimas_requisiciones = Requisicion.objects.select_related(
        'solicitante', 'aprobada_por'
    ).order_by('-fecha_solicitud')[:10]
    
    # Últimas órdenes de compra
    ultimas_ordenes = OrdenCompra.objects.select_related(
        'proveedor', 'requisicion', 'creada_por'
    ).order_by('-fecha_creacion')[:10]
    
    # Recepciones recientes
    recepciones_recientes = RecepcionAlmacen.objects.select_related(
        'orden_compra', 'recibido_por'
    ).order_by('-fecha_recepcion')[:5]
    
    context = {
        'total_proveedores': total_proveedores,
        'total_productos': total_productos,
        'requisiciones_pendientes': requisiciones_pendientes,
        'ordenes_activas': ordenes_activas,
        'ultimas_requisiciones': ultimas_requisiciones,
        'ultimas_ordenes': ultimas_ordenes,
        'recepciones_recientes': recepciones_recientes,
    }
    return render(request, 'compras/dashboard.html', context)


class ProveedorListView(LoginRequiredMixin, ListView):
    """Lista de proveedores"""
    model = Proveedor
    template_name = 'compras/proveedor_list.html'
    context_object_name = 'proveedores'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Proveedor.objects.all()
        
        # Filtros
        search = self.request.GET.get('search')
        activo = self.request.GET.get('activo')
        
        if search:
            queryset = queryset.filter(
                Q(nombre__icontains=search) |
                Q(rfc__icontains=search) |
                Q(contacto__icontains=search)
            )
        
        if activo:
            queryset = queryset.filter(activo=(activo == 'true'))
        
        return queryset.order_by('nombre')


class RequisicionListView(LoginRequiredMixin, ListView):
    """Lista de requisiciones"""
    model = Requisicion
    template_name = 'compras/requisicion_list.html'
    context_object_name = 'requisiciones'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Requisicion.objects.select_related(
            'solicitante', 'aprobada_por'
        )
        
        # Filtros
        estado = self.request.GET.get('estado')
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        
        if estado:
            queryset = queryset.filter(estado=estado)
        if fecha_desde:
            queryset = queryset.filter(fecha_solicitud__date__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha_solicitud__date__lte=fecha_hasta)
        
        return queryset.order_by('-fecha_solicitud')


class OrdenCompraListView(LoginRequiredMixin, ListView):
    """Lista de órdenes de compra"""
    model = OrdenCompra
    template_name = 'compras/ordencompra_list.html'
    context_object_name = 'ordenes'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = OrdenCompra.objects.select_related(
            'proveedor', 'requisicion', 'creada_por'
        )
        
        # Filtros
        estado = self.request.GET.get('estado')
        proveedor = self.request.GET.get('proveedor')
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        
        if estado:
            queryset = queryset.filter(estado=estado)
        if proveedor:
            queryset = queryset.filter(proveedor_id=proveedor)
        if fecha_desde:
            queryset = queryset.filter(fecha_creacion__date__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha_creacion__date__lte=fecha_hasta)
        
        return queryset.order_by('-fecha_creacion')


class ProductoListView(LoginRequiredMixin, ListView):
    """Lista de productos"""
    model = Producto
    template_name = 'compras/producto_list.html'
    context_object_name = 'productos'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Producto.objects.all()
        
        # Filtros
        search = self.request.GET.get('search')
        categoria = self.request.GET.get('categoria')
        activo = self.request.GET.get('activo')
        
        if search:
            queryset = queryset.filter(
                Q(nombre__icontains=search) |
                Q(descripcion__icontains=search)
            )
        if categoria:
            queryset = queryset.filter(categoria__icontains=categoria)
        if activo:
            queryset = queryset.filter(activo=(activo == 'true'))
        
        return queryset.order_by('categoria', 'nombre')


# ============================================================================
# CRUD PROVEEDORES
# ============================================================================

class ProveedorCreateView(LoginRequiredMixin, CreateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = 'compras/proveedor_form.html'
    success_url = reverse_lazy('compras:proveedor_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Proveedor {form.instance.nombre} creado exitosamente.')
        return super().form_valid(form)


class ProveedorUpdateView(LoginRequiredMixin, UpdateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = 'compras/proveedor_form.html'
    success_url = reverse_lazy('compras:proveedor_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Proveedor {form.instance.nombre} actualizado exitosamente.')
        return super().form_valid(form)


class ProveedorDeleteView(LoginRequiredMixin, DeleteView):
    model = Proveedor
    template_name = 'compras/proveedor_confirm_delete.html'
    success_url = reverse_lazy('compras:proveedor_list')
    
    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, f'Proveedor {obj.nombre} eliminado exitosamente.')
        return super().delete(request, *args, **kwargs)


# ============================================================================
# CRUD PRODUCTOS
# ============================================================================

class ProductoCreateView(LoginRequiredMixin, CreateView):
    model = Producto
    form_class = ProductoForm
    template_name = 'compras/producto_form.html'
    success_url = reverse_lazy('compras:producto_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Producto {form.instance.nombre} creado exitosamente.')
        return super().form_valid(form)


class ProductoUpdateView(LoginRequiredMixin, UpdateView):
    model = Producto
    form_class = ProductoForm
    template_name = 'compras/producto_form.html'
    success_url = reverse_lazy('compras:producto_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Producto {form.instance.nombre} actualizado exitosamente.')
        return super().form_valid(form)


class ProductoDeleteView(LoginRequiredMixin, DeleteView):
    model = Producto
    template_name = 'compras/producto_confirm_delete.html'
    success_url = reverse_lazy('compras:producto_list')
    
    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, f'Producto {obj.nombre} eliminado exitosamente.')
        return super().delete(request, *args, **kwargs)


# ============================================================================
# CRUD REQUISICIONES
# ============================================================================

@login_required
def requisicion_crear(request):
    """Crear nueva requisición"""
    if request.method == 'POST':
        form = RequisicionForm(request.POST)
        if form.is_valid():
            requisicion = form.save(commit=False)
            requisicion.solicitante = request.user
            requisicion.save()
            messages.success(request, f'Requisición {requisicion.folio} creada exitosamente.')
            return redirect('compras:requisicion_agregar_items', pk=requisicion.pk)
    else:
        form = RequisicionForm()
    
    return render(request, 'compras/requisicion_form.html', {'form': form})


@login_required
def requisicion_agregar_items(request, pk):
    """Agregar items a una requisición"""
    requisicion = get_object_or_404(Requisicion, pk=pk)
    
    # Solo permitir agregar items si está pendiente
    if requisicion.estado != 'PENDIENTE':
        messages.error(request, 'No se pueden agregar items a una requisición que ya fue procesada.')
        return redirect('compras:requisicion_list')
    
    if request.method == 'POST':
        form = ItemRequisicionForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.requisicion = requisicion
            item.save()
            messages.success(request, 'Item agregado exitosamente.')
            return redirect('compras:requisicion_agregar_items', pk=pk)
    else:
        form = ItemRequisicionForm()
    
    items = requisicion.items.select_related('producto')
    
    return render(request, 'compras/requisicion_agregar_items.html', {
        'requisicion': requisicion,
        'items': items,
        'form': form
    })


@login_required
def requisicion_eliminar_item(request, requisicion_pk, item_pk):
    """Eliminar un item de una requisición"""
    requisicion = get_object_or_404(Requisicion, pk=requisicion_pk)
    item = get_object_or_404(ItemRequisicion, pk=item_pk, requisicion=requisicion)
    
    if requisicion.estado != 'PENDIENTE':
        messages.error(request, 'No se pueden eliminar items de una requisición procesada.')
        return redirect('compras:requisicion_list')
    
    item.delete()
    messages.success(request, 'Item eliminado exitosamente.')
    return redirect('compras:requisicion_agregar_items', pk=requisicion_pk)


# ============================================================================
# CRUD ÓRDENES DE COMPRA
# ============================================================================

class OrdenCompraCreateView(LoginRequiredMixin, CreateView):
    model = OrdenCompra
    form_class = OrdenCompraForm
    template_name = 'compras/ordencompra_form.html'
    success_url = reverse_lazy('compras:ordencompra_list')
    
    def form_valid(self, form):
        form.instance.creada_por = self.request.user
        messages.success(self.request, f'Orden de compra {form.instance.folio} creada exitosamente.')
        return super().form_valid(form)


class OrdenCompraUpdateView(LoginRequiredMixin, UpdateView):
    model = OrdenCompra
    form_class = OrdenCompraForm
    template_name = 'compras/ordencompra_form.html'
    success_url = reverse_lazy('compras:ordencompra_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Orden de compra {form.instance.folio} actualizada exitosamente.')
        return super().form_valid(form)
