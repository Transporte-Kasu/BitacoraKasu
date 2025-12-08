from modulos.taller.models import TipoMantenimiento

tipos = [
    {
        'nombre': 'Servicio A (Menor)',
        'tipo': 'PREVENTIVO',
        'descripcion': 'Servicio de mantenimiento básico',
        'kilometraje_sugerido': 10000,
        'dias_sugeridos': 90
    },
    {
        'nombre': 'Servicio B (Mayor)',
        'tipo': 'PREVENTIVO',
        'descripcion': 'Servicio de mantenimiento completo',
        'kilometraje_sugerido': 40000,
        'dias_sugeridos': 180
    },
    {
        'nombre': 'Servicio C (Integral)',
        'tipo': 'PREVENTIVO',
        'descripcion': 'Servicio de mantenimiento integral',
        'kilometraje_sugerido': 80000,
        'dias_sugeridos': 365
    },
    {
        'nombre': 'Reparación Correctiva',
        'tipo': 'CORRECTIVO',
        'descripcion': 'Reparación por falla o daño',
        'kilometraje_sugerido': None,
        'dias_sugeridos': None
    },
    {
        'nombre': 'Diagnóstico Predictivo',
        'tipo': 'PREDICTIVO',
        'descripcion': 'Análisis predictivo con sensores',
        'kilometraje_sugerido': None,
        'dias_sugeridos': 30
    },
]

for tipo_data in tipos:
    TipoMantenimiento.objects.get_or_create(
        nombre=tipo_data['nombre'],
        defaults=tipo_data
    )
print("✓ Tipos de mantenimiento creados")