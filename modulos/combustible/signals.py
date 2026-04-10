import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CargaCombustible, AlertaCombustible, FotoCandadoNuevo

logger = logging.getLogger(__name__)


@receiver(post_save, sender=CargaCombustible)
def generar_alertas_combustible(sender, instance, created, **kwargs):
    """Genera alertas automáticas al completar una carga de combustible."""
    if instance.estado != 'COMPLETADO':
        return

    if instance.tipo_flujo == 'LOCAL':
        # Flujo simplificado: no hay datos de candado, solo alertas por litros y km
        _verificar_exceso_litros(instance)
        _verificar_kilometraje_menor(instance)
        return

    # Flujo completo (FORANEO / ESPERANZA)
    _verificar_estado_candado(instance)
    _verificar_exceso_litros(instance)
    _verificar_kilometraje_menor(instance)

    # OCR del candado anterior al completar la carga
    if not instance.ocr_candado_anterior_ok and instance.foto_candado_anterior:
        _procesar_ocr_candado_anterior(instance)


@receiver(post_save, sender=FotoCandadoNuevo)
def procesar_ocr_foto_candado_nuevo(sender, instance, created, **kwargs):
    """Ejecuta OCR sobre cada foto de candado nuevo al guardarla."""
    if not created or instance.ocr_procesado:
        return
    _procesar_ocr_foto_nueva(instance)


# ---------------------------------------------------------------------------
# Funciones privadas de verificación
# ---------------------------------------------------------------------------

def _verificar_estado_candado(carga):
    """Genera alerta si el candado anterior está alterado, violado o sin candado."""
    _tipo_candado = {
        'ALTERADO': 'CANDADO_ALTERADO',
        'VIOLADO': 'CANDADO_VIOLADO',
        'SIN_CANDADO': 'SIN_CANDADO',
    }
    tipo = _tipo_candado.get(carga.estado_candado_anterior)
    if tipo:
        AlertaCombustible.objects.get_or_create(
            carga=carga,
            tipo_alerta=tipo,
            defaults={
                'mensaje': (
                    f"Unidad {carga.unidad.numero_economico}: candado registrado como "
                    f"'{carga.get_estado_candado_anterior_display()}' en la carga del "
                    f"{carga.fecha_hora_inicio.strftime('%d/%m/%Y %H:%M')}. "
                    f"Despachador: {carga.despachador.nombre}."
                )
            }
        )


def _verificar_exceso_litros(carga):
    """Genera alerta si los litros cargados superan la capacidad del tanque."""
    if (carga.unidad.capacidad_combustible and
            carga.cantidad_litros > carga.unidad.capacidad_combustible):
        AlertaCombustible.objects.get_or_create(
            carga=carga,
            tipo_alerta='EXCESO_COMBUSTIBLE',
            defaults={
                'mensaje': (
                    f"Unidad {carga.unidad.numero_economico}: se cargaron "
                    f"{carga.cantidad_litros} L pero la capacidad del tanque es "
                    f"{carga.unidad.capacidad_combustible} L "
                    f"(exceso: {carga.cantidad_litros - carga.unidad.capacidad_combustible} L). "
                    f"Despachador: {carga.despachador.nombre}."
                )
            }
        )


def _verificar_kilometraje_menor(carga):
    """Genera alerta si el kilometraje registrado es menor al de la carga anterior."""
    # En flujo LOCAL el kilometraje queda en 0 (default temporal),
    # así que solo verificamos si es mayor que 0 para evitar falsos positivos.
    if carga.kilometraje_actual == 0:
        return

    carga_anterior = (
        CargaCombustible.objects
        .filter(unidad=carga.unidad, estado='COMPLETADO')
        .exclude(pk=carga.pk)
        .order_by('-fecha_hora_inicio')
        .first()
    )
    if carga_anterior and carga.kilometraje_actual < carga_anterior.kilometraje_actual:
        AlertaCombustible.objects.get_or_create(
            carga=carga,
            tipo_alerta='KILOMETRAJE_MENOR',
            defaults={
                'mensaje': (
                    f"Unidad ECO {carga.unidad.numero_economico}: el kilometraje registrado "
                    f"({carga.kilometraje_actual:,} km) es MENOR al de la carga anterior "
                    f"({carga_anterior.kilometraje_actual:,} km) del "
                    f"{carga_anterior.fecha_hora_inicio.strftime('%d/%m/%Y')}. "
                    f"Posible retroceso de odómetro o error de captura. "
                    f"Despachador: {carga.despachador.nombre}."
                )
            }
        )


# ---------------------------------------------------------------------------
# Funciones privadas de OCR
# ---------------------------------------------------------------------------

def _procesar_ocr_candado_anterior(carga):
    """Lee el número del candado anterior por OCR y verifica el ciclo."""
    from config.services.ocr_service import leer_numero_candado
    from .services import verificar_ciclo_candados

    numero = leer_numero_candado(carga.foto_candado_anterior)
    CargaCombustible.objects.filter(pk=carga.pk).update(
        numero_candado_anterior=numero,
        ocr_candado_anterior_ok=True,
    )
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
