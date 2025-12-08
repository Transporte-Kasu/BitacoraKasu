from django.contrib import admin
from django.utils.html import format_html
from .models import Operador


@admin.register(Operador)
class OperadorAdmin(admin.ModelAdmin):
    list_display = [
        'nombre', 'tipo_badge', 'unidad_asignada', 'telefono',
        'activo_badge', 'viajes_completados_display', 'fecha_ingreso'
    ]
    list_filter = ['tipo', 'activo', 'fecha_ingreso']
    search_fields = ['nombre', 'licencia', 'telefono', 'email']
    readonly_fields = ['fecha_ingreso', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Información Personal', {
            'fields': ('nombre', 'tipo', 'telefono', 'email')
        }),
        ('Documentación', {
            'fields': ('licencia',)
        }),
        ('Asignación', {
            'fields': ('unidad_asignada',)
        }),
        ('Estado', {
            'fields': ('activo', 'fecha_ingreso', 'fecha_baja')
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
        """Badge con el tipo de operador"""
        colors = {
            'LOCAL': '#3b82f6',
            'FORANEO': '#8b5cf6',
            'ESPERANZA': '#10b981',
        }
        color = colors.get(obj.tipo, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color, obj.get_tipo_display()
        )
    tipo_badge.short_description = 'Tipo'
    
    def activo_badge(self, obj):
        """Badge de estado activo/inactivo"""
        if obj.activo:
            return format_html(
                '<span style="background-color: #10b981; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">✓ Activo</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #ef4444; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">✗ Inactivo</span>'
            )
    activo_badge.short_description = 'Estado'
    
    def viajes_completados_display(self, obj):
        """Muestra el número de viajes completados"""
        count = obj.viajes_completados()
        return format_html(
            '<span style="background: #3b82f6; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-weight: bold;">{}</span>',
            count
        )
    viajes_completados_display.short_description = 'Viajes'
    
    actions = ['activar_operadores', 'desactivar_operadores']
    
    def activar_operadores(self, request, queryset):
        """Activa los operadores seleccionados"""
        updated = queryset.update(activo=True, fecha_baja=None)
        self.message_user(request, f'{updated} operadores activados.')
    activar_operadores.short_description = 'Activar operadores seleccionados'
    
    def desactivar_operadores(self, request, queryset):
        """Desactiva los operadores seleccionados"""
        from django.utils import timezone
        updated = queryset.update(activo=False, fecha_baja=timezone.now().date())
        self.message_user(request, f'{updated} operadores desactivados.')
    desactivar_operadores.short_description = 'Desactivar operadores seleccionados'
    
    def get_queryset(self, request):
        """Optimiza las consultas"""
        qs = super().get_queryset(request)
        return qs.select_related('unidad_asignada')
