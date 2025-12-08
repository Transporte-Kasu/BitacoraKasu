from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    TipoMantenimiento, CategoriaFalla, OrdenTrabajo, PiezaRequerida,
    SeguimientoOrden, ChecklistMantenimiento, ChecklistOrden, HistorialMantenimiento
)


@admin.register(TipoMantenimiento)
class TipoMantenimientoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'tipo', 'kilometraje_sugerido', 'dias_sugeridos', 'activo']
    list_filter = ['tipo', 'activo']
    search_fields = ['nombre', 'descripcion']
    ordering = ['tipo', 'nombre']


@admin.register(CategoriaFalla)
class CategoriaFallaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'prioridad_default', 'activo']
    list_filter = ['prioridad_default', 'activo']
    search_fields = ['nombre', 'descripcion']


class PiezaRequeridaInline(admin.TabularInline):
    model = PiezaRequerida
    extra = 1
    fields = [
        'producto', 'cantidad', 'estado', 'costo_estimado',
        'costo_real', 'descripcion_uso'
    ]
    readonly_fields = ['fecha_agregada']
    # Removido autocomplete_fields para Producto


class ChecklistOrdenInline(admin.TabularInline):
    model = ChecklistOrden
    extra = 0
    fields = ['item_checklist', 'estado', 'observaciones', 'fecha_revision']
    readonly_fields = ['fecha_revision']


class SeguimientoOrdenInline(admin.TabularInline):
    model = SeguimientoOrden
    extra = 0
    fields = ['fecha', 'usuario', 'estado_anterior', 'estado_nuevo', 'comentario']
    readonly_fields = ['fecha', 'usuario', 'estado_anterior', 'estado_nuevo']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrdenTrabajo)
