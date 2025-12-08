from django.contrib import admin
from .models import (
    ProductoAlmacen, EntradaAlmacen, ItemEntradaAlmacen,
    SolicitudSalida, ItemSolicitudSalida, SalidaAlmacen,
    ItemSalidaAlmacen, MovimientoAlmacen, AlertaStock
)


class ItemEntradaAlmacenInline(admin.TabularInline):
    model = ItemEntradaAlmacen
    extra = 1
    fields = ['producto_almacen', 'cantidad', 'costo_unitario', 'lote', 'ubicacion_asignada']


class ItemSolicitudSalidaInline(admin.TabularInline):
    model = ItemSolicitudSalida
    extra = 1
    fields = ['producto_almacen', 'cantidad_solicitada', 'cantidad_entregada']
    readonly_fields = ['cantidad_entregada']


class ItemSalidaAlmacenInline(admin.TabularInline):
    model = ItemSalidaAlmacen
    extra = 0
    fields = ['producto_almacen', 'cantidad_entregada', 'lote', 'ubicacion_origen']


@admin.register(ProductoAlmacen)
class ProductoAlmacenAdmin(admin.ModelAdmin):
    list_display = [
        'sku', 'descripcion', 'categoria', 'subcategoria', 'cantidad',
        'unidad_medida', 'stock_minimo', 'costo_unitario', 'activo'
    ]
    list_filter = ['categoria', 'activo', 'tiene_caducidad']
    search_fields = ['sku', 'descripcion', 'codigo_barras']
    readonly_fields = ['fecha_registro', 'fecha_actualizacion']
    fieldsets = (
        ('Información Básica', {
            'fields': ('categoria', 'subcategoria', 'sku', 'codigo_barras', 'descripcion', 'imagen')
        }),
        ('Ubicación y Stock', {
            'fields': ('localidad', 'cantidad', 'unidad_medida', 'stock_minimo', 'stock_maximo')
        }),
        ('Costos', {
            'fields': ('costo_unitario',)
        }),
        ('Caducidad', {
            'fields': ('tiene_caducidad', 'fecha_caducidad')
        }),
        ('Relaciones', {
            'fields': ('producto_compra', 'proveedor_principal', 'tiempo_reorden_dias')
        }),
        ('Metadata', {
            'fields': ('notas', 'activo', 'fecha_registro', 'fecha_actualizacion')
        }),
    )


@admin.register(EntradaAlmacen)
class EntradaAlmacenAdmin(admin.ModelAdmin):
    list_display = [
        'folio', 'tipo', 'fecha_entrada', 'recibido_por', 'total_items'
    ]
    list_filter = ['tipo', 'fecha_entrada']
    search_fields = ['folio', 'factura_numero']
    readonly_fields = ['folio']
    inlines = [ItemEntradaAlmacenInline]
    fieldsets = (
        ('Información Básica', {
            'fields': ('tipo', 'folio', 'fecha_entrada', 'recibido_por')
        }),
        ('Referencias', {
            'fields': ('orden_compra', 'orden_trabajo', 'recepcion_almacen_compras')
        }),
        ('Factura', {
            'fields': ('factura_numero', 'factura_archivo')
        }),
        ('Costos Adicionales', {
            'fields': ('costo_envio', 'costo_adicional')
        }),
        ('Observaciones', {
            'fields': ('observaciones',)
        }),
    )


@admin.register(ItemEntradaAlmacen)
class ItemEntradaAlmacenAdmin(admin.ModelAdmin):
    list_display = [
        'entrada', 'producto_almacen', 'cantidad', 'costo_unitario', 'costo_total'
    ]
    list_filter = ['entrada__tipo']
    search_fields = ['entrada__folio', 'producto_almacen__sku', 'producto_almacen__descripcion']


@admin.register(SolicitudSalida)
class SolicitudSalidaAdmin(admin.ModelAdmin):
    list_display = [
        'folio', 'tipo', 'estado', 'solicitante', 'fecha_solicitud',
        'requiere_autorizacion', 'autorizado_por'
    ]
    list_filter = ['tipo', 'estado', 'requiere_autorizacion', 'fecha_solicitud']
    search_fields = ['folio', 'solicitante__username']
    readonly_fields = ['folio', 'fecha_solicitud', 'fecha_autorizacion']
    inlines = [ItemSolicitudSalidaInline]
    fieldsets = (
        ('Información Básica', {
            'fields': ('tipo', 'folio', 'solicitante', 'fecha_solicitud', 'estado')
        }),
        ('Referencias', {
            'fields': ('orden_trabajo',)
        }),
        ('Justificación', {
            'fields': ('justificacion',)
        }),
        ('Autorización', {
            'fields': (
                'requiere_autorizacion', 'autorizado_por', 'fecha_autorizacion',
                'comentarios_autorizacion'
            )
        }),
    )


@admin.register(ItemSolicitudSalida)
class ItemSolicitudSalidaAdmin(admin.ModelAdmin):
    list_display = [
        'solicitud', 'producto_almacen', 'cantidad_solicitada',
        'cantidad_entregada', 'cantidad_pendiente'
    ]
    list_filter = ['solicitud__estado']
    search_fields = ['solicitud__folio', 'producto_almacen__sku']


@admin.register(SalidaAlmacen)
class SalidaAlmacenAdmin(admin.ModelAdmin):
    list_display = [
        'folio', 'solicitud_salida', 'fecha_salida', 'entregado_a', 'entregado_por'
    ]
    list_filter = ['fecha_salida']
    search_fields = ['folio', 'solicitud_salida__folio']
    readonly_fields = ['folio']
    inlines = [ItemSalidaAlmacenInline]


@admin.register(ItemSalidaAlmacen)
class ItemSalidaAlmacenAdmin(admin.ModelAdmin):
    list_display = [
        'salida', 'producto_almacen', 'cantidad_entregada', 'lote'
    ]
    search_fields = ['salida__folio', 'producto_almacen__sku']


@admin.register(MovimientoAlmacen)
class MovimientoAlmacenAdmin(admin.ModelAdmin):
    list_display = [
        'fecha_movimiento', 'tipo', 'producto_almacen', 'cantidad',
        'cantidad_anterior', 'cantidad_posterior', 'usuario'
    ]
    list_filter = ['tipo', 'fecha_movimiento']
    search_fields = ['producto_almacen__sku', 'producto_almacen__descripcion']
    readonly_fields = ['fecha_movimiento']
    date_hierarchy = 'fecha_movimiento'


@admin.register(AlertaStock)
class AlertaStockAdmin(admin.ModelAdmin):
    list_display = [
        'tipo_alerta', 'producto_almacen', 'fecha_generacion', 'resuelta',
        'resuelta_por', 'fecha_resolucion'
    ]
    list_filter = ['tipo_alerta', 'resuelta', 'fecha_generacion']
    search_fields = ['producto_almacen__sku', 'producto_almacen__descripcion', 'mensaje']
    readonly_fields = ['fecha_generacion', 'fecha_resolucion']
    date_hierarchy = 'fecha_generacion'
