"""
Twilio Service — envío de mensajes WhatsApp con plantillas Content API
y correos electrónicos a clientes de bitácoras.
"""

import json
import logging
import re
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone as dj_timezone

logger = logging.getLogger(__name__)


def _twilio_client():
    from twilio.rest import Client
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def _numero_wa(celular: str) -> str:
    """Normaliza celular a formato whatsapp:+521XXXXXXXXXX"""
    numero = celular.strip().replace(' ', '').replace('-', '')
    if not numero.startswith('+'):
        numero = '+' + numero
    if not numero.startswith('whatsapp:'):
        numero = 'whatsapp:' + numero
    return numero


def _numero_wa_mx(telefono: str) -> str:
    """
    Normaliza teléfono de operador a formato whatsapp:+521XXXXXXXXXX.
    Si son 10 dígitos (formato actual de Operador.telefono), antepone
    '521' (México + WhatsApp) automáticamente. Si ya trae código de país,
    se respeta tal cual (mismo comportamiento que _numero_wa).
    """
    numero = telefono.strip().replace(' ', '').replace('-', '')
    solo_digitos = numero.lstrip('+')
    if solo_digitos.isdigit() and len(solo_digitos) == 10:
        numero = '521' + solo_digitos
    return _numero_wa(numero)


def _sanitizar_texto(texto: str) -> str:
    """
    Normaliza texto libre para Content Variables de Twilio.

    Twilio rechaza (error 21656) cualquier variable que contenga saltos de
    línea, tabs, o más de cuatro espacios consecutivos. Los saltos de línea
    se convierten en ' | ' (mismo separador ya usado entre sub-campos en
    otras variables); tabs y espacios largos colapsan a un solo espacio.
    """
    if not texto:
        return texto
    texto = re.sub(r'[\r\n]+', ' | ', texto)
    texto = re.sub(r'\t+', ' ', texto)
    texto = re.sub(r' {5,}', ' ', texto)
    return texto.strip(' |')


_MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']


def _fecha_es(dt) -> str:
    """Formatea datetime como '22 jun 2026 17:00' (convertido a hora local)."""
    if not dt:
        return '-'
    if dj_timezone.is_aware(dt):
        dt = dj_timezone.localtime(dt)
    return f"{dt.day} {_MESES[dt.month - 1]} {dt.year} {dt.strftime('%H:%M')}"


def _var_info_carga(bitacora) -> str:
    """{{1}} — Información de Carga (contenedores, tipo, peso)."""
    es_full = bitacora.modalidad in ('FULL', 'LOCAL_FULL')
    tipo = bitacora.tipo_contenedor or '-'
    destino = _sanitizar_texto(bitacora.destino or '-').upper()

    if es_full and bitacora.contenedor_2:
        contenedores = f"{bitacora.contenedor or '-'} / {bitacora.contenedor_2}"
        especificaciones = f"Tipo {tipo} (ambos) con pesos de {bitacora.peso or '-'} y {bitacora.peso_2 or '-'} respectivamente"
    else:
        contenedores = bitacora.contenedor or '-'
        especificaciones = f"Tipo {tipo} con peso de {bitacora.peso or '-'}t"

    return f"Contenedores: {contenedores} | Especificaciones: {especificaciones} | Destino Final: {destino}"


