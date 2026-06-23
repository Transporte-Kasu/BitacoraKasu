"""
Twilio Service — envío de mensajes WhatsApp con plantillas Content API
y correos electrónicos a clientes de bitácoras.
"""

import logging
from django.conf import settings
from django.core.mail import send_mail

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


def enviar_notificacion_bitacora(bitacora, cliente) -> dict:
    """
    Envía WhatsApp (template Twilio) + email al cliente con los datos del viaje.

    Returns dict con claves 'wa_ok' (bool) y 'email_ok' (bool).
    """
    resultado = {'wa_ok': False, 'email_ok': False}

    # ── Construir variables del template ─────────────────────────────────────
    operador = bitacora.operador
    unidad = bitacora.unidad

    es_full = bitacora.modalidad in ('FULL', 'LOCAL_FULL')
    tipo = bitacora.tipo_contenedor or '-'

    # Para FULL los datos se combinan con " - " en un solo campo
    if es_full and bitacora.contenedor_2:
        var1 = f"{bitacora.contenedor or '-'} - {bitacora.contenedor_2}"
    else:
        var1 = bitacora.contenedor or '-'

    var3 = f"{tipo} - {tipo}" if es_full else tipo

    if es_full and bitacora.peso_2:
        var5 = f"{bitacora.peso or '-'} - {bitacora.peso_2}"
    else:
        var5 = str(bitacora.peso or '-')

    var7 = (bitacora.destino or '-').upper()
    var9 = f"{operador.nombre} 📱 {getattr(operador, 'telefono', '')}"
    var10 = f"🚛 {unidad.numero_economico} PLACAS {unidad.placa}"

    hora_salida = bitacora.fecha_salida.strftime('%d/%m/%Y %H:%M HRS') if bitacora.fecha_salida else '-'
    obs = bitacora.observaciones or 'SIN CUSTODIA'
    var11 = f"{obs} 🚩 SALIDA {hora_salida}"
    var12 = 'REPARTO' if bitacora.reparto else 'DIRECTO'

    variables = {
        '1': var1, '3': var3, '5': var5, '7': var7,
        '9': var9, '10': var10, '11': var11, '12': var12,
    }

    # ── WhatsApp ──────────────────────────────────────────────────────────────
    if cliente.celular and settings.TWILIO_CONTENT_SID_BITACORA:
        try:
            client = _twilio_client()
            client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=_numero_wa(cliente.celular),
                content_sid=settings.TWILIO_CONTENT_SID_BITACORA,
                content_variables=str(variables).replace("'", '"'),
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


def _cuerpo_email(bitacora, variables: dict) -> str:
    lineas = [
        "Sistema de Bitácora Kasu 🚛",
        "",
        "── CONTENEDOR ─────────────────",
        f"  {variables['1']}",
        "",
        "── TIPO ───────────────────────",
        f"  {variables['3']} pies",
        "",
        "── PESO ───────────────────────",
        f"  {variables['5']} t",
        "",
        "── DESTINO ────────────────────",
        f"  {variables['7']}",
        "",
        "── OPERADOR ───────────────────",
        f"  {variables['9']}",
        "",
        "── UNIDAD ─────────────────────",
        f"  {variables['10']}",
        "",
        "── OBSERVACIONES ──────────────",
        f"  {variables['11']}",
        f"  {variables['12']}",
        "",
        "Transportes y Logística Kasu",
    ]
    return "\n".join(lineas)
