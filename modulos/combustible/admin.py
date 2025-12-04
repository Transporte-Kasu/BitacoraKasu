from django.contrib import admin
from django.utils.html import format_html
from .models import Despachador, CargaCombustible


@admin.register(Despachador)
class DespachadorAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'telefono', 'activo', 'total_cargas', 'created_at']
    list_filter = ['activo', 'created_at']
    search_fields = ['nombre', 'telefono']
    ordering = ['nombre']

    fieldsets = (
        ('Información Personal', {
            'fields': ('nombre', 'telefono')
        }),
        ('Estado', {
            'fields': ('activo',)
        }),
    )

    def total_cargas(self, obj):
        """Muestra el total de cargas realizadas"""
        count = obj.cargas.count()
        return format_html(
            '<span style="background: #3b82f6; color: white; padding: 2px 8px; border-radius: 4px;">{}</span>',
            count
        )
    total_cargas.short_description = 'Total cargas'


@admin.register(CargaCombustible)
class CargaCombustibleAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'unidad_info', 'despachador', 'cantidad_litros',
        'estado_badge', 'alerta_badge', 'fecha_hora_inicio', 'tiempo_carga'
    ]
    list_filter = [
        'estado', 'estado_candado_anterior', 'nivel_combustible_inicial',
        'fecha_hora_inicio', 'unidad__tipo'
    ]
    search_fields = [
        'unidad__numero_economico', 'unidad__placa',
        'despachador__nombre', 'notas'
    ]
    readonly_fields = [
        'tiempo_carga_minutos', 'created_at', 'updated_at',
        'preview_fotos'
    ]
    date_hierarchy = 'fecha_hora_inicio'
    ordering = ['-fecha_hora_inicio']

    fieldsets = (
        ('Información Principal', {
            'fields': ('despachador', 'unidad', 'estado')
        }),
        ('Datos de Carga', {
            'fields': ('cantidad_litros', 'fecha_hora_inicio', 'fecha_hora_fin', 'tiempo_carga_minutos')
        }),
        ('Datos del Tablero', {
            'fields': ('kilometraje_actual', 'nivel_combustible_inicial')
        }),
        ('Estado del Candado', {
            'fields': ('estado_candado_anterior', 'observaciones_candado')
        }),
        ('Fotografías', {
            'fields': (
                'foto_numero_economico', 'foto_tablero', 'foto_candado_anterior',
                'foto_candado_nuevo', 'foto_ticket', 'preview_fotos'
            ),
            'classes': ('collapse',)
        }),
        ('Notas', {
            'fields': ('notas',)
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def unidad_info(self, obj):
        """Muestra información de la unidad"""
        return format_html(
            '<strong>{}</strong><br><small style="color: #666;">{}</small>',
            obj.unidad.numero_economico,
            obj.unidad.placa
        )
    unidad_info.short_description = 'Unidad'

    def estado_badge(self, obj):
        """Badge con el estado de la carga"""
        colors = {
            'INICIADO': '#6b7280',
            'EN_PROCESO': '#8b5cf6',
            'COMPLETADO': '#10b981',
            'CANCELADO': '#ef4444',
        }
        color = colors.get(obj.estado, '#6b7280')
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_estado_display()
        )
    estado_badge.short_description = 'Estado'

    def alerta_badge(self, obj):
        """Badge de alerta si hay problemas con el candado"""
        if obj.tiene_alertas():
            return format_html(
                '<span style="background: #ef4444; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px;">⚠️ {}</span>',
                obj.get_estado_candado_anterior_display()
            )
        return format_html(
            '<span style="color: #10b981; font-weight: bold;">✓ Normal</span>'
        )
    alerta_badge.short_description = 'Candado'

    def tiempo_carga(self, obj):
        """Muestra el tiempo de carga formateado"""
        if obj.tiempo_carga_minutos:
            return format_html(
                '<span style="background: #8b5cf6; color: white; padding: 2px 8px; border-radius: 4px;">{} min</span>',
                obj.tiempo_carga_minutos
            )
        return '-'
    tiempo_carga.short_description = 'Tiempo'

    def preview_fotos(self, obj):
        """Muestra previews de todas las fotos"""
        html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px;">'

        fotos = [
            ('Número Económico', obj.foto_numero_economico),
            ('Tablero', obj.foto_tablero),
            ('Candado Anterior', obj.foto_candado_anterior),
            ('Candado Nuevo', obj.foto_candado_nuevo),
            ('Ticket', obj.foto_ticket),
        ]

        for nombre, foto in fotos:
            if foto:
                html += f'''
                <div style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px;">
                    <p style="font-weight: bold; font-size: 12px; margin-bottom: 5px;">{nombre}</p>
                    <a href="{foto.url}" target="_blank">
                        <img src="{foto.url}" style="width: 100%; height: 120px; object-fit: cover; border-radius: 4px;">
                    </a>
                </div>
                '''

        html += '</div>'
        return format_html(html)
    preview_fotos.short_description = 'Vista previa de fotografías'

    def get_queryset(self, request):
        """Optimiza las consultas"""
        qs = super().get_queryset(request)
        return qs.select_related('despachador', 'unidad')

    actions = ['marcar_completado', 'exportar_reporte']

    def marcar_completado(self, request, queryset):
        """Acción para marcar cargas como completadas"""
        updated = queryset.update(estado='COMPLETADO')
        self.message_user(request, f'{updated} cargas marcadas como completadas.')
    marcar_completado.short_description = 'Marcar como completadas'

    def exportar_reporte(self, request, queryset):
        """Acción para exportar reporte (placeholder)"""
        self.message_user(request, 'Función de exportación en desarrollo.')
    exportar_reporte.short_description = 'Exportar reporte'