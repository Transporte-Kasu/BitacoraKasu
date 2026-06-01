"""
WhatsApp Service — WAHA (WhatsApp HTTP API).

Envía mensajes de texto a los números configurados en WA_ALLOWED_NUMBERS.
Nunca lanza excepciones hacia el caller; los errores se loggean y se ignoran.
"""

import logging
import time

import requests
from requests.exceptions import Timeout, ConnectionError as ReqConnectionError
from django.conf import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        'X-API-Key': settings.WA_API_KEY,
        'Content-Type': 'application/json',
    }


def _session_url() -> str:
    return f"{settings.WA_API_URL.rstrip('/')}/sessions/{settings.WA_SESSION_ID}"


def _session_status() -> str:
    try:
        r = requests.get(_session_url(), headers=_headers(), timeout=8)
        return r.json().get('status', 'unknown') if r.status_code == 200 else 'unknown'
    except Exception:
        return 'unknown'


def _ensure_session_ready() -> bool:
    """Verifica que la sesión esté activa; la inicia si está disconnected o stopped."""
    status = _session_status()
    if status == 'ready':
        return True

    if status not in ('disconnected', 'stopped'):
        # initializing / authenticating / qr_ready / unknown — no tocar
        logger.warning("Sesión WhatsApp en estado '%s', no se puede enviar.", status)
        return False

    logger.warning("Sesión WhatsApp %s — intentando iniciar...", status)
    try:
        # start puede bloquear mientras WAHA inicializa; continuamos con polling
        requests.post(f"{_session_url()}/start", headers=_headers(), timeout=20)
    except Timeout:
        pass  # WAHA sigue procesando en background
    except Exception as e:
        logger.error("Error al iniciar sesión WhatsApp: %s", e)
        return False

    # Polling hasta 60s — WAHA puede tardar hasta ~40s en reconectar
    for _ in range(30):
        time.sleep(2)
        if _session_status() == 'ready':
            logger.info("Sesión WhatsApp reconectada OK.")
            return True

    logger.error("Sesión WhatsApp no alcanzó estado ready tras iniciar.")
    return False


def _construir_chat_id(numero: str) -> str:
    """Normaliza un número a formato chatId de WhatsApp (sin + ni espacios, con @c.us)."""
    numero = numero.strip().lstrip('+').replace(' ', '').replace('-', '')
    if not numero.endswith('@c.us'):
        numero = f"{numero}@c.us"
    return numero


def enviar_mensaje(texto: str, numeros: list[str] | None = None) -> bool:
    """
    Envía un mensaje de texto a los números indicados (o a WA_ALLOWED_NUMBERS si None).

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

    if not _ensure_session_ready():
        logger.error("WhatsApp no disponible, mensajes no enviados.")
        return False

    endpoint = f"{api_url}/sessions/{session_id}/messages/send-text"

    enviados = 0
    for numero in numeros:
        chat_id = _construir_chat_id(numero)
        try:
            resp = requests.post(
                endpoint,
                json={'chatId': chat_id, 'text': texto},
                headers=_headers(),
                timeout=30,  # WAHA bloquea esperando ACK; reintentar causaría duplicados
            )
            if resp.status_code in (200, 201):
                enviados += 1
                logger.info("WhatsApp: mensaje enviado a %s", chat_id)
            else:
                logger.warning(
                    "WhatsApp: respuesta %s para %s — %s",
                    resp.status_code, chat_id, resp.text[:200],
                )
        except Timeout:
            # Timeout ≠ fallo: WAHA ya encoló el mensaje. No reintentar (causaría duplicados).
            enviados += 1
            logger.warning(
                "WhatsApp send_text timeout para %s (mensaje probablemente enviado).", chat_id
            )
        except ReqConnectionError as e:
            logger.error("WhatsApp sin conexión al enviar a %s: %s", chat_id, e)
        except Exception as exc:
            logger.exception("WhatsApp: error al enviar a %s — %s", chat_id, exc)

    return enviados > 0


def enviar_a_admin(texto: str) -> bool:
    """Envía un mensaje al chat del administrador configurado en WA_ADMIN_CHAT."""
    admin_chat = getattr(settings, 'WA_ADMIN_CHAT', '')
    if not admin_chat:
        logger.warning("WhatsApp: WA_ADMIN_CHAT no configurado.")
        return False
    return enviar_mensaje(texto, numeros=[admin_chat])
