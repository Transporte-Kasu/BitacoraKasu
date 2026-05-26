"""
WhatsApp Service — OpenWA REST API.

Envía mensajes de texto a los números configurados en WA_ALLOWED_NUMBERS.
Nunca lanza excepciones hacia el caller; los errores se loggean y se ignoran.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _construir_chat_id(numero: str) -> str:
    """Normaliza un número a formato chatId de WhatsApp (sin + ni espacios, con @c.us)."""
    numero = numero.strip().lstrip('+').replace(' ', '').replace('-', '')
    if not numero.endswith('@c.us'):
        numero = f"{numero}@c.us"
    return numero


def enviar_mensaje(texto: str, numeros: list[str] | None = None) -> bool:
    """
    Envía un mensaje de texto a los números indicados (o a WA_ALLOWED_NUMBERS si None).

    Endpoint: POST /api/sessions/{sessionId}/messages/send-text
    Body: { "chatId": "521XXXXXXXXX@c.us", "text": "..." }

    Returns True si al menos un mensaje fue enviado con éxito.
    """
    api_url = getattr(settings, 'WA_API_URL', '').rstrip('/')
    api_key = getattr(settings, 'WA_API_KEY', '')
    session_id = getattr(settings, 'WA_SESSION_ID', '')

    if not api_url or not api_key or not session_id:
        logger.warning("WhatsApp: WA_API_URL, WA_API_KEY o WA_SESSION_ID no configurados.")
        return False

    if numeros is None:
        numeros = getattr(settings, 'WA_ALLOWED_NUMBERS', [])

    if not numeros:
        logger.warning("WhatsApp: no hay números destinatarios configurados.")
        return False

    endpoint = f"{api_url}/sessions/{session_id}/messages/send-text"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    enviados = 0
    for numero in numeros:
        chat_id = _construir_chat_id(numero)
        payload = {'chatId': chat_id, 'text': texto}
        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=10)
            if resp.status_code in (200, 201):
                enviados += 1
                logger.info("WhatsApp: mensaje enviado a %s", chat_id)
            else:
                logger.warning(
                    "WhatsApp: respuesta %s para %s — %s",
                    resp.status_code, chat_id, resp.text[:200],
                )
        except requests.RequestException as exc:
            logger.exception("WhatsApp: error al enviar a %s — %s", chat_id, exc)

    return enviados > 0
