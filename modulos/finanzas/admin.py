from django.contrib import admin

from .models import TarifaKilometro, RecepcionPipa, PrecioDieselMensual


@admin.register(TarifaKilometro)
class TarifaKilometroAdmin(admin.ModelAdmin):
    list_display = ['valor', 'vigente_desde', 'activo']
    list_filter = ['activo']
    ordering = ['-vigente_desde']


@admin.register(RecepcionPipa)
class RecepcionPipaAdmin(admin.ModelAdmin):
    list_display = ['fecha', 'litros', 'costo_total', 'precio_litro', 'proveedor']
    list_filter = ['fecha']
    search_fields = ['proveedor', 'notas']
    ordering = ['-fecha']

    def precio_litro(self, obj):
        return f"${obj.precio_litro:.2f}" if obj.precio_litro is not None else '—'
    precio_litro.short_description = 'Precio/L'


@admin.register(PrecioDieselMensual)
class PrecioDieselMensualAdmin(admin.ModelAdmin):
    list_display = ['mes', 'anio', 'litros_totales', 'costo_total', 'precio_promedio_litro', 'actualizado_en']
    list_filter = ['anio']
    ordering = ['-anio', '-mes']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
