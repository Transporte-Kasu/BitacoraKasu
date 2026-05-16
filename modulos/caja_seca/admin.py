from django.contrib import admin
from .models import CajaSeca


@admin.register(CajaSeca)
class CajaSecaAdmin(admin.ModelAdmin):
    list_display = ['numero_economico', 'placas', 'marca', 'modelo', 'anio', 'color', 'activo']
    list_filter = ['marca', 'activo']
    search_fields = ['numero_economico', 'placas', 'numero_serie', 'marca']
    list_editable = ['activo']
    readonly_fields = ['slug', 'fecha_registro', 'fecha_actualizacion']
    ordering = ['numero_economico']