class OrdenTrabajoAdmin(admin.ModelAdmin):
    list_display = [
        'folio', 'unidad', 'estado_badge', 'prioridad_badge',
        'tipo_mantenimiento', 'mecanico_asignado', 'fecha_creacion',
        'dias_en_taller_display', 'costo_total_display'
    ]
    list_filter = [
        'estado', 'prioridad', 'tipo_mantenimiento',
        'fecha_creacion', 'mecanico_asignado'
    ]
    search_fields = [
        'folio', 'unidad__numero_economico', 'unidad__placas',
        'descripcion_problema', 'diagnostico'
    ]
    readonly_fields = [
        'folio', 'fecha_creacion', 'fecha_inicio_real', 'fecha_finalizacion',
        'fecha_diagnostico', 'creada_por', 'dias_en_taller_display',
        'costo_total_estimado_display', 'costo_total_real_display',
        'costo_total_piezas_estimado_display', 'costo_total_piezas_real_display'
    ]
    # Removido autocomplete_fields para evitar errores si no hay admin de Unidad/Operador

    fieldsets = (
        ('Información Básica', {
            'fields': (
                'folio', 'unidad', 'operador_reporta', 'creada_por',
                'fecha_creacion'
            )
        }),
        ('Tipo de Servicio', {
            'fields': (
                'tipo_mantenimiento', 'categoria_falla', 'prioridad',
                'kilometraje_ingreso', 'kilometraje_salida'
            )
        }),
        ('Descripción del Problema', {
            'fields': ('descripcion_problema', 'sintomas')
        }),
        ('Asignación y Programación', {
            'fields': (
                'mecanico_asignado', 'supervisor', 'fecha_programada',
                'fecha_inicio_real', 'fecha_finalizacion', 'dias_en_taller_display'
            )
        }),
        ('Estado', {
            'fields': ('estado',)
        }),
        ('Diagnóstico', {
            'fields': ('diagnostico', 'fecha_diagnostico'),
            'classes': ('collapse',)
        }),
        ('Trabajo Realizado', {
            'fields': ('trabajo_realizado',),
            'classes': ('collapse',)
        }),
        ('Costos', {
            'fields': (
                ('costo_estimado_mano_obra', 'costo_real_mano_obra'),
                ('costo_total_piezas_estimado_display', 'costo_total_piezas_real_display'),
                ('costo_total_estimado_display', 'costo_total_real_display')
            ),
            'classes': ('collapse',)
        }),
        ('Observaciones', {
            'fields': ('observaciones',),
            'classes': ('collapse',)
        }),
    )

    inlines = [PiezaRequeridaInline, ChecklistOrdenInline, SeguimientoOrdenInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creada_por = request.user

        # Registrar cambio de estado
        if change:
            old_obj = OrdenTrabajo.objects.get(pk=obj.pk)
            if old_obj.estado != obj.estado:
                SeguimientoOrden.objects.create(
                    orden_trabajo=obj,
                    usuario=request.user,
                    estado_anterior=old_obj.estado,
                    estado_nuevo=obj.estado,
                    comentario=f"Estado cambiado desde el admin"
                )

        super().save_model(request, obj, form, change)

    def estado_badge(self, obj):
        colors = {
            'PENDIENTE': '#6c757d',
            'EN_DIAGNOSTICO': '#17a2b8',
            'ESPERANDO_PIEZAS': '#ffc107',
            'EN_REPARACION': '#007bff',
            'EN_PRUEBAS': '#20c997',
            'COMPLETADA': '#28a745',
            'CANCELADA': '#dc3545',
        }
        color = colors.get(obj.estado, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color, obj.get_estado_display()
        )
    estado_badge.short_description = 'Estado'

    def prioridad_badge(self, obj):
        colors = {
            'BAJA': '#28a745',
            'MEDIA': '#ffc107',
            'ALTA': '#fd7e14',
            'CRITICA': '#dc3545',
        }
        color = colors.get(obj.prioridad, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color, obj.get_prioridad_display()
        )
    prioridad_badge.short_description = 'Prioridad'

    def dias_en_taller_display(self, obj):
        dias = obj.dias_en_taller
        if dias > 7:
            color = '#dc3545'
        elif dias > 3:
            color = '#ffc107'
        else:
            color = '#28a745'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} días</span>',
            color, dias
        )
    dias_en_taller_display.short_description = 'Días en Taller'

    def costo_total_display(self, obj):
        return f"${obj.costo_total_real:,.2f}"
    costo_total_display.short_description = 'Costo Total Real'

    def costo_total_estimado_display(self, obj):
        return f"${obj.costo_total_estimado:,.2f}"
    costo_total_estimado_display.short_description = 'Total Estimado'

    def costo_total_real_display(self, obj):
        return f"${obj.costo_total_real:,.2f}"
    costo_total_real_display.short_description = 'Total Real'

    def costo_total_piezas_estimado_display(self, obj):
        return f"${obj.costo_total_piezas_estimado:,.2f}"
    costo_total_piezas_estimado_display.short_description = 'Piezas Estimado'

    def costo_total_piezas_real_display(self, obj):
        return f"${obj.costo_total_piezas_real:,.2f}"
    costo_total_piezas_real_display.short_description = 'Piezas Real'

    actions = ['generar_requisicion_piezas', 'marcar_completadas', 'marcar_en_reparacion']

    def generar_requisicion_piezas(self, request, queryset):
        """Genera requisiciones para las piezas pendientes de las órdenes seleccionadas"""
        from modulos.compras.models import Requisicion, ItemRequisicion
        from django.utils import timezone

        count = 0
        for orden in queryset:
            piezas_pendientes = orden.piezas_requeridas.filter(estado='PENDIENTE')

            if piezas_pendientes.exists():
                # Crear requisición
                requisicion = Requisicion.objects.create(
                    solicitante=request.user,
                    fecha_requerida=orden.fecha_programada or timezone.now().date(),
                    justificacion=f"Piezas para {orden.folio} - {orden.descripcion_problema}",
                    estado='PENDIENTE'
                )

                # Crear items de requisición
                for pieza in piezas_pendientes:
                    item = ItemRequisicion.objects.create(
                        requisicion=requisicion,
                        producto=pieza.producto,
                        cantidad=pieza.cantidad,
                        descripcion_adicional=f"OT: {orden.folio} - {pieza.descripcion_uso}"
                    )

                    # Actualizar estado de la pieza
                    pieza.marcar_como_solicitada(item)

                # Actualizar estado de la orden
                if orden.estado == 'EN_DIAGNOSTICO':
                    orden.estado = 'ESPERANDO_PIEZAS'
                    orden.save()

                count += 1

        self.message_user(request, f"Se generaron {count} requisiciones de compra.")
    generar_requisicion_piezas.short_description = "Generar requisiciones de piezas"

    def marcar_completadas(self, request, queryset):
        """Marca las órdenes seleccionadas como completadas"""
        count = queryset.filter(estado='EN_PRUEBAS').update(
            estado='COMPLETADA',
            fecha_finalizacion=timezone.now()
        )
        self.message_user(request, f"{count} órdenes marcadas como completadas.")
    marcar_completadas.short_description = "Marcar como completadas"

    def marcar_en_reparacion(self, request, queryset):
        """Marca las órdenes como en reparación"""
        count = queryset.filter(
            estado__in=['EN_DIAGNOSTICO', 'ESPERANDO_PIEZAS']
        ).update(estado='EN_REPARACION')
        self.message_user(request, f"{count} órdenes marcadas en reparación.")
    marcar_en_reparacion.short_description = "Marcar en reparación"


