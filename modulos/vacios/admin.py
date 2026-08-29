from django.contrib import admin

from .models import CambioOperadorVacio, Naviera, RetrasoVacio, Vacio


class RetrasoVacioInline(admin.TabularInline):
    model = RetrasoVacio
    extra = 0
    readonly_fields = ('notificado_agencia', 'fecha_notificacion', 'created_at')


class CambioOperadorVacioInline(admin.TabularInline):
    model = CambioOperadorVacio
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Naviera)
class NavieraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'created_at')
    list_filter = ('activo',)
    search_fields = ('nombre',)


@admin.register(Vacio)
class VacioAdmin(admin.ModelAdmin):
    list_display = (
        'folio', 'contenedor', 'cliente', 'estado', 'operador', 'unidad',
        'naviera', 'tiene_retraso', 'fecha_entrega_cliente',
    )
    list_filter = ('estado', 'naviera', 'tiene_retraso', 'tipo_contenedor')
    search_fields = ('folio', 'contenedor')
    readonly_fields = (
        'folio', 'fecha_entrega_cliente', 'fecha_retorno_patio',
        'fecha_asignacion', 'fecha_salida_naviera', 'fecha_entrega_naviera',
        'created_at', 'updated_at',
    )
    autocomplete_fields = ('bitacora_viaje', 'cliente', 'operador', 'unidad', 'naviera', 'agencia')
    inlines = (RetrasoVacioInline, CambioOperadorVacioInline)


@admin.register(RetrasoVacio)
class RetrasoVacioAdmin(admin.ModelAdmin):
    list_display = ('vacio', 'tipo', 'fecha_estimada_nueva', 'notificado_agencia', 'created_at')
    list_filter = ('tipo', 'notificado_agencia')


@admin.register(CambioOperadorVacio)
class CambioOperadorVacioAdmin(admin.ModelAdmin):
    list_display = ('vacio', 'causa', 'operador_saliente', 'operador_entrante', 'created_at')
    list_filter = ('causa',)
