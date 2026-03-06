"""Lógica de negocio para verificación de ciclo de candados."""

import logging

logger = logging.getLogger(__name__)


def verificar_ciclo_candados(carga):
    """
    Compara los números de candado nuevo de la carga anterior de la misma unidad
    con el número de candado anterior retirado en la carga actual.

    Si no coinciden, genera AlertaCombustible de tipo CANDADO_NO_COINCIDE.
    No hace nada si faltan datos OCR en alguno de los dos registros.
    """
    from .models import CargaCombustible, AlertaCombustible

    # Solo verificar cuando la carga esté completada y tenga número de candado anterior
    if carga.estado != 'COMPLETADO' or not carga.numero_candado_anterior:
        return

    # Carga anterior completada de la misma unidad
    carga_anterior = (
        CargaCombustible.objects
        .filter(unidad=carga.unidad, estado='COMPLETADO')
        .exclude(pk=carga.pk)
        .order_by('-fecha_hora_inicio')
        .prefetch_related('fotos_candado_nuevo')
        .first()
    )
    if not carga_anterior:
        return

    # Números de candados nuevos colocados en la carga anterior
    numeros_nuevos_anterior = {
        foto.numero_candado
        for foto in carga_anterior.fotos_candado_nuevo.all()
        if foto.numero_candado
    }
    if not numeros_nuevos_anterior:
        return

    # Comparar
    numero_retirado = carga.numero_candado_anterior
    if numero_retirado not in numeros_nuevos_anterior:
        AlertaCombustible.objects.get_or_create(
            carga=carga,
            tipo_alerta='CANDADO_NO_COINCIDE',
            defaults={
                'mensaje': (
                    f"Unidad {carga.unidad.numero_economico}: el candado retirado "
                    f"({numero_retirado}) no coincide con los candados colocados "
                    f"en la carga anterior "
                    f"({', '.join(sorted(numeros_nuevos_anterior))}). "
                    f"Carga anterior folio #{carga_anterior.pk} del "
                    f"{carga_anterior.fecha_hora_inicio.strftime('%d/%m/%Y')}."
                )
            }
        )
        logger.warning(
            "Ciclo de candado no coincide — unidad %s: retirado=%s anterior=%s",
            carga.unidad.numero_economico,
            numero_retirado,
            numeros_nuevos_anterior,
        )
