from django.contrib import admin
from .models import Equipo


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ['numero_economico', 'tipo', 'placas', 'marca', 'color', 'vigencia_doble_articulado', 'verificacion', 'activo']
    list_filter = ['tipo', 'marca', 'activo', 'verificacion']
    search_fields = ['numero_economico', 'placas', 'numero_serie', 'marca']
    list_editable = ['activo', 'verificacion']
    readonly_fields = ['slug', 'fecha_registro', 'fecha_actualizacion']
    ordering = ['numero_economico']
