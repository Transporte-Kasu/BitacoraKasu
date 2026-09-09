"""
Cliente mínimo de Microsoft Graph (app-only) para leer el buzón de calidad.

Solo lectura: token client-credentials, listar los correos de un remitente y
bajar el primer adjunto `.xls`. Sin lógica de negocio. Toda falla de red,
de token o de HTTP se traduce a `GraphError`.
"""
import base64
import datetime
import logging
import time
from dataclasses import dataclass
from urllib.parse import quote

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('modulos.modulacion')

_GRAPH = 'https://graph.microsoft.com/v1.0'
_token_cache = {'valor': None, 'expira': 0.0}

# Tope de páginas al recorrer @odata.nextLink (cada página son $top correos).
# El remitente manda ~1 correo/día, así que 40 x 50 = 2000 cubre varios años.
_PAGINAS_MAX = 40


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
    token = payload.get('access_token')
    if not token:
        raise GraphError(f'Respuesta de token sin access_token: {resp.text[:300]}')
    _token_cache['valor'] = token
    _token_cache['expira'] = ahora + int(payload.get('expires_in', 3600))
    return token


def _get(path_o_url, params=None):
    token = obtener_token()
    # `@odata.nextLink` viene como URL absoluta y ya trae sus parámetros.
    url = path_o_url if path_o_url.startswith('http') else f'{_GRAPH}{path_o_url}'
    try:
        resp = requests.get(
            url, params=params,
            headers={'Authorization': f'Bearer {token}'}, timeout=30,
        )
    except requests.RequestException as exc:
        raise GraphError(f'Error de red en {url}: {exc}') from exc
    if resp.status_code != 200:
        raise GraphError(f'Graph {url} -> {resp.status_code}: {resp.text[:300]}')
    return resp.json()


def _inicio_ano_utc() -> datetime.datetime:
    """1 de enero del año en curso, aware en UTC."""
    return datetime.datetime(timezone.now().year, 1, 1, tzinfo=datetime.timezone.utc)


def _parsear_dt(valor):
    if not valor:
        return None
    try:
        return datetime.datetime.fromisoformat(valor.replace('Z', '+00:00'))
    except ValueError:
        return None


def listar_correos(remitente: str | None = None) -> list[CorreoLCTPC]:
    """Correos del remitente recibidos en el año en curso, del más nuevo al más viejo.

    Se recorren TODAS las páginas del remitente vía `@odata.nextLink` (hasta el
    tope `_PAGINAS_MAX`) y luego se filtra por fecha en cliente. No se asume
    ningún orden del servidor: Graph, sin `$orderby`, no garantiza
    receivedDateTime desc y de hecho suele devolver los más viejos primero, así
    que un corte temprano por fecha se saltaría correos recientes.

    No se manda `$orderby`: combinar un `$filter` sobre `from/emailAddress/address`
    con `$orderby receivedDateTime` hace que Graph responda 400 "InefficientFilter"
    (no hay índice compuesto). El reordenamiento por fecha se hace en cliente.
    """
    remitente = remitente or settings.MODULACION_LCTPC_REMITENTE
    mailbox = settings.MODULACION_LCTPC_MAILBOX
    # Escape de comilla simple para el literal OData ('' representa una ').
    remitente_odata = remitente.replace("'", "''")
    desde = _inicio_ano_utc()
    params = {
        '$filter': f"from/emailAddress/address eq '{remitente_odata}'",
        '$select': 'id,subject,receivedDateTime',
        '$top': '50',
    }

    correos: list[CorreoLCTPC] = []
    data = _get(f'/users/{mailbox}/messages', params=params)
    paginas = 0
    while True:
        paginas += 1
        correos.extend(
            CorreoLCTPC(
                id=item['id'],
                asunto=item.get('subject', '') or '',
                recibido=_parsear_dt(item.get('receivedDateTime')),
            )
            for item in data.get('value', [])
        )
        siguiente = data.get('@odata.nextLink')
        if not siguiente:
            break
        if paginas >= _PAGINAS_MAX:
            logger.warning(
                'listar_correos: se alcanzó el tope de %s páginas para %s; '
                'puede haber correos antiguos sin revisar.',
                _PAGINAS_MAX, remitente,
            )
            break
        data = _get(siguiente)

    correos = [c for c in correos if c.recibido is None or c.recibido >= desde]
    correos.sort(
        key=lambda c: c.recibido or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
        reverse=True,
    )
    return correos


def descargar_adjunto_xls(message_id: str) -> bytes:
    mailbox = settings.MODULACION_LCTPC_MAILBOX
    mid = quote(message_id, safe='')
    data = _get(f'/users/{mailbox}/messages/{mid}/attachments')
    for att in data.get('value', []):
        nombre = (att.get('name') or '').lower()
        if (att.get('@odata.type') == '#microsoft.graph.fileAttachment'
                and nombre.endswith('.xls')):
            contenido_b64 = att.get('contentBytes')
            if not contenido_b64:
                raise GraphError(
                    f'El adjunto .xls del correo {message_id} no trae contentBytes.'
                )
            return base64.b64decode(contenido_b64)
    raise GraphError(f'El correo {message_id} no tiene un adjunto .xls.')
