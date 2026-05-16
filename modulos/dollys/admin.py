from django.contrib import admin
from .models import Dolly


@admin.register(Dolly)
class DollyAdmin(admin.ModelAdmin):
    list_display = ['numero_economico', 'marca', 'color', 'numero_serie', 'activo']
    list_filter = ['marca', 'activo']
    search_fields = ['numero_economico', 'numero_serie', 'marca']
    list_editable = ['activo']
    readonly_fields = ['slug', 'fecha_registro', 'fecha_actualizacion']
    ordering = ['numero_economico']
