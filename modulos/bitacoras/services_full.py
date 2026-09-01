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


def sencillo_apareable(unidad, operador, *, excluir_pk=None):
    """
    Viaje SENCILLO en curso de la misma unidad y el mismo operador con el que
    se puede formar un Full. El más reciente por fecha_carga si hubiera varios.
    """
    if unidad is None or operador is None:
        return None
    candidatos = [
        v for v in viajes_en_curso(unidad, excluir_pk=excluir_pk)
        if v.modalidad == 'SENCILLO' and v.operador_id == operador.pk
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda v: v.fecha_carga)


def _mismo_destino(sencillo, cliente, cp_destino):
    """True si el sencillo va al mismo cliente y CP que los datos dados."""
    cliente_pk = cliente.pk if cliente is not None else None
    mismo_cliente = sencillo.cliente_id == cliente_pk
    mismo_cp = (sencillo.cp_destino or '').strip() == (cp_destino or '').strip()
    return mismo_cliente and mismo_cp


def evaluar_fusion(unidad, operador, cliente, cp_destino, *, excluir_pk=None):
    """
    Decide qué hacer al guardar/editar un viaje SENCILLO. Devuelve un dict con
    'accion' en {'ninguna', 'bloqueo', 'ofrecer_full'}.

    `cliente` es instancia de Cliente o None; `cp_destino` es str.
    """
    if unidad is None or operador is None:
        return {'accion': 'ninguna'}

    apareable = sencillo_apareable(unidad, operador, excluir_pk=excluir_pk)
    if apareable is not None:
        tipo = 'directo' if _mismo_destino(apareable, cliente, cp_destino) else 'reparto'
        return {'accion': 'ofrecer_full', 'sencillo': apareable, 'tipo_full': tipo}

    en_curso = viajes_en_curso(unidad, excluir_pk=excluir_pk)

    sencillo_otro_op = next(
        (v for v in en_curso
         if v.modalidad == 'SENCILLO' and v.operador_id != operador.pk),
        None,
    )
    if sencillo_otro_op is not None:
        return {'accion': 'bloqueo', 'mensaje': (
            f'La unidad {unidad.numero_economico} ya tiene un viaje sencillo en '
            f'curso con el operador {sencillo_otro_op.operador.nombre}. Una unidad '
            f'no puede llevar dos sencillos por separado; para un segundo '
            f'contenedor genere un Full con el mismo operador.'
        )}

    carga = sum(CARGA_POR_MODALIDAD.get(v.modalidad, 1) for v in en_curso)
    if carga >= CAPACIDAD_UNIDAD:
        return {'accion': 'bloqueo', 'mensaje': (
            f'La unidad {unidad.numero_economico} ya tiene 2 contenedores en curso.'
        )}

    return {'accion': 'ninguna'}


def fusionar_en_full(sencillo_existente, datos_segundo, *, tipo_full):
    """
    Convierte `sencillo_existente` en un viaje FULL absorbiendo el segundo
    contenedor. Conserva todos los datos del primer contenedor (fechas,
    destino, kilometraje, diésel, tipo). Guarda con full_clean().

    `datos_segundo`: {contenedor, peso, sellos, cliente, cp_destino}.
    `tipo_full`: 'directo' (mismo destino) o 'reparto' (dos destinos).

    El borrado del segundo registro y el ligado de la Modulación son
    responsabilidad de quien llama.
    """
    s = sencillo_existente
    s.modalidad = 'FULL'
    s.contenedor_2 = (datos_segundo.get('contenedor') or '').strip().upper()
    s.peso_2 = datos_segundo.get('peso')
    s.sellos_2 = datos_segundo.get('sellos') or ''

    if tipo_full == 'reparto':
        s.reparto = True
        s.cliente_2 = datos_segundo.get('cliente')
        s.cp_destino_2 = (datos_segundo.get('cp_destino') or '').strip()
    else:
        s.reparto = False
        s.cliente_2 = None
        s.cp_destino_2 = ''

    s.full_clean()
    s.save()

    if s.reparto and s.cp_destino_2 and os.environ.get('GOOGLE_MAPS_API_KEY'):
        s.calcular_distancia_google()

    return s
