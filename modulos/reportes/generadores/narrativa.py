"""
IAKasu — Módulo 4: Narrativa ejecutiva para reportes programados.

Genera un párrafo de análisis en lenguaje natural a partir de los KPIs
del reporte usando Claude Haiku. Se invoca desde el management command
generar_reportes, después de obtener los datos del generador.

Nunca lanza excepciones — retorna '' en cualquier caso de falla.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

SISTEMA_NARRATIVA = """
Eres un analista de operaciones de una empresa de transporte de carga pesada en México.
Tu tarea es redactar un párrafo ejecutivo breve que resuma los resultados del reporte
de manera clara y accionable para la gerencia.

Reglas estrictas:
- Máximo 4 oraciones en español neutro y profesional.
- Si hay alertas, problemas o anomalías en los datos, menciónalos primero.
- Menciona los números más relevantes con contexto, no solo los listes.
- Si todo está en orden, indícalo brevemente al final.
- Sin markdown, sin listas, sin encabezados — solo texto corrido.
""".strip()

# Nombres legibles por tipo de reporte para el prompt
_NOMBRES_REPORTE = {
    'ALMACEN_INVENTARIO':    'Inventario general de almacén',
    'ALMACEN_STOCK_CRITICO': 'Stock crítico de almacén',
    'ALMACEN_CADUCIDAD':     'Productos próximos a caducar en almacén',
    'ALMACEN_MOVIMIENTOS':   'Movimientos de almacén (entradas y salidas)',
    'COMBUSTIBLE_CARGAS':    'Cargas de combustible del período',
    'COMBUSTIBLE_CONSUMO':   'Consumo de combustible por unidad',
    'COMBUSTIBLE_ALERTAS':   'Alertas de candado de combustible',
    'UNIDADES_KILOMETRAJE':  'Kilometraje actual de la flota',
}


def _prompt_almacen_movimientos(resumen: dict, periodo_inicio: str, periodo_fin: str) -> tuple:
    """Prompt y max_tokens especializados para el reporte de movimientos de almacén."""
    total = resumen.get('total_movimientos', 0)
    entradas = resumen.get('entradas', 0)
    salidas = resumen.get('salidas', 0)
    top5 = resumen.get('top_5_mas_salidas', 'Sin datos')
    total_sin_mov = resumen.get('total_sin_movimiento', 0)
    sin_mov_muestra = resumen.get('sin_movimiento_muestra', 'Sin datos')

    prompt = (
        f"Reporte: Movimientos de Almacén\n"
        f"Período: {periodo_inicio} al {periodo_fin}\n\n"
        f"Actividad del período:\n"
        f"  - Total movimientos: {total} ({entradas} entradas, {salidas} salidas)\n\n"
        f"Top 5 productos con más salidas:\n"
        f"  {top5}\n\n"
        f"Productos activos sin movimiento en el período: {total_sin_mov}\n"
        f"  Muestra: {sin_mov_muestra}\n\n"
        f"Redacta el análisis ejecutivo del estado del inventario. Menciona los productos "
        f"de alta rotación, señala si hay productos estancados que requieren atención, "
        f"y concluye con una valoración general del flujo del almacén:"
    )
    return prompt, 500


def generar_narrativa(tipo_reporte: str, resumen: dict, periodo_inicio: str, periodo_fin: str) -> str:
    """
    Genera un párrafo ejecutivo en lenguaje natural usando Claude.

    Args:
        tipo_reporte:  Clave del tipo de reporte (ej. 'COMBUSTIBLE_ALERTAS').
        resumen:       Dict con los KPIs del reporte (igual al campo resumen del generador).
        periodo_inicio: Fecha de inicio del período en formato 'YYYY-MM-DD'.
        periodo_fin:    Fecha de fin del período en formato 'YYYY-MM-DD'.

    Returns:
        Texto de la narrativa, o '' si IA está deshabilitada o la llamada falla.
    """
    if not getattr(settings, 'IA_HABILITADA', True):
        return ''

    if not resumen:
        return ''

    try:
        from config.services.claude_service import ClaudeService, Modelo
        claude = ClaudeService()
    except (ValueError, ImportError):
        logger.warning("IAKasu narrativa: ClaudeService no disponible, omitiendo narrativa.")
        return ''

    # Prompt y parámetros según el tipo de reporte
    if tipo_reporte == 'ALMACEN_MOVIMIENTOS':
        prompt, max_tokens = _prompt_almacen_movimientos(resumen, periodo_inicio, periodo_fin)
        modelo = Modelo.SONNET
    else:
        nombre = _NOMBRES_REPORTE.get(tipo_reporte, tipo_reporte.replace('_', ' ').title())
        lineas_resumen = '\n'.join(
            f"  - {k.replace('_', ' ').title()}: {v}"
            for k, v in resumen.items()
        )
        prompt = (
            f"Tipo de reporte: {nombre}\n"
            f"Período: {periodo_inicio} al {periodo_fin}\n\n"
            f"Datos del resumen:\n{lineas_resumen}\n\n"
            f"Redacta el párrafo ejecutivo:"
        )
        max_tokens = 350
        modelo = Modelo.HAIKU

    try:
        return claude.completar(
            prompt=prompt,
            sistema=SISTEMA_NARRATIVA,
            modelo=modelo,
            max_tokens=max_tokens,
        )
    except Exception:
        logger.exception("IAKasu narrativa: error al generar para %s", tipo_reporte)
        return ''