def _enviar_wa_y_email_cliente(bitacora, cliente, variables: dict) -> dict:
    """
    Envía WhatsApp (template Twilio) + email a `cliente` con `variables` ya armadas.
    Mecanismo compartido entre la notificación combinada y las notificaciones
    divididas por contenedor (reparto).
    """
    resultado = {'wa_ok': False, 'email_ok': False}

    # ── WhatsApp ──────────────────────────────────────────────────────────────
    if cliente.celular and settings.TWILIO_CONTENT_SID_BITACORA:
        try:
            client = _twilio_client()
            client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=_numero_wa(cliente.celular),
                content_sid=settings.TWILIO_CONTENT_SID_BITACORA,
                content_variables=json.dumps(variables, ensure_ascii=False),
            )
            resultado['wa_ok'] = True
            logger.info("WA enviado a cliente %s (%s)", cliente.nombre, cliente.celular)
        except Exception as exc:
            logger.error("Error WA Twilio para cliente %s: %s", cliente.nombre, exc)
    else:
        if not cliente.celular:
            logger.warning("Cliente %s sin celular — WA omitido.", cliente.nombre)
        if not settings.TWILIO_CONTENT_SID_BITACORA:
            logger.warning("TWILIO_CONTENT_SID_BITACORA no configurado.")

    # ── Email ─────────────────────────────────────────────────────────────────
    if cliente.email:
        try:
            asunto = f"Programación de contenedores — {bitacora.fecha_salida.strftime('%d/%m/%Y') if bitacora.fecha_salida else ''}"
            cuerpo = _cuerpo_email(bitacora, variables)
            send_mail(
                subject=asunto,
                message=cuerpo,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[cliente.email],
                fail_silently=False,
            )
            resultado['email_ok'] = True
            logger.info("Email enviado a cliente %s (%s)", cliente.nombre, cliente.email)
        except Exception as exc:
            logger.error("Error email para cliente %s: %s", cliente.nombre, exc)
    else:
        logger.warning("Cliente %s sin email — correo omitido.", cliente.nombre)

    return resultado


def enviar_notificacion_bitacora(bitacora, cliente) -> dict:
    """
    Envía WhatsApp (template Twilio) + email al cliente con los datos del viaje.

    Returns dict con claves 'wa_ok' (bool) y 'email_ok' (bool).
    """
    operador = bitacora.operador
    unidad = bitacora.unidad
    var1 = _var_info_carga(bitacora)

    # {{2}} — Detalles del Traslado
    telefono = getattr(operador, 'telefono', '') or ''
    var2 = (
        f"Unidad: {unidad.numero_economico} (Placas {unidad.placa}) | "
        f"Operador: {operador.nombre} {telefono} | "
        f"Salida: {_fecha_es(bitacora.fecha_salida)}"
    )

    # {{3}} — Notas Adicionales
    obs = _sanitizar_texto(bitacora.observaciones or 'SIN CUSTODIA')
    tipo_servicio = 'REPARTO' if bitacora.reparto else 'DIRECTO'
    var3 = f"Servicio {tipo_servicio} ejecutado {obs}."

    variables = {'1': var1, '2': var2, '3': var3}

    return _enviar_wa_y_email_cliente(bitacora, cliente, variables)


def _var_info_carga_contenedor(bitacora, numero) -> str:
    """{{1}} para un solo contenedor — usado en notificaciones de reparto."""
    if numero == 2:
        contenedor = bitacora.contenedor_2 or '-'
        peso = bitacora.peso_2 or '-'
        cp_destino = bitacora.cp_destino_2 or '-'
    else:
        contenedor = bitacora.contenedor or '-'
        peso = bitacora.peso or '-'
        cp_destino = bitacora.cp_destino or '-'

    tipo = bitacora.tipo_contenedor or '-'
    especificaciones = f"Tipo {tipo} con peso de {peso}t"

    return f"Contenedor: {contenedor} | Especificaciones: {especificaciones} | Destino Final: CP {cp_destino}"


def _enviar_notificacion_contenedor(bitacora, numero, cliente, fecha_entrega) -> dict:
    """Arma variables para un solo contenedor (con su propio horario de entrega) y envía WA+email."""
    operador = bitacora.operador
    unidad = bitacora.unidad
    var1 = _var_info_carga_contenedor(bitacora, numero)

    telefono = getattr(operador, 'telefono', '') or ''
    var2 = (
        f"Unidad: {unidad.numero_economico} (Placas {unidad.placa}) | "
        f"Operador: {operador.nombre} {telefono} | "
        f"Salida: {_fecha_es(bitacora.fecha_salida)} | "
        f"Entrega: {_fecha_es(fecha_entrega)}"
    )

    obs = _sanitizar_texto(bitacora.observaciones or 'SIN CUSTODIA')
    var3 = f"Servicio REPARTO ejecutado (contenedor {numero}) {obs}."

    variables = {'1': var1, '2': var2, '3': var3}
    return _enviar_wa_y_email_cliente(bitacora, cliente, variables)