@admin.register(PiezaRequerida)
class PiezaRequeridaAdmin(admin.ModelAdmin):
    list_display = [
        'orden_trabajo', 'producto', 'cantidad', 'estado_badge',
        'subtotal_estimado_display', 'subtotal_real_display',
        'fecha_agregada'
    ]
    list_filter = ['estado', 'fecha_agregada', 'fecha_solicitud']
    search_fields = [
        'orden_trabajo__folio', 'producto__nombre',
        'descripcion_uso'
    ]
    readonly_fields = [
        'fecha_agregada', 'agregada_por', 'fecha_solicitud',
        'fecha_recepcion', 'fecha_instalacion', 'subtotal_estimado_display',
        'subtotal_real_display'
    ]
    # Removido autocomplete_fields

    fieldsets = (
        ('Información Básica', {
            'fields': (
                'orden_trabajo', 'producto', 'cantidad',
                'descripcion_uso', 'agregada_por', 'fecha_agregada'
            )
        }),
        ('Estado y Costos', {
            'fields': (
                'estado', 'costo_estimado', 'costo_real',
                'subtotal_estimado_display', 'subtotal_real_display'
            )
        }),
        ('Seguimiento', {
            'fields': (
                'item_requisicion', 'fecha_solicitud',
                'fecha_recepcion', 'fecha_instalacion'
            )
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.agregada_por = request.user
        super().save_model(request, obj, form, change)

    def estado_badge(self, obj):
        colors = {
            'PENDIENTE': '#6c757d',
            'SOLICITADA': '#17a2b8',
            'EN_COMPRA': '#ffc107',
            'RECIBIDA': '#20c997',
            'INSTALADA': '#28a745',
            'CANCELADA': '#dc3545',
        }
        color = colors.get(obj.estado, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 0.85em;">{}</span>',
            color, obj.get_estado_display()
        )
    estado_badge.short_description = 'Estado'

    def subtotal_estimado_display(self, obj):
        return f"${obj.subtotal_estimado:,.2f}"
    subtotal_estimado_display.short_description = 'Subtotal Estimado'

    def subtotal_real_display(self, obj):
        return f"${obj.subtotal_real:,.2f}" if obj.costo_real else "-"
    subtotal_real_display.short_description = 'Subtotal Real'


@admin.register(SeguimientoOrden)
class SeguimientoOrdenAdmin(admin.ModelAdmin):
    list_display = [
        'orden_trabajo', 'fecha', 'usuario',
        'estado_anterior', 'estado_nuevo', 'comentario_corto'
    ]
    list_filter = ['fecha', 'estado_anterior', 'estado_nuevo']
    search_fields = ['orden_trabajo__folio', 'comentario', 'usuario__username']
    readonly_fields = ['fecha']
    # Removido autocomplete_fields

    def comentario_corto(self, obj):
        if len(obj.comentario) > 50:
            return obj.comentario[:50] + "..."
        return obj.comentario
    comentario_corto.short_description = 'Comentario'


@admin.register(ChecklistMantenimiento)
class ChecklistMantenimientoAdmin(admin.ModelAdmin):
    list_display = [
        'tipo_mantenimiento', 'descripcion', 'orden',
        'es_obligatorio', 'activo'
    ]
    list_filter = ['tipo_mantenimiento', 'es_obligatorio', 'activo']
    search_fields = ['descripcion']
    ordering = ['tipo_mantenimiento', 'orden']


@admin.register(ChecklistOrden)
class ChecklistOrdenAdmin(admin.ModelAdmin):
    list_display = [
        'orden_trabajo', 'item_checklist', 'estado',
        'fecha_revision', 'revisado_por'
    ]
    list_filter = ['estado', 'fecha_revision']
    search_fields = [
        'orden_trabajo__folio', 'item_checklist__descripcion',
        'observaciones'
    ]
    readonly_fields = ['fecha_revision']
    # Removido autocomplete_fields


@admin.register(HistorialMantenimiento)
class HistorialMantenimientoAdmin(admin.ModelAdmin):
    list_display = [
        'unidad', 'fecha_servicio', 'kilometraje_ingreso', 'kilometraje_salida',
        'tipo_servicio', 'costo_total_display',
        'tiempo_fuera_servicio_dias', 'tiempo_fuera_servicio_horas'
    ]
    list_filter = ['fecha_servicio', 'tipo_servicio']
    search_fields = [
        'unidad__numero_economico', 'unidad__placa', 'orden_trabajo__folio',
        'tipo_servicio', 'descripcion_breve'
    ]
    readonly_fields = ['orden_trabajo', 'kilometros_en_taller_display']
    # Removido autocomplete_fields
    date_hierarchy = 'fecha_servicio'

    fieldsets = (
        ('Información Básica', {
            'fields': ('unidad', 'orden_trabajo', 'fecha_servicio', 'tipo_servicio')
        }),
        ('Kilometraje', {
            'fields': ('kilometraje_ingreso', 'kilometraje_salida', 'kilometros_en_taller_display')
        }),
        ('Costos y Tiempos', {
            'fields': (
                'costo_total', 'tiempo_fuera_servicio_dias',
                'tiempo_fuera_servicio_horas'
            )
        }),
        ('Descripción', {
            'fields': ('descripcion_breve',)
        }),
    )

    def costo_total_display(self, obj):
        return f"${obj.costo_total:,.2f}"
    costo_total_display.short_description = 'Costo Total'

    def kilometros_en_taller_display(self, obj):
        return f"{obj.kilometros_en_taller} km"
    kilometros_en_taller_display.short_description = 'Kms en Taller'