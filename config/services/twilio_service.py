"""
Twilio Service — envío de mensajes WhatsApp con plantillas Content API
y correos electrónicos a clientes de bitácoras.
"""

import json
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


_MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']


def _fecha_es(dt) -> str:
    """Formatea datetime como '22 jun 2026 17:00'."""
    if not dt:
        return '-'
    return f"{dt.day} {_MESES[dt.month - 1]} {dt.year} {dt.strftime('%H:%M')}"


def enviar_notificacion_bitacora(bitacora, cliente) -> dict:
    """
    Envía WhatsApp (template Twilio) + email al cliente con los datos del viaje.

    Returns dict con claves 'wa_ok' (bool) y 'email_ok' (bool).
    """
    resultado = {'wa_ok': False, 'email_ok': False}

    # ── Construir variables del template (3 vars) ─────────────────────────────
    operador = bitacora.operador
    unidad = bitacora.unidad
    es_full = bitacora.modalidad in ('FULL', 'LOCAL_FULL')
    tipo = bitacora.tipo_contenedor or '-'
    destino = (bitacora.destino or '-').upper()

    # {{1}} — Información de Carga
    if es_full and bitacora.contenedor_2:
        contenedores = f"{bitacora.contenedor or '-'} / {bitacora.contenedor_2}"
        especificaciones = f"Tipo {tipo} (ambos) con pesos de {bitacora.peso or '-'} y {bitacora.peso_2 or '-'} respectivamente"
    else:
        contenedores = bitacora.contenedor or '-'
        especificaciones = f"Tipo {tipo} con peso de {bitacora.peso or '-'}t"
    var1 = f"• Contenedores: {contenedores}\n• Especificaciones: {especificaciones}\n• Destino Final: {destino}"

    # {{2}} — Detalles del Traslado
    telefono = getattr(operador, 'telefono', '') or ''
    var2 = (
        f"• Unidad: {unidad.numero_economico} (Placas {unidad.placa})\n"
        f"• Operador: {operador.nombre} 📱 {telefono}\n"
        f"• Salida Programada: {_fecha_es(bitacora.fecha_salida)}"
    )

    # {{3}} — Notas Adicionales
    obs = bitacora.observaciones or 'SIN CUSTODIA'
    tipo_servicio = 'REPARTO' if bitacora.reparto else 'DIRECTO'
    var3 = f"Servicio {tipo_servicio} ejecutado {obs}."

    variables = {'1': var1, '2': var2, '3': var3}

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


def _cuerpo_email(bitacora, variables: dict) -> str:
    lineas = [
        "📋 Resumen de Bitácora - Sistema Kasu 🚛",
        "",
        "📦 Información de Carga",
        variables['1'],
        "",
        "🚚 Detalles del Traslado",
        variables['2'],
        "",
        "📝 Notas Adicionales",
        variables['3'],
        "",
        "Gracias por su atención",
        "Transportes y Logística Kasu",
    ]
    return "\n".join(lineas)
