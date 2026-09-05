"""
Token firmado para el formulario público de "completar datos de terminal"
(carril/horarios) en Modulación. No requiere tabla propia: el token es el
pk de la Modulación firmado con SECRET_KEY (django.core.signing), así que
es opaco y no se puede fabricar sin conocer la clave del proyecto.

Vigencia por estado, no por tiempo: el token no expira solo, pero
completar_datos_terminal (views.py) rechaza el acceso en cuanto
Modulacion.estado deja de ser 'PENDIENTE'.
"""
from django.core import signing

from .models import Modulacion

_SALT = 'modulacion.completar_datos_terminal'


def generar_token(modulacion):
    return signing.dumps({'modulacion_id': modulacion.pk}, salt=_SALT)


def resolver_modulacion(token):
    """Devuelve la Modulacion del token, o levanta Modulacion.DoesNotExist
    si el token es inválido, fue manipulado, o el registro ya no existe."""
    try:
        data = signing.loads(token, salt=_SALT)
        modulacion_id = data['modulacion_id']
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise Modulacion.DoesNotExist('Token inválido')
    return Modulacion.objects.select_related('terminal_portuaria').get(pk=modulacion_id)
