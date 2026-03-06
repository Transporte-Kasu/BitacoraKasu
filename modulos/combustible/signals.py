import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CargaCombustible, AlertaCombustible, FotoCandadoNuevo

logger = logging.getLogger(__name__)


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

    # OCR del candado anterior al completar la carga
    if not instance.ocr_candado_anterior_ok and instance.foto_candado_anterior:
        _procesar_ocr_candado_anterior(instance)


@receiver(post_save, sender=FotoCandadoNuevo)
def procesar_ocr_foto_candado_nuevo(sender, instance, created, **kwargs):
    """Ejecuta OCR sobre cada foto de candado nuevo al guardarla."""
    if not created or instance.ocr_procesado:
        return
    _procesar_ocr_foto_nueva(instance)


def _procesar_ocr_candado_anterior(carga):
    """Lee el número del candado anterior por OCR y verifica el ciclo."""
    from config.services.ocr_service import leer_numero_candado
    from .services import verificar_ciclo_candados

    numero = leer_numero_candado(carga.foto_candado_anterior)
    CargaCombustible.objects.filter(pk=carga.pk).update(
        numero_candado_anterior=numero,
        ocr_candado_anterior_ok=True,
    )
    # Actualizar instancia en memoria para la verificación
    carga.numero_candado_anterior = numero
    carga.ocr_candado_anterior_ok = True

    logger.info(
        "OCR candado anterior — carga #%s unidad %s: '%s'",
        carga.pk, carga.unidad.numero_economico, numero or '(no detectado)',
    )

    verificar_ciclo_candados(carga)


def _procesar_ocr_foto_nueva(foto):
    """Lee el número del candado nuevo por OCR."""
    from config.services.ocr_service import leer_numero_candado

    numero = leer_numero_candado(foto.foto)
    FotoCandadoNuevo.objects.filter(pk=foto.pk).update(
        numero_candado=numero,
        ocr_procesado=True,
    )
    logger.info(
        "OCR candado nuevo — carga #%s '%s': '%s'",
        foto.carga_id, foto.descripcion or foto.pk, numero or '(no detectado)',
    )
