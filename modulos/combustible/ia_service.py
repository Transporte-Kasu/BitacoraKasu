"""
IAKasu — Sprint 1: Análisis estadístico de anomalías en cargas de combustible.

Detecta patrones atípicos comparando cada carga contra el historial propio
de la unidad (últimos 90 días). No requiere API externa.

Anomalías detectadas:
  - CONSUMO_ATIPICO       : litros cargados fuera del rango histórico (z-score)
  - RENDIMIENTO_ANOMALO   : km/lt por debajo del percentil histórico de la unidad
  - TIEMPO_CARGA_ATIPICO  : duración de carga inusualmente alta
  - NIVEL_INCONSISTENTE   : nivel_combustible_inicial incompatible con litros cargados
  - PATRON_DESPACHADOR    : despachador con alta concentración de cargas con alertas
"""

import logging
import statistics
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Scores que activan la llamada a Claude API (configurado en settings.IA_SCORE_MINIMO_CLAUDE)
_SCORES_CON_CLAUDE = {'ALTO', 'CRITICO'}

SISTEMA_ANALISTA = """
Eres un analista experto en operación de flotas de transporte de carga pesada en México.
Tu rol es revisar anomalías detectadas automáticamente en cargas de diésel y emitir un
diagnóstico breve en español para el equipo de gerencia.

Reglas de formato:
- Máximo 3 oraciones.
- Directo y concreto: qué ocurrió, por qué es relevante y qué acción se recomienda.
- Tono ejecutivo, sin tecnicismos estadísticos.
- No uses markdown ni listas, solo texto corrido.
""".strip()

# ---------------------------------------------------------------------------
# Constantes de configuración
# ---------------------------------------------------------------------------

VENTANA_HISTORICA_DIAS = 90       # días hacia atrás para calcular la línea base
MIN_CARGAS_PARA_ANALISIS = 5      # mínimo de cargas históricas para emitir alertas
UMBRAL_SIGMA = 2.0                # z-score a partir del cual se considera anomalía
VENTANA_DESPACHADOR_DIAS = 30     # días para evaluar el patrón por despachador
MIN_CARGAS_DESPACHADOR = 3        # mínimo de cargas del despachador para el análisis

# Puntaje por tipo de anomalía — determina el score_riesgo final
PUNTOS_ANOMALIA = {
    'CONSUMO_ATIPICO_EXTREMO':    3,   # z > 3.0
    'CONSUMO_ATIPICO':            2,   # z > UMBRAL_SIGMA
    'RENDIMIENTO_ANOMALO_EXTREMO': 3,
    'RENDIMIENTO_ANOMALO':        2,
    'NIVEL_INCONSISTENTE':        2,
    'PATRON_DESPACHADOR':         2,
    'TIEMPO_CARGA_ATIPICO':       1,
}

SCORE_THRESHOLDS = {
    'CRITICO': 5,
    'ALTO':    3,
    'MEDIO':   1,
}

# Mapa de nivel_combustible_inicial a porcentaje estimado del tanque
# Rango razonable de rendimiento para vehículos de carga pesada (km/lt)
# Filtra outliers causados por grandes diferencias entre odómetros consecutivos
RENDIMIENTO_MIN_KM_LT = 0.5
RENDIMIENTO_MAX_KM_LT = 12.0

