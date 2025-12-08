from django.contrib import admin
from .models import (
    Proveedor, Producto, Requisicion, ItemRequisicion,
    OrdenCompra, ItemOrdenCompra, RecepcionAlmacen, ItemRecepcion, Inventario
)


class ItemRequisicionInline(admin.TabularInline):
    model = ItemRequisicion
    extra = 1
    fields = ['producto', 'cantidad', 'descripcion_adicional']


@admin.register(Requisicion)
class RequisicionAdmin(admin.ModelAdmin):
    list_display = ['folio', 'solicitante', 'fecha_solicitud', 'fecha_requerida', 'estado', 'total_items']
    list_filter = ['estado', 'fecha_solicitud', 'fecha_requerida']
    search_fields = ['folio', 'solicitante__username', 'solicitante__first_name', 'solicitante__last_name']
    readonly_fields = ['folio', 'fecha_solicitud', 'aprobada_por', 'fecha_aprobacion']
    inlines = [ItemRequisicionInline]

    fieldsets = (
        ('Información General', {
            'fields': ('folio', 'solicitante', 'fecha_solicitud', 'fecha_requerida', 'justificacion', 'estado')
        }),
        ('Aprobación', {
            'fields': ('aprobada_por', 'fecha_aprobacion', 'comentarios_aprobacion'),
            'classes': ('collapse',)
        }),
    )


class ItemOrdenCompraInline(admin.TabularInline):
    model = ItemOrdenCompra
    extra = 0
    fields = ['item_requisicion', 'cantidad', 'precio_unitario', 'subtotal']
    readonly_fields = ['subtotal']


@admin.register(OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    list_display = ['folio', 'requisicion', 'proveedor', 'fecha_creacion', 'estado', 'factura_numero']
    list_filter = ['estado', 'fecha_creacion', 'proveedor']
    search_fields = ['folio', 'requisicion__folio', 'proveedor__nombre', 'factura_numero']
    readonly_fields = ['folio', 'fecha_creacion', 'creada_por']
    inlines = [ItemOrdenCompraInline]

    fieldsets = (
        ('Información General', {
            'fields': ('folio', 'requisicion', 'proveedor', 'fecha_creacion', 'creada_por', 'fecha_estimada_entrega', 'estado')
        }),
        ('Factura', {
            'fields': ('factura_numero', 'factura_fecha', 'factura_monto', 'factura_archivo')
        }),
        ('Notas', {
            'fields': ('notas',)
        }),
    )


class ItemRecepcionInline(admin.TabularInline):
    model = ItemRecepcion
    extra = 0
    fields = ['item_orden', 'cantidad_recibida', 'cantidad_aceptada', 'cantidad_rechazada', 'motivo_rechazo']


@admin.register(RecepcionAlmacen)
class RecepcionAlmacenAdmin(admin.ModelAdmin):
    list_display = ['orden_compra', 'fecha_recepcion', 'recibido_por', 'estado', 'ubicacion_almacen']
    list_filter = ['estado', 'fecha_recepcion']
    search_fields = ['orden_compra__folio', 'ubicacion_almacen', 'remision']
    readonly_fields = ['fecha_recepcion']
    inlines = [ItemRecepcionInline]


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'rfc', 'telefono', 'email', 'activo']
    list_filter = ['activo']
    search_fields = ['nombre', 'rfc', 'email']


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'categoria', 'unidad_medida', 'activo']
    list_filter = ['categoria', 'activo']
    search_fields = ['nombre', 'descripcion', 'categoria']


@admin.register(Inventario)
class InventarioAdmin(admin.ModelAdmin):
    list_display = ['producto', 'cantidad_disponible', 'ubicacion', 'fecha_actualizacion']
    list_filter = ['ubicacion', 'fecha_actualizacion']
    search_fields = ['producto__nombre', 'ubicacion']
    readonly_fields = ['fecha_actualizacion']