from django.contrib import admin
from django.utils.html import format_html
from .models import BitacoraViaje


@admin.register(BitacoraViaje)
class BitacoraViajeAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'operador', 'unidad', 'modalidad_badge', 'destino_corto',
        'fecha_salida', 'completado_badge', 'kilometros_recorridos_display',
        'rendimiento_badge', 'alerta_display'
    ]
    list_filter = [
        'modalidad', 'completado', 'fecha_salida', 'reparto',
        'operador', 'unidad__tipo'
    ]
    search_fields = [
        'operador__nombre', 'unidad__numero_economico', 'unidad__placa',
        'contenedor', 'destino', 'cp_destino'
    ]
    readonly_fields = [
        'created_at', 'updated_at',
        'kilometros_recorridos_display', 'rendimiento_combustible_display',
        'horas_viaje_display', 'velocidad_promedio_display',
        'eficiencia_vs_esperado_display', 'diferencia_distancias_display'
    ]
    date_hierarchy = 'fecha_salida'
    ordering = ['-fecha_salida']
    
    fieldsets = (
        ('Asignación', {
            'fields': ('operador', 'unidad')
        }),
        ('Información del Viaje', {
            'fields': (
                'modalidad', 'contenedor', 'peso', 'reparto',
                'fecha_carga', 'fecha_salida', 'fecha_llegada', 'completado'
            )
        }),
        ('Ubicación', {
            'fields': ('cp_origen', 'cp_destino', 'destino')
        }),
        ('Combustible y Kilometraje', {
            'fields': (
                'diesel_cargado', 'kilometraje_salida', 'kilometraje_llegada',
                'kilometros_recorridos_display', 'rendimiento_combustible_display'
            )
        }),
        ('Datos Google Maps', {
            'fields': (
                'distancia_calculada', 'duracion_estimada',
                'diferencia_distancias_display'
            ),
            'classes': ('collapse',)
        }),
        ('Métricas de Rendimiento', {
            'fields': (
                'horas_viaje_display', 'velocidad_promedio_display',
                'eficiencia_vs_esperado_display'
            ),
            'classes': ('collapse',)
        }),
        ('Seguridad', {
            'fields': ('sellos',)
        }),
        ('Observaciones', {
            'fields': ('observaciones',)
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def modalidad_badge(self, obj):
        """Badge con la modalidad"""
        colors = {
            'SENCILLO': '#3b82f6',
            'FULL': '#8b5cf6',
        }
        color = colors.get(obj.modalidad, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color, obj.get_modalidad_display()
        )
    modalidad_badge.short_description = 'Modalidad'
    
    def completado_badge(self, obj):
        """Badge de estado completado"""
        if obj.completado:
            return format_html(
                '<span style="background-color: #10b981; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">✓ Completado</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #fbbf24; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">⌛ En curso</span>'
            )
    completado_badge.short_description = 'Estado'
    
    def destino_corto(self, obj):
        """Muestra el destino truncado"""
        if len(obj.destino) > 50:
            return obj.destino[:50] + '...'
        return obj.destino
    destino_corto.short_description = 'Destino'
    
    def kilometros_recorridos_display(self, obj):
        """Muestra los kilómetros recorridos"""
        km = obj.kilometros_recorridos
        if km > 0:
            return f"{km:,} km"
        return "Pendiente"
    kilometros_recorridos_display.short_description = 'Kms Recorridos'
    
    def rendimiento_badge(self, obj):
        """Badge con el rendimiento de combustible"""
        rendimiento = obj.rendimiento_combustible
        if rendimiento > 0:
            if rendimiento >= 3.0:
                color = '#10b981'  # Verde - Excelente
            elif rendimiento >= 2.5:
                color = '#3b82f6'  # Azul - Bueno
            elif rendimiento >= 2.0:
                color = '#fbbf24'  # Amarillo - Regular
            else:
                color = '#ef4444'  # Rojo - Bajo
            
            return format_html(
                '<span style="background-color: {}; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">{:.2f} km/lt</span>',
                color, rendimiento
            )
        return format_html('<span style="color: #6b7280;">-</span>')
    rendimiento_badge.short_description = 'Rendimiento'
    
    def alerta_display(self, obj):
        """Muestra alerta si hay bajo rendimiento"""
        if obj.alerta_bajo_rendimiento:
            return format_html(
                '<span style="background-color: #ef4444; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">⚠ Bajo</span>'
            )
        return format_html('<span style="color: #10b981; font-weight: bold;">✓</span>')
    alerta_display.short_description = 'Alerta'
    
    def rendimiento_combustible_display(self, obj):
        """Muestra el rendimiento de combustible"""
        rendimiento = obj.rendimiento_combustible
        return f"{rendimiento:.2f} km/lt" if rendimiento > 0 else "Sin datos"
    rendimiento_combustible_display.short_description = 'Rendimiento'
    
    def horas_viaje_display(self, obj):
        """Muestra las horas de viaje"""
        horas = obj.horas_viaje
        return f"{horas:.2f} horas" if horas > 0 else "Sin datos"
    horas_viaje_display.short_description = 'Horas de Viaje'
    
    def velocidad_promedio_display(self, obj):
        """Muestra la velocidad promedio"""
        velocidad = obj.velocidad_promedio
        return f"{velocidad:.2f} km/h" if velocidad > 0 else "Sin datos"
    velocidad_promedio_display.short_description = 'Velocidad Promedio'
    
    def eficiencia_vs_esperado_display(self, obj):
        """Muestra la eficiencia vs esperado"""
        eficiencia = obj.eficiencia_vs_esperado
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
    eficiencia_vs_esperado_display.short_description = 'Eficiencia vs Esperado'
    
    def diferencia_distancias_display(self, obj):
        """Muestra la diferencia entre distancia real y calculada"""
        diferencia = obj.diferencia_distancias
        if diferencia is not None:
            color = '#ef4444' if abs(diferencia) > 50 else '#10b981'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:+.2f} km</span>',
                color, diferencia
            )
        return "Sin datos"
    diferencia_distancias_display.short_description = 'Diferencia Distancias'
    
    actions = ['marcar_completados', 'calcular_distancias_google']
    
    def marcar_completados(self, request, queryset):
        """Marca los viajes seleccionados como completados"""
        count = 0
        for viaje in queryset:
            if not viaje.completado and viaje.fecha_llegada and viaje.kilometraje_llegada:
                viaje.completado = True
                viaje.save()
                count += 1
        
        self.message_user(
            request,
            f'{count} viajes marcados como completados. {queryset.count() - count} viajes no se pudieron completar (falta fecha de llegada o kilometraje).'
        )
    marcar_completados.short_description = 'Marcar como completados'
    
    def calcular_distancias_google(self, request, queryset):
        """Calcula distancias usando Google Maps API"""
        count_success = 0
        count_error = 0
        
        for viaje in queryset:
            if viaje.cp_destino:
                resultado = viaje.calcular_distancia_google()
                if resultado['status'] == 'success':
                    count_success += 1
                else:
                    count_error += 1
            else:
                count_error += 1
        
        if count_success > 0:
            self.message_user(
                request,
                f'{count_success} distancias calculadas exitosamente. {count_error} viajes con errores.'
            )
        else:
            self.message_user(
                request,
                f'No se pudieron calcular las distancias. Asegúrese de que los viajes tengan código postal de destino.',
                level='warning'
            )
    calcular_distancias_google.short_description = 'Calcular distancias (Google Maps)'
    
    def get_queryset(self, request):
        """Optimiza las consultas"""
        qs = super().get_queryset(request)
        return qs.select_related('operador', 'unidad')
