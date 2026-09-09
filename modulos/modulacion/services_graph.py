"""
Cliente mínimo de Microsoft Graph (app-only) para leer el buzón de calidad.

Solo lectura: token client-credentials, listar los correos de un remitente y
bajar el primer adjunto `.xls`. Sin lógica de negocio. Toda falla de red,
de token o de HTTP se traduce a `GraphError`.
"""
import base64
import datetime
import time
from dataclasses import dataclass

import requests
from django.conf import settings

_GRAPH = 'https://graph.microsoft.com/v1.0'
_token_cache = {'valor': None, 'expira': 0.0}


class GraphError(Exception):
    """Cualquier problema hablando con Microsoft Graph."""


@dataclass
class CorreoLCTPC:
    id: str
    asunto: str
    recibido: datetime.datetime | None


def _config_ok():
    return all([
        settings.GRAPH_TENANT_ID,
        settings.GRAPH_CLIENT_ID,
        settings.GRAPH_CLIENT_SECRET,
    ])


def obtener_token() -> str:
    if not _config_ok():
        raise GraphError(
            'Graph API no configurada (faltan GRAPH_TENANT_ID / GRAPH_CLIENT_ID / '
            'GRAPH_CLIENT_SECRET).'
        )
    ahora = time.time()
    if _token_cache['valor'] and _token_cache['expira'] - 60 > ahora:
        return _token_cache['valor']

    url = f'https://login.microsoftonline.com/{settings.GRAPH_TENANT_ID}/oauth2/v2.0/token'
    datos = {
        'client_id': settings.GRAPH_CLIENT_ID,
        'client_secret': settings.GRAPH_CLIENT_SECRET,
        'scope': 'https://graph.microsoft.com/.default',
        'grant_type': 'client_credentials',
    }
    try:
        resp = requests.post(url, data=datos, timeout=15)
    except requests.RequestException as exc:
        raise GraphError(f'Error de red al pedir el token: {exc}') from exc
    if resp.status_code != 200:
        raise GraphError(f'Token rechazado ({resp.status_code}): {resp.text[:300]}')

    payload = resp.json()
    _token_cache['valor'] = payload['access_token']
    _token_cache['expira'] = ahora + int(payload.get('expires_in', 3600))
    return _token_cache['valor']


def _get(path, params=None):
    token = obtener_token()
    try:
        resp = requests.get(
            f'{_GRAPH}{path}', params=params,
            headers={'Authorization': f'Bearer {token}'}, timeout=30,
        )
    except requests.RequestException as exc:
        raise GraphError(f'Error de red en {path}: {exc}') from exc
    if resp.status_code != 200:
        raise GraphError(f'Graph {path} -> {resp.status_code}: {resp.text[:300]}')
    return resp.json()


def _parsear_dt(valor):
    if not valor:
        return None
    try:
        return datetime.datetime.fromisoformat(valor.replace('Z', '+00:00'))
    except ValueError:
        return None


def listar_correos(remitente: str | None = None) -> list:
    remitente = remitente or settings.MODULACION_LCTPC_REMITENTE
    mailbox = settings.MODULACION_LCTPC_MAILBOX
    params = {
        '$filter': f"from/emailAddress/address eq '{remitente}'",
        '$select': 'id,subject,receivedDateTime',
        '$orderby': 'receivedDateTime desc',
        '$top': '25',
    }
    data = _get(f'/users/{mailbox}/messages', params=params)
    return [
        CorreoLCTPC(
            id=item['id'],
            asunto=item.get('subject', '') or '',
            recibido=_parsear_dt(item.get('receivedDateTime')),
        )
        for item in data.get('value', [])
    ]


def descargar_adjunto_xls(message_id: str) -> bytes:
    mailbox = settings.MODULACION_LCTPC_MAILBOX
    data = _get(f'/users/{mailbox}/messages/{message_id}/attachments')
    for att in data.get('value', []):
        nombre = (att.get('name') or '').lower()
        if (att.get('@odata.type') == '#microsoft.graph.fileAttachment'
                and nombre.endswith('.xls')):
            return base64.b64decode(att['contentBytes'])
    raise GraphError(f'El correo {message_id} no tiene un adjunto .xls.')
