"""
IAKasu — Cliente centralizado para Claude API (Anthropic).

Reutilizable por todos los módulos que necesiten IA generativa.
Implementa prompt caching para reducir costos en prompts de sistema repetidos.

Modelos disponibles:
  - HAIKU  : claude-haiku-4-5-20251001  → clasificación, tareas simples (bajo costo)
  - SONNET : claude-sonnet-4-6          → análisis complejos, narrativas

Uso:
    from config.services.claude_service import ClaudeService, Modelo

    claude = ClaudeService()
    respuesta = claude.completar(
        sistema="Eres un analista de flota vehicular.",
        prompt="Analiza este patrón de consumo...",
        modelo=Modelo.SONNET,
    )
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class Modelo:
    HAIKU = 'claude-haiku-4-5-20251001'
    SONNET = 'claude-sonnet-4-6'


class ClaudeService:
    """
    Cliente para llamadas a Claude API con soporte de prompt caching.

    El campo `sistema` se marca como cache_control ephemeral para
    aprovechar el prompt caching de Anthropic y reducir costos.
    """

    def __init__(self):
        import anthropic
        api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY no está configurada en settings. "
                "Agrégala al .env y a settings.py."
            )
        self.client = anthropic.Anthropic(api_key=api_key)

    def completar(
        self,
        prompt: str,
        sistema: str = '',
        modelo: str = Modelo.HAIKU,
        max_tokens: int = 600,
    ) -> str:
        """
        Llama a Claude y retorna el texto de la respuesta.

        Args:
            prompt:    El mensaje del usuario (lo que varía en cada llamada).
            sistema:   Instrucciones del sistema (se cachea si es largo).
            modelo:    Modelo a usar (Modelo.HAIKU o Modelo.SONNET).
            max_tokens: Máximo de tokens en la respuesta.

        Returns:
            Texto de la respuesta o '' si la llamada falla.
        """
        if not getattr(settings, 'IA_HABILITADA', True):
            logger.debug("ClaudeService: IA_HABILITADA=False, omitiendo llamada.")
            return ''

        try:
            kwargs = {
                'model': modelo,
                'max_tokens': max_tokens,
                'messages': [{'role': 'user', 'content': prompt}],
            }

            # Agregar system con prompt caching si se provee
            if sistema:
                kwargs['system'] = [
                    {
                        'type': 'text',
                        'text': sistema,
                        'cache_control': {'type': 'ephemeral'},
                    }
                ]

            respuesta = self.client.messages.create(**kwargs)
            texto = respuesta.content[0].text.strip()

            logger.debug(
                "ClaudeService: modelo=%s tokens_entrada=%s tokens_salida=%s cache_hit=%s",
                modelo,
                respuesta.usage.input_tokens,
                respuesta.usage.output_tokens,
                getattr(respuesta.usage, 'cache_read_input_tokens', 0),
            )
            return texto

        except Exception as exc:
            logger.exception("ClaudeService: error en llamada a Claude API — %s", exc)
            return ''

    def disponible(self) -> bool:
        """Verifica que la API key está configurada y la IA está habilitada."""
        return bool(
            getattr(settings, 'ANTHROPIC_API_KEY', None)
            and getattr(settings, 'IA_HABILITADA', True)
        )
