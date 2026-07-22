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
    'ALMACEN_ANALISIS_INTEGRAL': 'Análisis integral de almacén (asignaciones, entradas, auditoría)',
    'COMBUSTIBLE_CARGAS':    'Cargas de combustible del período',
    'COMBUSTIBLE_CONSUMO':   'Consumo de combustible por unidad',
    'COMBUSTIBLE_ALERTAS':   'Alertas de candado de combustible',
    'UNIDADES_KILOMETRAJE':  'Kilometraje actual de la flota',
}


def _prompt_almacen_movimientos(resumen: dict, datos: dict, periodo_inicio: str, periodo_fin: str) -> tuple:
    """Prompt y max_tokens especializados para el reporte de movimientos de almacén."""
    total = resumen.get('total_movimientos', 0)
    entradas = resumen.get('entradas', 0)
    salidas = resumen.get('salidas', 0)
    ajustes = resumen.get('ajustes_traslados', 0)
    total_activos = resumen.get('total_productos_activos', 0)
    con_mov = resumen.get('productos_con_movimiento', 0)
    total_sin_mov = resumen.get('total_sin_movimiento', 0)

    top5 = datos.get('top_5_salidas', [])
    sin_mov = datos.get('sin_movimiento', [])

    top5_texto = '\n'.join(
        f"  {i+1}. {r['descripcion']} — {r['num_salidas']} salidas"
        for i, r in enumerate(top5)
    ) or '  Sin salidas registradas en el período'

    sin_mov_texto = ', '.join(p['descripcion'] for p in sin_mov) or 'Todos con movimiento'

    pct_activos = f"{round(con_mov / total_activos * 100)}%" if total_activos else 'N/D'

    prompt = (
        f"Reporte: Movimientos de Almacén\n"
        f"Período: {periodo_inicio} al {periodo_fin}\n\n"
        f"Actividad del período:\n"
        f"  - Total movimientos: {total} ({entradas} entradas, {salidas} salidas, {ajustes} ajustes/traslados)\n"
        f"  - Productos activos: {total_activos} | Con movimiento: {con_mov} ({pct_activos}) | Sin movimiento: {total_sin_mov}\n\n"
        f"Top 5 productos con más salidas:\n{top5_texto}\n\n"
        f"Productos sin ningún movimiento en el período ({total_sin_mov} en total):\n"
        f"  Muestra: {sin_mov_texto}\n\n"
        f"Redacta el análisis ejecutivo del estado del inventario. Menciona los productos "
        f"de alta rotación, señala si el volumen de productos estancados es preocupante, "
        f"y concluye con una valoración general del flujo del almacén en el período:"
    )
    return prompt, 500


def _prompt_almacen_analisis_integral(resumen: dict, datos: dict, periodo_inicio: str, periodo_fin: str) -> tuple:
    """Prompt especializado para el reporte de análisis integral de almacén."""
    total_directas = resumen.get('total_asignaciones_directas', 0)
    total_salida = resumen.get('total_asignaciones_salida', 0)
    total_items = resumen.get('total_items_asignados', 0)
    total_entradas = resumen.get('total_entradas', 0)
    entradas_por_tipo = resumen.get('entradas_por_tipo', {})
    valor_entradas = resumen.get('valor_total_entradas', 0)
    total_eventos_auditoria = resumen.get('total_eventos_auditoria', 0)
    alertas_auditoria = resumen.get('alertas_auditoria', [])

    top_destinos = datos.get('top_destinos', [])
    top_usuarios = datos.get('top_usuarios_auditoria', [])

    destinos_texto = '\n'.join(
        f"  {i+1}. {d['destino']} — {d['cantidad_total']} piezas"
        for i, d in enumerate(top_destinos)
    ) or '  Sin asignaciones registradas en el período'

    entradas_texto = '\n'.join(
        f"  - {tipo}: {cantidad}" for tipo, cantidad in entradas_por_tipo.items()
    ) or '  Sin entradas registradas en el período'

    usuarios_texto = '\n'.join(
        f"  {i+1}. {u['usuario']} — {u['total_eventos']} eventos"
        for i, u in enumerate(top_usuarios)
    ) or '  Sin actividad de auditoría en el período'

    alertas_texto = '\n'.join(f"  ⚠ {a}" for a in alertas_auditoria) or '  Sin anomalías detectadas'

    prompt = (
        f"Reporte: Análisis Integral de Almacén\n"
        f"Período: {periodo_inicio} al {periodo_fin}\n\n"
        f"Asignaciones directas de piezas:\n"
        f"  - Asignaciones directas: {total_directas} | Asignaciones de salida: {total_salida} "
        f"| Total de piezas asignadas: {total_items}\n"
        f"  Top destinos que más piezas reciben:\n{destinos_texto}\n\n"
        f"Entradas al almacén:\n"
        f"  - Total entradas: {total_entradas} | Valor total: ${valor_entradas:,.2f} MXN\n"
        f"  Desglose por tipo:\n{entradas_texto}\n\n"
        f"Actividad de auditoría:\n"
        f"  - Total eventos: {total_eventos_auditoria}\n"
        f"  Top usuarios por actividad:\n{usuarios_texto}\n"
        f"  Anomalías detectadas:\n{alertas_texto}\n\n"
        f"Redacta el análisis ejecutivo correlacionando las tres áreas: señala si alguna unidad o "
        f"destino concentra asignaciones directas de forma recurrente (posible falla mecánica "
        f"recurrente), si el volumen de entradas es consistente con la actividad general del "
        f"almacén, y si las anomalías de auditoría ameritan atención de la gerencia:"
    )
    return prompt, 600


def generar_narrativa(
    tipo_reporte: str,
    resumen: dict,
    periodo_inicio: str,
    periodo_fin: str,
    datos: dict = None,
) -> str:
    """
    Genera un párrafo ejecutivo en lenguaje natural usando Claude.

    Args:
        tipo_reporte:  Clave del tipo de reporte (ej. 'COMBUSTIBLE_ALERTAS').
        resumen:       Dict con los KPIs numéricos del reporte.
        periodo_inicio: Fecha de inicio del período en formato 'YYYY-MM-DD'.
        periodo_fin:    Fecha de fin del período en formato 'YYYY-MM-DD'.
        datos:         Dict completo del generador (necesario para tipos con listas).

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
        prompt, max_tokens = _prompt_almacen_movimientos(
            resumen, datos or {}, periodo_inicio, periodo_fin
        )
        modelo = Modelo.SONNET
    elif tipo_reporte == 'ALMACEN_ANALISIS_INTEGRAL':
        prompt, max_tokens = _prompt_almacen_analisis_integral(
            resumen, datos or {}, periodo_inicio, periodo_fin
        )
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
