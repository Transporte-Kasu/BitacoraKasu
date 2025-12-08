from modulos.taller.models import CategoriaFalla

categorias = [
    {'nombre': 'Motor', 'prioridad_default': 'ALTA'},
    {'nombre': 'Transmisión', 'prioridad_default': 'ALTA'},
    {'nombre': 'Frenos', 'prioridad_default': 'CRITICA'},
    {'nombre': 'Suspensión', 'prioridad_default': 'MEDIA'},
    {'nombre': 'Sistema Eléctrico', 'prioridad_default': 'MEDIA'},
    {'nombre': 'Sistema de Enfriamiento', 'prioridad_default': 'ALTA'},
    {'nombre': 'Neumáticos', 'prioridad_default': 'MEDIA'},
    {'nombre': 'Sistema de Escape', 'prioridad_default': 'BAJA'},
    {'nombre': 'Carrocería', 'prioridad_default': 'BAJA'},
    {'nombre': 'Sistema de Combustible', 'prioridad_default': 'ALTA'},
    {'nombre': 'Dirección', 'prioridad_default': 'ALTA'},
    {'nombre': 'Clutch/Embrague', 'prioridad_default': 'MEDIA'},
]

for cat_data in categorias:
    CategoriaFalla.objects.get_or_create(
        nombre=cat_data['nombre'],
        defaults=cat_data
    )
print("✓ Categorías de falla creadas")