from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Unidad


@admin.register(Unidad)
class UnidadAdmin(admin.ModelAdmin):
    list_display = [
        'numero_economico', 'placa', 'tipo_badge', 'marca', 'modelo', 'año',
        'kilometraje_actual', 'activa_badge', 'mantenimiento_status',
        'viajes_completados_display'
    ]
    list_filter = ['tipo', 'activa', 'marca', 'año']
    search_fields = ['numero_economico', 'placa', 'marca', 'modelo']
    readonly_fields = [
        'fecha_alta', 'created_at', 'updated_at',
        'rendimiento_promedio_real_display', 'eficiencia_combustible_display'
    ]
    
    fieldsets = (
        ('Identificación', {
            'fields': ('numero_economico', 'placa', 'tipo')
        }),
        ('Especificaciones Técnicas', {
            'fields': ('marca', 'modelo', 'año', 'capacidad_combustible', 'rendimiento_esperado')
        }),
        ('Kilometraje', {
            'fields': (
                'kilometraje_actual',
                'rendimiento_promedio_real_display',
                'eficiencia_combustible_display'
            )
        }),
        ('Mantenimiento', {
            'fields': ('ultimo_mantenimiento', 'proximo_mantenimiento')
        }),
        ('Estado', {
            'fields': ('activa', 'fecha_alta', 'fecha_baja')
        }),
        ('Notas', {
            'fields': ('notas',)
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def tipo_badge(self, obj):
        """Badge con el tipo de unidad"""
        colors = {
            'LOCAL': '#3b82f6',
            'FORANEA': '#8b5cf6',
            'ESPERANZA': '#10b981',
        }
        color = colors.get(obj.tipo, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color, obj.get_tipo_display()
        )
    tipo_badge.short_description = 'Tipo'
    
    def activa_badge(self, obj):
        """Badge de estado activo/inactivo"""
        if obj.activa:
            return format_html(
                '<span style="background-color: #10b981; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">✓ Activa</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #ef4444; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">✗ Inactiva</span>'
            )
    activa_badge.short_description = 'Estado'
    
    def mantenimiento_status(self, obj):
        """Muestra el estado del mantenimiento"""
        if obj.requiere_mantenimiento():
            return format_html(
                '<span style="background-color: #ef4444; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">⚠ Requiere</span>'
            )
        elif obj.proximo_mantenimiento:
            dias_restantes = (obj.proximo_mantenimiento - timezone.now().date()).days
            if dias_restantes <= 7:
                color = '#fbbf24'  # Amarillo
                texto = f'{dias_restantes} días'
            else:
                color = '#10b981'  # Verde
                texto = f'{dias_restantes} días'
            return format_html(
                '<span style="background-color: {}; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">{}</span>',
                color, texto
            )
        return format_html('<span style="color: #6b7280;">Sin programar</span>')
    mantenimiento_status.short_description = 'Mantenimiento'
    
    def viajes_completados_display(self, obj):
        """Muestra el número de viajes completados"""
        count = obj.viajes_completados()
        return format_html(
            '<span style="background: #3b82f6; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-weight: bold;">{}</span>',
            count
        )
    viajes_completados_display.short_description = 'Viajes'
    
    def rendimiento_promedio_real_display(self, obj):
        """Muestra el rendimiento promedio real"""
        rendimiento = obj.rendimiento_promedio_real()
        if rendimiento > 0:
            return f"{rendimiento} km/lt"
        return "Sin datos"
    rendimiento_promedio_real_display.short_description = 'Rendimiento Real'
    
    def eficiencia_combustible_display(self, obj):
        """Muestra la eficiencia de combustible"""
        eficiencia = obj.eficiencia_combustible()
        if eficiencia > 0:
            if eficiencia >= 90:
                color = '#10b981'
            elif eficiencia >= 70:
                color = '#fbbf24'
            else:
                color = '#ef4444'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
                color, eficiencia
            )
        return "Sin datos"
    eficiencia_combustible_display.short_description = 'Eficiencia'
    
    actions = ['activar_unidades', 'desactivar_unidades']
    
    def activar_unidades(self, request, queryset):
        """Activa las unidades seleccionadas"""
        updated = queryset.update(activa=True, fecha_baja=None)
        self.message_user(request, f'{updated} unidades activadas.')
    activar_unidades.short_description = 'Activar unidades seleccionadas'
    
    def desactivar_unidades(self, request, queryset):
        """Desactiva las unidades seleccionadas"""
        updated = queryset.update(activa=False, fecha_baja=timezone.now().date())
        self.message_user(request, f'{updated} unidades desactivadas.')
    desactivar_unidades.short_description = 'Desactivar unidades seleccionadas'
