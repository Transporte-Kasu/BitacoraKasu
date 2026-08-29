"""Lógica de negocio reutilizable del módulo Vacíos."""

from modulos.bitacoras.models import BitacoraViaje
from modulos.modulacion.models import Modulacion
from modulos.operadores.models import Operador

from .models import Vacio


def operadores_libres():
    """
    Operadores LOCAL activos que no están ocupados:
    - sin Modulación asignada en estado MODULADO o EN_PATIO_ESPERANZA,
    - sin Vacío en estado ASIGNADO,
    - sin BitacoraViaje en curso (completado=False).
    """
    ocupados_modulacion = (
        Modulacion.objects
        .filter(estado__in=['MODULADO', 'EN_PATIO_ESPERANZA'], operador__isnull=False)
        .values_list('operador_id', flat=True)
    )
    ocupados_vacio = (
        Vacio.objects
        .filter(estado='ASIGNADO', operador__isnull=False)
        .values_list('operador_id', flat=True)
    )
    ocupados_bitacora = (
        BitacoraViaje.objects
        .filter(completado=False, operador__isnull=False)
        .values_list('operador_id', flat=True)
    )
    ocupados = set(ocupados_modulacion) | set(ocupados_vacio) | set(ocupados_bitacora)

    return (
        Operador.objects
        .filter(tipo='LOCAL', activo=True)
        .exclude(id__in=ocupados)
        .order_by('nombre')
    )
