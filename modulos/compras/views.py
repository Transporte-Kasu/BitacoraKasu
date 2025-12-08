from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta

from .models import (
    Proveedor, Producto, Requisicion, OrdenCompra, 
    RecepcionAlmacen, Inventario
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
