from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User

from .models import OrdenTrabajo, PiezaRequerida, SeguimientoOrden
from modulos.compras.models import RecepcionAlmacen, ItemRecepcion


@receiver(post_save, sender=OrdenTrabajo)
def notificar_nueva_orden(sender, instance, created, **kwargs):
    """Notificar cuando se crea una nueva orden de trabajo"""
    if created:
        # Notificar al supervisor/jefe de taller
        supervisores = User.objects.filter(
            groups__name='Supervisores Taller'
        )

        if supervisores.exists():
            send_mail(
                subject=f'Nueva Orden de Trabajo: {instance.folio}',
                message=f'''
                Se ha creado una nueva orden de trabajo:

                Folio: {instance.folio}
                Unidad: {instance.unidad.numero_economico} - {instance.unidad.placa}
                Prioridad: {instance.get_prioridad_display()}
                Problema: {instance.descripcion_problema}
                Kilometraje: {instance.kilometraje_ingreso:,} km

                Por favor revise y asigne un mecánico.
                ''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[s.email for s in supervisores if s.email],
                fail_silently=True,
            )


@receiver(post_save, sender=OrdenTrabajo)
def notificar_cambio_estado_critico(sender, instance, created, **kwargs):
    """Notificar cuando una orden cambia a estado crítico o se completa"""
    if not created:
        # Notificar si la orden está más de 7 días en taller
        if instance.dias_en_taller > 7 and instance.estado not in ['COMPLETADA', 'CANCELADA']:
            supervisores = User.objects.filter(
                groups__name__in=['Supervisores Taller', 'Gerentes']
            )

            if supervisores.exists():
                send_mail(
                    subject=f'ALERTA: Orden {instance.folio} lleva {instance.dias_en_taller} días en taller',
                    message=f'''
                    ATENCIÓN: La orden de trabajo {instance.folio} lleva {instance.dias_en_taller} días en taller.

                    Unidad: {instance.unidad.numero_economico} - {instance.unidad.placa}
                    Estado: {instance.get_estado_display()}
                    Mecánico: {instance.mecanico_asignado}
                    Kilometraje ingreso: {instance.kilometraje_ingreso:,} km

                    Por favor revise el estado de esta orden.
                    ''',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[s.email for s in supervisores if s.email],
                    fail_silently=True,
                )

        # Notificar cuando se completa
        elif instance.estado == 'COMPLETADA' and instance.creada_por:
            send_mail(
                subject=f'Orden de Trabajo Completada: {instance.folio}',
                message=f'''
                La orden de trabajo {instance.folio} ha sido completada.

                Unidad: {instance.unidad.numero_economico} - {instance.unidad.placa}
                Trabajo realizado: {instance.trabajo_realizado}
                Costo total: ${instance.costo_total_real:,.2f}
                Tiempo en taller: {instance.dias_en_taller} días ({instance.horas_en_taller} horas)
                Kilometraje salida: {instance.kilometraje_salida:,} km

                La unidad está lista para volver a operación.
                ''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[instance.creada_por.email] if instance.creada_por.email else [],
                fail_silently=True,
            )


@receiver(post_save, sender=OrdenTrabajo)
def asignar_mecanico_notificacion(sender, instance, created, **kwargs):
    """Notificar al mecánico cuando se le asigna una orden"""
    if not created and instance.mecanico_asignado:
        # Verificar si se acaba de asignar (comparando con el objeto anterior)
        try:
            old_instance = OrdenTrabajo.objects.get(pk=instance.pk)
            if old_instance.mecanico_asignado != instance.mecanico_asignado:
                if instance.mecanico_asignado.email:
                    send_mail(
                        subject=f'Orden de Trabajo Asignada: {instance.folio}',
                        message=f'''
                        Se te ha asignado la siguiente orden de trabajo:

                        Folio: {instance.folio}
                        Unidad: {instance.unidad.numero_economico} - {instance.unidad.placa}
                        Prioridad: {instance.get_prioridad_display()}
                        Problema: {instance.descripcion_problema}
                        Kilometraje: {instance.kilometraje_ingreso:,} km

                        Por favor revisa los detalles en el sistema.
                        ''',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[instance.mecanico_asignado.email],
                        fail_silently=True,
                    )
        except OrdenTrabajo.DoesNotExist:
            pass


@receiver(post_save, sender=PiezaRequerida)
def actualizar_estado_orden_por_piezas(sender, instance, created, **kwargs):
    """Actualizar el estado de la orden cuando se agregan piezas"""
    if created:
        orden = instance.orden_trabajo

        # Si la orden está en diagnóstico y se agregan piezas, cambiar a esperando piezas
        if orden.estado == 'EN_DIAGNOSTICO':
            orden.estado = 'ESPERANDO_PIEZAS'
            orden.save()


@receiver(post_save, sender=ItemRecepcion)
def actualizar_piezas_recibidas(sender, instance, created, **kwargs):
    """
    Cuando se recibe una pieza en almacén, actualizar el estado
    de las piezas requeridas en las órdenes de trabajo
    """
    if created and instance.item_orden.item_requisicion:
        # Buscar piezas requeridas vinculadas a este item de requisición
        piezas_vinculadas = PiezaRequerida.objects.filter(
            item_requisicion=instance.item_orden.item_requisicion,
            estado__in=['SOLICITADA', 'EN_COMPRA']
        )

        # Actualizar estado a recibida
        for pieza in piezas_vinculadas:
            pieza.marcar_como_recibida(
                costo_real=instance.item_orden.precio_unitario
            )

        # Verificar si todas las piezas de la orden ya fueron recibidas
        for pieza in piezas_vinculadas:
            orden = pieza.orden_trabajo

            # Si todas las piezas están recibidas, cambiar estado de la orden
            if not orden.piezas_requeridas.filter(
                estado__in=['PENDIENTE', 'SOLICITADA', 'EN_COMPRA']
            ).exists() and orden.estado == 'ESPERANDO_PIEZAS':
                orden.estado = 'EN_REPARACION'
                orden.save()

                # Notificar al mecánico
                if orden.mecanico_asignado and orden.mecanico_asignado.email:
                    send_mail(
                        subject=f'Piezas Recibidas: {orden.folio}',
                        message=f'''
                        Las piezas para la orden {orden.folio} han sido recibidas.

                        Unidad: {orden.unidad.numero_economico} - {orden.unidad.placa}

                        La orden ha sido cambiada a estado "En Reparación".
                        Puedes continuar con el trabajo.
                        ''',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[orden.mecanico_asignado.email],
                        fail_silently=True,
                    )


@receiver(pre_save, sender=OrdenTrabajo)
def registrar_cambio_estado(sender, instance, **kwargs):
    """Registrar automáticamente cambios de estado en el seguimiento"""
    if instance.pk:  # Solo si la orden ya existe
        try:
            old_instance = OrdenTrabajo.objects.get(pk=instance.pk)

            # Si cambió el estado, crear seguimiento automático
            if old_instance.estado != instance.estado:
                # Este se ejecuta después del save, por eso usamos post_save
                pass

        except OrdenTrabajo.DoesNotExist:
            pass