"""Aviso por correo a la agencia aduanal cuando un vacío sufre un retraso."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def notificar_retraso_agencia(retraso) -> bool:
    """
    Envía el correo del retraso a la agencia del vacío. Sella
    notificado_agencia / fecha_notificacion en éxito. Nunca lanza:
    devuelve False si no hay destinatario o si el envío falla.
    """
    vacio = retraso.vacio
    agencia = vacio.agencia
    destinatario = getattr(agencia, 'email_contacto', '') if agencia else ''
    if not destinatario:
        logger.warning('Retraso %s: sin correo de agencia; no se notifica.', retraso.pk)
        return False

    contexto = {
        'retraso': retraso,
        'vacio': vacio,
        'agencia': agencia,
    }
    asunto = f'[Transportes Kasu] Retraso de vacío {vacio.folio} — {retraso.get_tipo_display()}'
    cuerpo_txt = render_to_string('vacios/email/retraso_agencia.txt', contexto)
    cuerpo_html = render_to_string('vacios/email/retraso_agencia.html', contexto)

    try:
        msg = EmailMultiAlternatives(
            subject=asunto,
            body=cuerpo_txt,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            to=[destinatario],
        )
        msg.attach_alternative(cuerpo_html, 'text/html')
        msg.send()
    except Exception:
        logger.exception('Retraso %s: falló el envío del correo a la agencia.', retraso.pk)
        return False

    retraso.notificado_agencia = True
    retraso.fecha_notificacion = timezone.now()
    retraso.save(update_fields=['notificado_agencia', 'fecha_notificacion'])
    return True
