"""
IAKasu — Notificaciones de alertas de combustible por email.

Envía un email a la gerencia cuando el analizador estadístico detecta
anomalías con score ALTO o CRITICO en una carga de combustible.

Destinatarios configurados en settings.IA_ALERTAS_COMBUSTIBLE_EMAILS.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)

SCORES_QUE_NOTIFICAN = {'ALTO', 'CRITICO'}

ASUNTO_POR_SCORE = {
    'CRITICO': '[CRITICO] Alerta IAKasu — Anomalía grave en carga de combustible',
    'ALTO':    '[ALTO] Alerta IAKasu — Anomalía en carga de combustible',
}


def enviar_alerta_ia_combustible(carga, anomalias_qs, score_riesgo: str, analisis_ia: str = ''):
    """
    Envía un email de alerta IA a los destinatarios configurados.

    Args:
        carga:        Instancia de CargaCombustible recién analizada.
        anomalias_qs: QuerySet o lista de AlertaCombustible generadas por IA.
        score_riesgo: 'ALTO' o 'CRITICO'.
        analisis_ia:  Texto de interpretación de Claude (puede ser vacío).
    """
    if score_riesgo not in SCORES_QUE_NOTIFICAN:
        return

    destinatarios = getattr(settings, 'IA_ALERTAS_COMBUSTIBLE_EMAILS', [])
    if not destinatarios:
        logger.warning("IAKasu: IA_ALERTAS_COMBUSTIBLE_EMAILS vacío, no se envía email.")
        return

    try:
        url_detalle = _construir_url_detalle(carga)
        anomalias_lista = list(anomalias_qs)

        contexto = {
            'alerta': anomalias_lista[0] if anomalias_lista else None,
            'anomalias': anomalias_lista,
            'total_anomalias': len(anomalias_lista),
            'analisis_ia': analisis_ia,
            'url_detalle': url_detalle,
            'score_riesgo': score_riesgo,
        }

        html = render_to_string('combustible/email/alerta_ia.html', contexto)

        asunto = ASUNTO_POR_SCORE.get(score_riesgo, '[Alerta] IAKasu — Combustible')
        asunto += f' — Unidad {carga.unidad.numero_economico}'

        texto_plano = _generar_texto_plano(carga, anomalias_lista, score_riesgo, analisis_ia)

        email = EmailMultiAlternatives(
            subject=asunto,
            body=texto_plano,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=destinatarios,
        )
        email.attach_alternative(html, 'text/html')
        email.send(fail_silently=False)

        logger.info(
            "IAKasu: alerta IA [%s] enviada a %s — carga #%s unidad %s",
            score_riesgo,
            destinatarios,
            carga.pk,
            carga.unidad.numero_economico,
        )

    except Exception as exc:
        # El email nunca debe romper el flujo principal
        logger.exception(
            "IAKasu: error enviando alerta IA para carga #%s — %s",
            carga.pk, exc,
        )


def _construir_url_detalle(carga) -> str:
    """Construye la URL absoluta al detalle de la carga."""
    try:
        ruta = reverse('combustible:detalle', kwargs={'pk': carga.pk})
        base = getattr(settings, 'SITE_URL', 'https://bitacorakasu.com')
        return f"{base.rstrip('/')}{ruta}"
    except Exception:
        return ''


def _generar_texto_plano(carga, anomalias, score_riesgo, analisis_ia) -> str:
    """Versión texto plano del email para clientes que no renderizan HTML."""
    lineas = [
        f"ALERTA IAKASU — RIESGO {score_riesgo}",
        f"Unidad: {carga.unidad.numero_economico}",
        f"Despachador: {carga.despachador.nombre}",
        f"Litros cargados: {carga.cantidad_litros} L",
        f"Fecha: {carga.fecha_hora_inicio.strftime('%d/%m/%Y %H:%M')}",
        f"Kilometraje: {carga.kilometraje_actual} km",
        "",
    ]

    if analisis_ia:
        lineas += ["ANÁLISIS IAKASU:", analisis_ia, ""]

    lineas.append(f"ANOMALÍAS DETECTADAS ({len(anomalias)}):")
    for a in anomalias:
        lineas.append(f"  [{a.get_tipo_alerta_display()}] {a.mensaje}")

    return '\n'.join(lineas)
