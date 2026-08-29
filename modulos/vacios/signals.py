"""Creación automática de Vacío al registrarse la entrega de un contenedor."""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from modulos.bitacoras.models import BitacoraViaje

from .models import Vacio

logger = logging.getLogger(__name__)


def _agencia_de(bitacora):
    """Agencia ligada vía Modulación (OneToOne inverso), o None."""
    try:
        return bitacora.modulacion.agencia
    except Exception:
        return None


@receiver(post_save, sender=BitacoraViaje)
def crear_vacios_por_entrega(sender, instance, **kwargs):
    """
    Por cada contenedor del viaje con fecha de entrega registrada y sin Vacío
    aún, crea el Vacío. Solo crea: nunca borra ni revierte.
    """
    agencia = _agencia_de(instance)

    contenedores = [
        ('1', instance.fecha_hora_entrega, instance.contenedor, instance.cliente),
        ('2', instance.fecha_hora_entrega_2, instance.contenedor_2,
         instance.cliente_2 or instance.cliente),
    ]

    for numero, fecha_entrega, contenedor, cliente in contenedores:
        if not fecha_entrega:
            continue
        vacio, creado = Vacio.objects.get_or_create(
            bitacora_viaje=instance,
            numero_contenedor=numero,
            defaults={
                'contenedor': contenedor or '',
                'cliente': cliente,
                'tipo_contenedor': instance.tipo_contenedor or '40',
                'agencia': agencia,
                'fecha_entrega_cliente': fecha_entrega,
                'estado': 'POR_VACIAR',
            },
        )
        if creado:
            logger.info('Vacío %s creado desde bitácora #%s (contenedor %s)',
                        vacio.folio, instance.pk, numero)