NIVEL_A_PORCENTAJE = {
    'VACIO':         0.02,
    'CUARTO':        0.25,
    'MEDIO':         0.50,
    'TRES_CUARTOS':  0.75,
}


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class AnalizadorCombustible:
    """
    Analiza una carga recién completada contra el historial de su unidad
    y emite alertas estadísticas sin depender de umbrales fijos.

    Uso:
        analizador = AnalizadorCombustible()
        resultado = analizador.analizar_carga(carga)
        # resultado = {
        #     'anomalias': [...],
        #     'score_riesgo': 'ALTO' | 'MEDIO' | 'BAJO' | None,
        #     'total_puntos': int,
        # }
    """

    def analizar_carga(self, carga) -> dict:
        """
        Punto de entrada principal. Retorna dict con anomalías detectadas,
        score de riesgo global e interpretación de Claude (si aplica).
        """
        anomalias = []

        stats = self._calcular_estadisticas_unidad(carga.unidad)

        if stats['suficientes_datos']:
            anomalias += self._detectar_consumo_atipico(carga, stats)
            anomalias += self._detectar_rendimiento_anomalo(carga, stats)
            anomalias += self._detectar_tiempo_atipico(carga, stats)

        anomalias += self._detectar_nivel_inconsistente(carga)
        anomalias += self._detectar_patron_despachador(carga)

        score_riesgo, total_puntos = self._calcular_score(anomalias)

        # Llamar a Claude solo para scores ALTO y CRITICO
        interpretacion = ''
        if anomalias and score_riesgo in _SCORES_CON_CLAUDE:
            interpretacion = self.generar_interpretacion(carga, anomalias, score_riesgo, stats)

        if anomalias:
            logger.info(
                "IAKasu combustible — unidad %s carga #%s: %d anomalía(s) score=%s claude=%s",
                carga.unidad.numero_economico,
                carga.pk,
                len(anomalias),
                score_riesgo,
                'sí' if interpretacion else 'no',
            )

        return {
            'anomalias': anomalias,
            'score_riesgo': score_riesgo,
            'total_puntos': total_puntos,
            'interpretacion': interpretacion,
        }

    def generar_interpretacion(self, carga, anomalias: list, score_riesgo: str, stats: dict) -> str:
        """
        Llama a Claude Sonnet para generar un análisis ejecutivo en lenguaje
        natural de las anomalías detectadas.

        Solo se invoca cuando score_riesgo está en _SCORES_CON_CLAUDE.
        Retorna '' si IA está deshabilitada o si la llamada falla.
        """
        from django.conf import settings
        from config.services.claude_service import ClaudeService, Modelo

        if not getattr(settings, 'IA_HABILITADA', True):
            return ''

        score_minimo = getattr(settings, 'IA_SCORE_MINIMO_CLAUDE', 'ALTO')
        orden_scores = ['BAJO', 'MEDIO', 'ALTO', 'CRITICO']
        if orden_scores.index(score_riesgo) < orden_scores.index(score_minimo):
            return ''

        try:
            claude = ClaudeService()
        except ValueError:
            logger.warning("IAKasu: ANTHROPIC_API_KEY no configurada, omitiendo interpretación.")
            return ''

        # Construir resumen de anomalías para el prompt
        resumen_anomalias = '\n'.join(
            f"- {a['tipo_alerta']}: {a['mensaje']}"
            for a in anomalias
        )

        historial = ''
        if stats.get('suficientes_datos'):
            historial = (
                f"Historial (últimos 90 días, {stats['n']} cargas): "
                f"promedio {stats['media_litros']:.1f} L/carga"
            )
            if stats.get('media_rendimiento'):
                historial += f", rendimiento promedio {stats['media_rendimiento']:.2f} km/lt"
            if stats.get('media_tiempo'):
                historial += f", tiempo promedio {stats['media_tiempo']:.0f} min"

        prompt = (
            f"Unidad: {carga.unidad.numero_economico} "
            f"({carga.unidad.marca} {carga.unidad.modelo} {carga.unidad.año}, "
            f"tipo {carga.unidad.tipo})\n"
            f"Fecha de carga: {carga.fecha_hora_inicio.strftime('%d/%m/%Y %H:%M')}\n"
            f"Despachador: {carga.despachador.nombre}\n"
            f"Litros cargados: {carga.cantidad_litros} L\n"
            f"Kilometraje registrado: {carga.kilometraje_actual:,} km\n"
            f"{historial}\n\n"
            f"Nivel de riesgo detectado: {score_riesgo}\n\n"
            f"Anomalías detectadas:\n{resumen_anomalias}\n\n"
            f"Genera el análisis ejecutivo:"
        )

        return claude.completar(
            prompt=prompt,
            sistema=SISTEMA_ANALISTA,
            modelo=Modelo.SONNET,
            max_tokens=300,
        )

    # ------------------------------------------------------------------
    # Estadísticas históricas de la unidad
    # ------------------------------------------------------------------

    def _calcular_estadisticas_unidad(self, unidad) -> dict:
        """
        Calcula μ y σ de litros, tiempo_carga_minutos y rendimiento (km/lt)
        para la unidad en los últimos VENTANA_HISTORICA_DIAS días.

        Retorna un dict con las métricas y el flag 'suficientes_datos'.
        """
        from modulos.combustible.models import CargaCombustible

        fecha_limite = timezone.now() - timedelta(days=VENTANA_HISTORICA_DIAS)
        cargas_qs = (
            CargaCombustible.objects
            .filter(
                unidad=unidad,
                estado='COMPLETADO',
                fecha_hora_inicio__gte=fecha_limite,
            )
            .order_by('fecha_hora_inicio')
            .values('id', 'cantidad_litros', 'tiempo_carga_minutos', 'kilometraje_actual')
        )
        cargas = list(cargas_qs)

        if len(cargas) < MIN_CARGAS_PARA_ANALISIS:
            return {'suficientes_datos': False, 'n': len(cargas)}

        litros = [float(c['cantidad_litros']) for c in cargas]
        tiempos = [c['tiempo_carga_minutos'] for c in cargas if c['tiempo_carga_minutos'] is not None]

        # Rendimiento: km desde la carga anterior / litros de esta carga
        rendimientos = self._calcular_serie_rendimientos(cargas)

        stats = {
            'suficientes_datos': True,
            'n': len(cargas),
            # Litros
            'media_litros': statistics.mean(litros),
            'std_litros': statistics.stdev(litros) if len(litros) > 1 else 0,
        }

        if tiempos and len(tiempos) >= MIN_CARGAS_PARA_ANALISIS:
            stats['media_tiempo'] = statistics.mean(tiempos)
            stats['std_tiempo'] = statistics.stdev(tiempos) if len(tiempos) > 1 else 0
        else:
            stats['media_tiempo'] = None
            stats['std_tiempo'] = None

        if rendimientos and len(rendimientos) >= MIN_CARGAS_PARA_ANALISIS:
            stats['media_rendimiento'] = statistics.mean(rendimientos)
            stats['std_rendimiento'] = statistics.stdev(rendimientos) if len(rendimientos) > 1 else 0
            stats['p10_rendimiento'] = self._percentil(rendimientos, 10)
        else:
            stats['media_rendimiento'] = None
            stats['std_rendimiento'] = None
            stats['p10_rendimiento'] = None

        return stats

    def _calcular_serie_rendimientos(self, cargas_ordenadas: list) -> list:
        """
        Calcula km/lt entre cargas consecutivas con kilometraje válido (>0).
        """
        rendimientos = []
        cargas_con_km = [c for c in cargas_ordenadas if c['kilometraje_actual'] > 0]

        for i in range(1, len(cargas_con_km)):
            km_anterior = cargas_con_km[i - 1]['kilometraje_actual']
            km_actual = cargas_con_km[i]['kilometraje_actual']
            litros = float(cargas_con_km[i]['cantidad_litros'])

            km_recorridos = km_actual - km_anterior
            if km_recorridos > 0 and litros > 0:
                rendimiento = km_recorridos / litros
                # Filtrar valores fuera del rango físicamente posible para vehículos de carga
                if RENDIMIENTO_MIN_KM_LT <= rendimiento <= RENDIMIENTO_MAX_KM_LT:
                    rendimientos.append(rendimiento)

        return rendimientos

    # ------------------------------------------------------------------
    # Detección de anomalías individuales
    # ------------------------------------------------------------------

    def _detectar_consumo_atipico(self, carga, stats: dict) -> list:
        """
        Detecta si los litros cargados son atípicos respecto al historial.
        Solo alerta en exceso (no en defecto) para evitar falsos positivos
        en cargas parciales.
        """
        if stats['std_litros'] == 0:
            return []

        litros = float(carga.cantidad_litros)
        z = (litros - stats['media_litros']) / stats['std_litros']

        if z <= UMBRAL_SIGMA:
            return []

        tipo_interno = 'CONSUMO_ATIPICO_EXTREMO' if z > 3.0 else 'CONSUMO_ATIPICO'
        exceso_pct = ((litros - stats['media_litros']) / stats['media_litros']) * 100

        mensaje = (
            f"Unidad {carga.unidad.numero_economico}: se cargaron {litros:.1f} L, "
            f"un {exceso_pct:.0f}% por encima del promedio histórico de "
            f"{stats['media_litros']:.1f} L (±{stats['std_litros']:.1f} L, "
            f"n={stats['n']} cargas en 90 días). "
            f"Despachador: {carga.despachador.nombre}."
        )

        return [{
            'tipo_alerta': 'CONSUMO_ATIPICO',
            'tipo_interno': tipo_interno,
            'mensaje': mensaje,
            'datos_estadisticos': {
                'media': round(stats['media_litros'], 2),
                'std': round(stats['std_litros'], 2),
                'valor': round(litros, 2),
                'z_score': round(z, 2),
                'n_historico': stats['n'],
            },
        }]

    def _detectar_rendimiento_anomalo(self, carga, stats: dict) -> list:
        """
        Detecta rendimiento (km/lt) por debajo del percentil 10 histórico
        de la unidad. Solo aplica si la carga tiene km válido (>0).
        """
        if carga.kilometraje_actual == 0 or stats.get('p10_rendimiento') is None:
            return []

        from modulos.combustible.models import CargaCombustible

        carga_anterior = (
            CargaCombustible.objects
            .filter(
                unidad=carga.unidad,
                estado='COMPLETADO',
                kilometraje_actual__gt=0,
            )
            .exclude(pk=carga.pk)
            .order_by('-fecha_hora_inicio')
            .first()
        )
        if not carga_anterior or carga.kilometraje_actual <= carga_anterior.kilometraje_actual:
            return []

        km_recorridos = carga.kilometraje_actual - carga_anterior.kilometraje_actual
        litros = float(carga.cantidad_litros)
        if litros == 0:
            return []

        rendimiento = km_recorridos / litros

        if rendimiento >= stats['p10_rendimiento']:
            return []

        # z-score negativo (bajo rendimiento)
        if stats['std_rendimiento'] and stats['std_rendimiento'] > 0:
            z = (rendimiento - stats['media_rendimiento']) / stats['std_rendimiento']
        else:
            z = -99

        tipo_interno = 'RENDIMIENTO_ANOMALO_EXTREMO' if z < -3.0 else 'RENDIMIENTO_ANOMALO'
        diferencia_pct = ((stats['media_rendimiento'] - rendimiento) / stats['media_rendimiento']) * 100

        mensaje = (
            f"Unidad {carga.unidad.numero_economico}: rendimiento de {rendimiento:.2f} km/lt "
            f"en este tramo ({km_recorridos:,} km / {litros:.1f} L), un {diferencia_pct:.0f}% "
            f"por debajo del promedio histórico de {stats['media_rendimiento']:.2f} km/lt "
            f"(p10={stats['p10_rendimiento']:.2f} km/lt, n={stats['n']} cargas). "
            f"Verificar estado mecánico de la unidad."
        )

        return [{
            'tipo_alerta': 'RENDIMIENTO_ANOMALO',
            'tipo_interno': tipo_interno,
            'mensaje': mensaje,
            'datos_estadisticos': {
                'media': round(stats['media_rendimiento'], 3),
                'std': round(stats['std_rendimiento'], 3) if stats['std_rendimiento'] else None,
                'p10': round(stats['p10_rendimiento'], 3),
                'valor': round(rendimiento, 3),
                'z_score': round(z, 2),
                'km_recorridos': km_recorridos,
                'n_historico': stats['n'],
            },
        }]

    def _detectar_tiempo_atipico(self, carga, stats: dict) -> list:
        """
        Detecta tiempo de carga inusualmente alto (z-score > UMBRAL_SIGMA).
        Tiempos bajos no se alertan (podría ser carga parcial o error del reloj).
        """
        if (carga.tiempo_carga_minutos is None
                or stats.get('media_tiempo') is None
                or stats.get('std_tiempo') is None
                or stats['std_tiempo'] == 0):
            return []

        tiempo = carga.tiempo_carga_minutos
        z = (tiempo - stats['media_tiempo']) / stats['std_tiempo']

        if z <= UMBRAL_SIGMA:
            return []

        mensaje = (
            f"Unidad {carga.unidad.numero_economico}: tiempo de carga de {tiempo} min, "
            f"un {z:.1f}σ por encima del promedio histórico de "
            f"{stats['media_tiempo']:.0f} min (±{stats['std_tiempo']:.0f} min). "
            f"Despachador: {carga.despachador.nombre}. "
            f"Verificar si hubo incidencia durante la carga."
        )

        return [{
            'tipo_alerta': 'TIEMPO_CARGA_ATIPICO',
            'tipo_interno': 'TIEMPO_CARGA_ATIPICO',
            'mensaje': mensaje,
            'datos_estadisticos': {
                'media': round(stats['media_tiempo'], 1),
                'std': round(stats['std_tiempo'], 1),
                'valor': tiempo,
                'z_score': round(z, 2),
                'n_historico': stats['n'],
            },
        }]

    def _detectar_nivel_inconsistente(self, carga) -> list:
        """
        Detecta inconsistencia entre el nivel_combustible_inicial reportado
        y los litros cargados.

        Si el nivel inicial es alto (TRES_CUARTOS) pero se cargaron muchos litros
        (más de lo que el espacio disponible estimado permitiría), hay inconsistencia.
        Solo aplica a flujo completo (tiene nivel_combustible_inicial).
        """
        if not carga.nivel_combustible_inicial:
            return []

        if not carga.unidad.capacidad_combustible:
            return []

        capacidad = float(carga.unidad.capacidad_combustible)
        nivel_pct = NIVEL_A_PORCENTAJE.get(carga.nivel_combustible_inicial, 0)
        espacio_estimado = capacidad * (1 - nivel_pct)

        # Margen del 25% para absorber variaciones normales de medición
        limite_razonable = espacio_estimado * 1.25
        litros = float(carga.cantidad_litros)

        if litros <= limite_razonable:
            return []

        mensaje = (
            f"Unidad {carga.unidad.numero_economico}: nivel inicial reportado como "
            f"'{carga.get_nivel_combustible_inicial_display()}' "
            f"({nivel_pct*100:.0f}% del tanque), pero se cargaron {litros:.1f} L. "
            f"Con un tanque de {capacidad:.0f} L, el espacio disponible estimado es "
            f"{espacio_estimado:.0f} L. "
            f"Verificar si el nivel fue reportado correctamente."
        )

        return [{
            'tipo_alerta': 'NIVEL_INCONSISTENTE',
            'tipo_interno': 'NIVEL_INCONSISTENTE',
            'mensaje': mensaje,
            'datos_estadisticos': {
                'capacidad_tanque': capacidad,
                'nivel_inicial': carga.nivel_combustible_inicial,
                'nivel_pct': nivel_pct,
                'espacio_estimado': round(espacio_estimado, 1),
                'limite_razonable': round(limite_razonable, 1),
                'litros_cargados': round(litros, 1),
            },
        }]

    def _detectar_patron_despachador(self, carga) -> list:
        """
        Detecta si el despachador tiene una concentración anómala de cargas
        con alertas en los últimos VENTANA_DESPACHADOR_DIAS días.

        Solo alerta si >= 40% de sus cargas tienen alguna alerta Y hay
        al menos MIN_CARGAS_DESPACHADOR cargas en el período.
        No alerta si el despachador ya fue señalado en la carga anterior de
        la misma unidad para evitar alertas redundantes.
        """
        from modulos.combustible.models import CargaCombustible, AlertaCombustible

        fecha_limite = timezone.now() - timedelta(days=VENTANA_DESPACHADOR_DIAS)

        cargas_despachador = (
            CargaCombustible.objects
            .filter(
                despachador=carga.despachador,
                estado='COMPLETADO',
                fecha_hora_inicio__gte=fecha_limite,
            )
            .exclude(pk=carga.pk)
        )

        total = cargas_despachador.count()
        if total < MIN_CARGAS_DESPACHADOR:
            return []

        con_alerta = cargas_despachador.filter(alertas__isnull=False).distinct().count()
        porcentaje = con_alerta / total

        UMBRAL_PATRON = 0.40
        if porcentaje < UMBRAL_PATRON:
            return []

        mensaje = (
            f"Despachador {carga.despachador.nombre}: {con_alerta} de {total} cargas "
            f"recientes ({porcentaje*100:.0f}%) tienen al menos una alerta en los últimos "
            f"{VENTANA_DESPACHADOR_DIAS} días. Se recomienda revisar el historial de este despachador."
        )

        return [{
            'tipo_alerta': 'PATRON_DESPACHADOR',
            'tipo_interno': 'PATRON_DESPACHADOR',
            'mensaje': mensaje,
            'datos_estadisticos': {
                'despachador_id': carga.despachador.pk,
                'total_cargas': total,
                'cargas_con_alerta': con_alerta,
                'porcentaje': round(porcentaje, 3),
                'ventana_dias': VENTANA_DESPACHADOR_DIAS,
            },
        }]

    # ------------------------------------------------------------------
    # Score de riesgo
    # ------------------------------------------------------------------

    def _calcular_score(self, anomalias: list) -> tuple:
        """
        Suma los puntos de cada anomalía y retorna (score_riesgo, total_puntos).
        Retorna (None, 0) si no hay anomalías.
        """
        if not anomalias:
            return (None, 0)

        total = sum(
            PUNTOS_ANOMALIA.get(a['tipo_interno'], 1)
            for a in anomalias
        )

        if total >= SCORE_THRESHOLDS['CRITICO']:
            score = 'CRITICO'
        elif total >= SCORE_THRESHOLDS['ALTO']:
            score = 'ALTO'
        elif total >= SCORE_THRESHOLDS['MEDIO']:
            score = 'MEDIO'
        else:
            score = 'BAJO'

        return (score, total)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @staticmethod
    def _percentil(datos: list, p: int) -> float:
        """Calcula el percentil p de una lista de datos ordenables."""
        if not datos:
            return 0.0
        datos_ordenados = sorted(datos)
        n = len(datos_ordenados)
        indice = (p / 100) * (n - 1)
        inferior = int(indice)
        superior = inferior + 1
        if superior >= n:
            return datos_ordenados[-1]
        fraccion = indice - inferior
        return datos_ordenados[inferior] + fraccion * (datos_ordenados[superior] - datos_ordenados[inferior])
