"""
Lógica para detectar cuándo dos viajes SENCILLO (misma unidad + mismo
operador, en curso) deben unirse en un único viaje FULL, y para ejecutar esa
fusión. Compartida por el alta manual de bitácoras, su edición y el traslado
desde Modulación.
"""
import os

from modulos.bitacoras.models import BitacoraViaje

# Contenedores que ocupa cada modalidad en la capacidad de la unidad.
CARGA_POR_MODALIDAD = {
    'SENCILLO': 1,
    'LOCAL': 1,
    'FULL': 2,
    'LOCAL_FULL': 2,
}

CAPACIDAD_UNIDAD = 2


def viajes_en_curso(unidad, *, excluir_pk=None):
    """Viajes no completados de la unidad, con el operador pre-cargado."""
    if unidad is None:
        return []
    qs = (BitacoraViaje.objects
          .filter(unidad=unidad, completado=False)
          .select_related('operador'))
    if excluir_pk:
        qs = qs.exclude(pk=excluir_pk)
    return list(qs)


def contenedores_en_curso(unidad, *, excluir_pk=None):
    """Suma la carga (1 ó 2) de los viajes en curso de la unidad."""
    return sum(
        CARGA_POR_MODALIDAD.get(v.modalidad, 1)
        for v in viajes_en_curso(unidad, excluir_pk=excluir_pk)
    )


def unidad_bloqueada(unidad, *, excluir_pk=None):
    """True si la unidad ya llegó a su capacidad (2 contenedores en curso)."""
    return contenedores_en_curso(unidad, excluir_pk=excluir_pk) >= CAPACIDAD_UNIDAD


def unidades_bloqueadas_ids(*, excluir_pk=None):
    """Ids de unidades con 2+ contenedores en curso (para filtrar selectores)."""
    from django.db.models import Case, IntegerField, Sum, Value, When

    qs = BitacoraViaje.objects.filter(completado=False)
    if excluir_pk:
        qs = qs.exclude(pk=excluir_pk)
    qs = (qs.values('unidad_id')
            .annotate(carga=Sum(Case(
                When(modalidad__in=['FULL', 'LOCAL_FULL'], then=Value(2)),
                default=Value(1),
                output_field=IntegerField(),
            )))
            .filter(carga__gte=CAPACIDAD_UNIDAD))
    return {row['unidad_id'] for row in qs}
