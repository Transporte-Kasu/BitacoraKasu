"""Servicio OCR para lectura de números de candado en fotos de combustible.

Backend: Google Cloud Vision API (TEXT_DETECTION).
Fallback: pytesseract local si no hay API key configurada.
"""

import re
import base64
import logging
import os
from io import BytesIO

logger = logging.getLogger(__name__)

# Patrón: secuencias de 4 o más dígitos consecutivos (número de serie del candado)
_PATRON_CANDADO = re.compile(r'\d{4,}')


def _leer_bytes_imagen(imagen_field) -> bytes | None:
    """Lee los bytes de un ImageField (local o DigitalOcean Spaces)."""
    try:
        with imagen_field.storage.open(imagen_field.name, 'rb') as f:
            return f.read()
    except Exception as exc:
        logger.warning("OCR: no se pudo abrir imagen '%s': %s", imagen_field.name, exc)
        return None


def _extraer_numero(texto: str) -> str:
    """Devuelve el primer número de 4+ dígitos encontrado en el texto, o ''."""
    candidatos = _PATRON_CANDADO.findall(texto)
    return candidatos[0] if candidatos else ''


# ---------------------------------------------------------------------------
# Backend principal: Google Cloud Vision API
# ---------------------------------------------------------------------------

def _leer_con_vision_api(imagen_bytes: bytes, api_key: str) -> str:
    """
    Envía la imagen a Google Cloud Vision TEXT_DETECTION y devuelve el número.
    Usa requests (ya en requirements.txt), sin SDK adicional.
    """
    import requests

    url = f'https://vision.googleapis.com/v1/images:annotate?key={api_key}'
    payload = {
        'requests': [{
            'image': {'content': base64.b64encode(imagen_bytes).decode('utf-8')},
            'features': [{'type': 'TEXT_DETECTION', 'maxResults': 1}],
        }]
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        anotaciones = data.get('responses', [{}])[0].get('textAnnotations', [])
        if not anotaciones:
            return ''

        # La primera anotación contiene todo el texto detectado
        texto_completo = anotaciones[0].get('description', '')
        return _extraer_numero(texto_completo)

    except requests.exceptions.RequestException as exc:
        logger.error("OCR Vision API: error de red para '%s': %s", exc, exc)
        return ''
    except Exception as exc:
        logger.error("OCR Vision API: error inesperado: %s", exc)
        return ''


# ---------------------------------------------------------------------------
# Fallback: pytesseract local
# ---------------------------------------------------------------------------

def _leer_con_tesseract(imagen_bytes: bytes, nombre: str) -> str:
    """Fallback con pytesseract cuando no hay API key de Vision configurada."""
    try:
        import pytesseract
    except ImportError:
        logger.warning("OCR: pytesseract no instalado y no hay GOOGLE_VISION_API_KEY.")
        return ''

    from PIL import Image, ImageEnhance, ImageFilter

    try:
        img = Image.open(BytesIO(imagen_bytes))
        ancho, alto = img.size

        regiones = [
            img,
            img.crop((0, int(alto * 0.45), ancho, alto)),
            img.crop((0, int(alto * 0.65), ancho, alto)),
        ]

        configs = [
            r'--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789',
            r'--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789',
            r'--psm 11 --oem 3 -c tessedit_char_whitelist=0123456789',
        ]

        for region in regiones:
            gray = region.convert('L')
            w, h = gray.size
            if w < 1200:
                factor = 1200 / w
                gray = gray.resize((int(w * factor), int(h * factor)), Image.LANCZOS)

            realzada = ImageEnhance.Contrast(gray).enhance(3.0)
            realzada = ImageEnhance.Sharpness(realzada).enhance(3.0)

            variantes = []
            for umbral in [90, 128, 160]:
                bin_img = realzada.point(lambda p, u=umbral: 255 if p > u else 0)
                variantes.append(bin_img)
                variantes.append(bin_img.point(lambda p: 255 - p))
            variantes.append(gray.filter(ImageFilter.FIND_EDGES))

            for variante in variantes:
                for config in configs:
                    try:
                        texto = pytesseract.image_to_string(variante, config=config)
                        numero = _extraer_numero(texto)
                        if numero:
                            return numero
                    except Exception:
                        continue

        return ''

    except Exception as exc:
        logger.error("OCR tesseract: error procesando '%s': %s", nombre, exc)
        return ''


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def leer_numero_candado(imagen_field) -> str:
    """
    Extrae el número de candado de un ImageField.

    Usa Google Cloud Vision API si GOOGLE_VISION_API_KEY está configurado.
    Si no, hace fallback a pytesseract local.

    Devuelve la primera secuencia de 4+ dígitos encontrada, o ''.
    """
    imagen_bytes = _leer_bytes_imagen(imagen_field)
    if imagen_bytes is None:
        return ''

    api_key = os.environ.get('GOOGLE_VISION_API_KEY', '')

    if api_key:
        numero = _leer_con_vision_api(imagen_bytes, api_key)
        logger.info(
            "OCR Vision API — '%s': '%s'",
            imagen_field.name, numero or '(no detectado)',
        )
        return numero

    # Sin API key: fallback a tesseract
    logger.warning(
        "OCR: GOOGLE_VISION_API_KEY no configurada, usando tesseract para '%s'",
        imagen_field.name,
    )
    return _leer_con_tesseract(imagen_bytes, imagen_field.name)