def enviar_notificaciones_reparto(bitacora) -> dict:
    """
    Envía dos notificaciones de cliente independientes (una por contenedor)
    para viajes con reparto=True. Cada una usa los datos propios de su
    contenedor (destino, cliente, horario de entrega), con fallback al
    contenedor 1 cuando el campo _2 correspondiente está vacío.

    Returns dict: {'contenedor_1': {...} | None, 'contenedor_2': {...} | None},
    mismo formato de resultado que enviar_notificacion_bitacora en cada entrada
    (None cuando ese contenedor no tiene cliente asignado).
    """
    resultado = {'contenedor_1': None, 'contenedor_2': None}

    if bitacora.cliente:
        resultado['contenedor_1'] = _enviar_notificacion_contenedor(
            bitacora, numero=1, cliente=bitacora.cliente,
            fecha_entrega=bitacora.fecha_hora_entrega,
        )

    cliente_2 = bitacora.cliente_2 or bitacora.cliente
    if cliente_2:
        resultado['contenedor_2'] = _enviar_notificacion_contenedor(
            bitacora, numero=2, cliente=cliente_2,
            fecha_entrega=bitacora.fecha_hora_entrega_2 or bitacora.fecha_hora_entrega,
        )

    return resultado


def enviar_notificacion_operador(bitacora) -> dict:
    """
    Envía WhatsApp (mismo template Twilio que cliente) al operador asignado
    con los datos de su próximo viaje.

    Returns dict con clave 'wa_ok' (bool).
    """
    resultado = {'wa_ok': False}
    operador = bitacora.operador
    unidad = bitacora.unidad

    var1 = _var_info_carga(bitacora)

    # {{2}} — Detalles del Traslado (versión operador: destino + horario de salida + unidad)
    destino = _sanitizar_texto(bitacora.destino or '-').upper()
    var2 = f"Destino: {destino} | Horario de Salida: {_fecha_es(bitacora.fecha_salida)} | Unidad: {unidad.numero_economico} (Placas {unidad.placa})"

    # {{3}} — Notas Adicionales (igual que cliente)
    obs = _sanitizar_texto(bitacora.observaciones or 'SIN CUSTODIA')
    tipo_servicio = 'REPARTO' if bitacora.reparto else 'DIRECTO'
    var3 = f"Servicio {tipo_servicio} ejecutado {obs}."

    variables = {'1': var1, '2': var2, '3': var3}

    telefono = (operador.telefono or '').strip()
    if telefono and settings.TWILIO_CONTENT_SID_BITACORA:
        try:
            client = _twilio_client()
            client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=_numero_wa_mx(telefono),
                content_sid=settings.TWILIO_CONTENT_SID_BITACORA,
                content_variables=json.dumps(variables, ensure_ascii=False),
            )
            resultado['wa_ok'] = True
            logger.info("WA enviado a operador %s (%s)", operador.nombre, telefono)
        except Exception as exc:
            logger.error("Error WA Twilio para operador %s: %s", operador.nombre, exc)
    else:
        if not telefono:
            logger.warning("Operador %s sin teléfono — WA omitido.", operador.nombre)
        if not settings.TWILIO_CONTENT_SID_BITACORA:
            logger.warning("TWILIO_CONTENT_SID_BITACORA no configurado.")

    return resultado


def _cuerpo_email(bitacora, variables: dict) -> str:
    # El email sí puede usar saltos de línea; reemplazamos los separadores pipe
    def expand(v):
        return v.replace(' | ', '\n  ')

    # Notas Adicionales usa bitacora.observaciones directo (no variables['3']),
    # que viene saneado (sin saltos de línea reales) para WhatsApp/Twilio.
    tipo_servicio = 'REPARTO' if bitacora.reparto else 'DIRECTO'
    obs_email = bitacora.observaciones or 'SIN CUSTODIA'

    lineas = [
        "Resumen de Bitacora - Sistema Kasu",
        "",
        "INFORMACION DE CARGA",
        f"  {expand(variables['1'])}",
        "",
        "DETALLES DEL TRASLADO",
        f"  {expand(variables['2'])}",
        "",
        "NOTAS ADICIONALES",
        f"  Servicio {tipo_servicio} ejecutado {obs_email}.",
        "",
        "Transportes y Logistica Kasu",
    ]
    return "\n".join(lineas)
