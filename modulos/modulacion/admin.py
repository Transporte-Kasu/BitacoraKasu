from django.contrib import admin

from .models import Agencia, Modulacion, TerminalPortuaria


@admin.register(Agencia)
class AgenciaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'activo', 'created_at']
    list_filter = ['activo']
    search_fields = ['nombre']


@admin.register(TerminalPortuaria)
class TerminalPortuariaAdmin(admin.ModelAdmin):
    list_display = [
        'nombre', 'activo', 'requiere_datos_extra',
        'requiere_carril', 'requiere_hora_ingreso', 'requiere_hora_carga', 'created_at',
    ]
    list_filter = ['activo', 'requiere_datos_extra']
    search_fields = ['nombre']


@admin.register(Modulacion)
class ModulacionAdmin(admin.ModelAdmin):
    list_display = [
        'folio', 'contenedor', 'agencia', 'terminal_portuaria',
        'tipo_contenedor', 'cliente', 'unidad', 'operador', 'origen', 'estado', 'fecha_recepcion',
    ]
    list_filter = ['estado', 'origen', 'agencia', 'terminal_portuaria', 'operador']
    search_fields = ['folio', 'contenedor', 'num_pedimento', 'num_doda', 'cliente__nombre']
    autocomplete_fields = ['operador', 'unidad']
    readonly_fields = ['folio', 'fecha_recepcion', 'fecha_patio_esperanza', 'created_at', 'updated_at']
    date_hierarchy = 'fecha_recepcion'
    ordering = ['-fecha_recepcion']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            'agencia', 'terminal_portuaria', 'cliente', 'bitacora_viaje', 'unidad', 'operador',
        )
