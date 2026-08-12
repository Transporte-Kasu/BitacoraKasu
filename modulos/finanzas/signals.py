from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from .models import RecepcionPipa, PrecioDieselMensual


@receiver(pre_save, sender=RecepcionPipa)
def guardar_fecha_anterior(sender, instance, **kwargs):
    if not instance.pk:
        instance._fecha_anterior = None
        return
    try:
        instance._fecha_anterior = RecepcionPipa.objects.get(pk=instance.pk).fecha
    except RecepcionPipa.DoesNotExist:
        instance._fecha_anterior = None


@receiver(post_save, sender=RecepcionPipa)
def recalcular_precio_mensual_al_guardar(sender, instance, **kwargs):
    PrecioDieselMensual.recalcular(instance.fecha.year, instance.fecha.month)

    fecha_anterior = getattr(instance, '_fecha_anterior', None)
    if fecha_anterior and (fecha_anterior.year, fecha_anterior.month) != (instance.fecha.year, instance.fecha.month):
        PrecioDieselMensual.recalcular(fecha_anterior.year, fecha_anterior.month)


@receiver(post_delete, sender=RecepcionPipa)
def recalcular_precio_mensual_al_borrar(sender, instance, **kwargs):
    PrecioDieselMensual.recalcular(instance.fecha.year, instance.fecha.month)
