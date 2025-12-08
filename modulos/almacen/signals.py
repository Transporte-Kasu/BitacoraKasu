from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import (
    ProductoAlmacen, ItemEntradaAlmacen, ItemSalidaAlmacen,
    MovimientoAlmacen, AlertaStock
)


@receiver(post_save, sender=ItemEntradaAlmacen)
def actualizar_stock_entrada(sender, instance, created, **kwargs):
    """
    Actualizar el stock del producto cuando se crea un item de entrada.
    También genera el movimiento de almacén correspondiente.
    """
    if created:
        producto = instance.producto_almacen
        cantidad_anterior = producto.cantidad
        
        # Agregar al stock
        producto.agregar_stock(instance.cantidad)
        
        # Crear movimiento de almacén
        MovimientoAlmacen.objects.create(
            tipo='ENTRADA',
            producto_almacen=producto,
            cantidad=instance.cantidad,
            cantidad_anterior=cantidad_anterior,
            cantidad_posterior=producto.cantidad,
            entrada_almacen=instance.entrada,
            usuario=instance.entrada.recibido_por,
            observaciones=f"Entrada desde {instance.entrada.get_tipo_display()}"
        )


@receiver(post_save, sender=ItemSalidaAlmacen)
def actualizar_stock_salida(sender, instance, created, **kwargs):
    """
    Actualizar el stock del producto cuando se crea un item de salida.
    También genera el movimiento de almacén correspondiente.
    """
    if created:
        producto = instance.producto_almacen
        cantidad_anterior = producto.cantidad
        
        # Reducir del stock
        if producto.reducir_stock(instance.cantidad_entregada):
            # Crear movimiento de almacén
            MovimientoAlmacen.objects.create(
                tipo='SALIDA',
                producto_almacen=producto,
                cantidad=-instance.cantidad_entregada,
                cantidad_anterior=cantidad_anterior,
                cantidad_posterior=producto.cantidad,
                salida_almacen=instance.salida,
                usuario=instance.salida.entregado_por,
                observaciones=f"Salida para {instance.salida.solicitud_salida.get_tipo_display()}"
            )
            
            # Actualizar cantidad entregada en el item de solicitud
            item_solicitud = instance.item_solicitud
            item_solicitud.cantidad_entregada += instance.cantidad_entregada
            item_solicitud.save()


@receiver(post_save, sender=ProductoAlmacen)
def verificar_alertas_producto(sender, instance, **kwargs):
    """
    Verificar y generar alertas automáticas para el producto.
    Se ejecuta cada vez que se guarda un ProductoAlmacen.
    """
    # Solo verificar si el producto está activo
    if not instance.activo:
        return
    
    # Verificar stock agotado
    if instance.stock_agotado:
        # Verificar si ya existe una alerta activa de este tipo
        alerta_existente = AlertaStock.objects.filter(
            producto_almacen=instance,
            tipo_alerta='STOCK_AGOTADO',
            resuelta=False
        ).exists()
        
        if not alerta_existente:
            AlertaStock.objects.create(
                producto_almacen=instance,
                tipo_alerta='STOCK_AGOTADO',
                mensaje=f"El producto {instance.sku} - {instance.descripcion} está AGOTADO. Cantidad actual: 0"
            )
    
    # Verificar stock bajo
    elif instance.stock_bajo and instance.stock_minimo > 0:
        # Verificar si ya existe una alerta activa de este tipo
        alerta_existente = AlertaStock.objects.filter(
            producto_almacen=instance,
            tipo_alerta='STOCK_MINIMO',
            resuelta=False
        ).exists()
        
        if not alerta_existente:
            AlertaStock.objects.create(
                producto_almacen=instance,
                tipo_alerta='STOCK_MINIMO',
                mensaje=f"El producto {instance.sku} - {instance.descripcion} está por debajo del stock mínimo. "
                        f"Cantidad actual: {instance.cantidad} {instance.unidad_medida}, "
                        f"Stock mínimo: {instance.stock_minimo} {instance.unidad_medida}"
            )
    else:
        # Si el stock se normalizó, resolver alertas de stock
        AlertaStock.objects.filter(
            producto_almacen=instance,
            tipo_alerta__in=['STOCK_AGOTADO', 'STOCK_MINIMO'],
            resuelta=False
        ).update(resuelta=True, fecha_resolucion=timezone.now())
    
    # Verificar caducidad
    if instance.tiene_caducidad and instance.fecha_caducidad:
        # Verificar si está caducado
        if instance.caducado:
            alerta_existente = AlertaStock.objects.filter(
                producto_almacen=instance,
                tipo_alerta='CADUCADO',
                resuelta=False
            ).exists()
            
            if not alerta_existente:
                AlertaStock.objects.create(
                    producto_almacen=instance,
                    tipo_alerta='CADUCADO',
                    mensaje=f"El producto {instance.sku} - {instance.descripcion} ha CADUCADO. "
                            f"Fecha de caducidad: {instance.fecha_caducidad.strftime('%d/%m/%Y')}"
                )
        
        # Verificar si está próximo a caducar
        elif instance.proximo_caducar:
            alerta_existente = AlertaStock.objects.filter(
                producto_almacen=instance,
                tipo_alerta='PROXIMO_CADUCAR',
                resuelta=False
            ).exists()
            
            if not alerta_existente:
                dias_restantes = (instance.fecha_caducidad - timezone.now().date()).days
                AlertaStock.objects.create(
                    producto_almacen=instance,
                    tipo_alerta='PROXIMO_CADUCAR',
                    mensaje=f"El producto {instance.sku} - {instance.descripcion} está próximo a caducar. "
                            f"Fecha de caducidad: {instance.fecha_caducidad.strftime('%d/%m/%Y')} "
                            f"({dias_restantes} días restantes)"
                )


@receiver(post_save, sender='almacen.SalidaAlmacen')
def actualizar_estado_solicitud(sender, instance, created, **kwargs):
    """
    Actualizar el estado de la solicitud cuando se procesa la salida.
    """
    if created:
        solicitud = instance.solicitud_salida
        
        # Verificar si todos los items fueron entregados completamente
        todos_completos = all(
            item.entrega_completa for item in solicitud.items.all()
        )
        
        if todos_completos:
            solicitud.estado = 'ENTREGADA'
            solicitud.save()
