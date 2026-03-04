from django.contrib import admin
from .models import ConfiguracionReporte, ReporteGenerado


@admin.register(ConfiguracionReporte)
class ConfiguracionReporteAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'modulo', 'tipo_reporte', 'frecuencia', 'activo', 'ultimo_envio', 'creado_por']
    list_filter = ['modulo', 'frecuencia', 'activo']
    search_fields = ['nombre', 'destinatarios']
    readonly_fields = ['ultimo_envio', 'fecha_creacion']

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(ReporteGenerado)
class ReporteGeneradoAdmin(admin.ModelAdmin):
    list_display = ['configuracion', 'fecha_generacion', 'periodo_inicio', 'periodo_fin', 'estado']
    list_filter = ['estado', 'configuracion__modulo']
    readonly_fields = [
        'configuracion', 'fecha_generacion', 'periodo_inicio', 'periodo_fin',
        'estado', 'destinatarios_enviados', 'resumen', 'mensaje_error',
    ]
    date_hierarchy = 'fecha_generacion'

    def has_add_permission(self, request):
        return False
