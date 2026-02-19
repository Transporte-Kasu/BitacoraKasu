from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import CargaCombustible, AlertaCombustible


@receiver(post_save, sender=CargaCombustible)
def generar_alertas_combustible(sender, instance, created, **kwargs):
    """Genera alertas automáticas al completar una carga de combustible"""
    if instance.estado != 'COMPLETADO':
        return

    # Alerta por estado del candado
    _tipo_candado = {
        'ALTERADO': 'CANDADO_ALTERADO',
        'VIOLADO': 'CANDADO_VIOLADO',
        'SIN_CANDADO': 'SIN_CANDADO',
    }
    tipo = _tipo_candado.get(instance.estado_candado_anterior)
    if tipo:
        AlertaCombustible.objects.get_or_create(
            carga=instance,
            tipo_alerta=tipo,
            defaults={
                'mensaje': (
                    f"Unidad {instance.unidad.numero_economico}: candado registrado como "
                    f"'{instance.get_estado_candado_anterior_display()}' en la carga del "
                    f"{instance.fecha_hora_inicio.strftime('%d/%m/%Y %H:%M')}. "
                    f"Despachador: {instance.despachador.nombre}."
                )
            }
        )

    # Alerta por exceso de combustible respecto a la capacidad del tanque
    if (instance.unidad.capacidad_combustible and
            instance.cantidad_litros > instance.unidad.capacidad_combustible):
        AlertaCombustible.objects.get_or_create(
            carga=instance,
            tipo_alerta='EXCESO_COMBUSTIBLE',
            defaults={
                'mensaje': (
                    f"Unidad {instance.unidad.numero_economico}: se cargaron "
                    f"{instance.cantidad_litros} L pero la capacidad del tanque es "
                    f"{instance.unidad.capacidad_combustible} L "
                    f"(exceso: {instance.cantidad_litros - instance.unidad.capacidad_combustible} L). "
                    f"Despachador: {instance.despachador.nombre}."
                )
            }
        )
