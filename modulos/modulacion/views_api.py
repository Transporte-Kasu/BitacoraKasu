import json
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from modulos.bitacoras.models import Cliente

from .models import Agencia, Modulacion, TerminalPortuaria
from .tokens import generar_token

REQUIRED_FIELDS = ['agencia', 'terminal_portuaria', 'tipo_contenedor', 'peso_toneladas', 'contenedor', 'cliente']


def _parsear_fecha_doda(valor):
    """Parsea 'fecha_doda' ('YYYY-MM-DD', opcional) a un datetime aware.

    Usada como fecha_recepcion para que el folio y las vistas por mes
    reflejen la fecha real del DODA en vez del día en que HAL9MIL lo mandó
    — importante para reintentos masivos de historial atrasado. Una fecha
    ausente o inválida no es un error: se ignora y Modulacion cae a su
    default (fecha_recepcion = ahora).
    """
    valor = str(valor or '').strip()
    if not valor:
        return None
    try:
        return timezone.make_aware(datetime.strptime(valor, '%Y-%m-%d'))
    except ValueError:
        return None


def _completar_datos_url(request, modulacion):
    """Link firmado para completar carril/horarios, o None si la terminal
    de esta modulación no requiere datos extra.

    Si PUBLIC_BASE_URL está configurado, se usa como base fija en vez de
    confiar en el Host de la request (build_absolute_uri refleja ese Host, y
    ALLOWED_HOSTS = ['*'] no lo valida)."""
    if not modulacion.terminal_portuaria.requiere_datos_extra:
        return None
    token = generar_token(modulacion)
    path = reverse('modulacion:completar_datos_terminal', args=[token])
    if settings.PUBLIC_BASE_URL:
        return f"{settings.PUBLIC_BASE_URL.rstrip('/')}{path}"
    return request.build_absolute_uri(path)


@csrf_exempt
@require_POST
def recibir_modulacion(request):
    """
    Endpoint que HAL9MIL invoca por cada contenedor de un DODA asignado a
    Transportes Kasu. Contrato de payload (ver plan de Proyecto_HAL9MIL):

    {
      "agencia": "LOGINCO",
      "terminal_portuaria": "<nombre del recinto>",
      "tipo_contenedor": "<'20DC'/'40HC'/...>",
      "peso_toneladas": "<peso>",
      "contenedor": "<numero>",
      "cliente": "<nombre>",
      "num_pedimento": "<opcional>",
      "num_doda": "<opcional>",
      "fecha_doda": "<opcional, 'YYYY-MM-DD'>"
    }
    """
    token_esperado = settings.BITACORAKASU_API_TOKEN
    auth_header = request.headers.get('Authorization', '')
    if not token_esperado or auth_header != f'Token {token_esperado}':
        return JsonResponse({'success': False, 'error': 'No autorizado'}, status=401)

    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)

    faltantes = [campo for campo in REQUIRED_FIELDS if not payload.get(campo)]
    if faltantes:
        return JsonResponse(
            {'success': False, 'error': f'Faltan campos requeridos: {", ".join(faltantes)}'},
            status=400,
        )

    num_doda = str(payload.get('num_doda', '') or '').strip()
    contenedor = str(payload['contenedor']).strip().upper()

    if num_doda:
        existente = Modulacion.objects.select_related('terminal_portuaria').filter(
            num_doda=num_doda, contenedor=contenedor
        ).first()
        if existente:
            data = {'success': True, 'id': existente.id, 'folio': existente.folio, 'duplicado': True}
            if existente.estado == 'PENDIENTE':
                url = _completar_datos_url(request, existente)
                if url:
                    data['completar_datos_url'] = url
            return JsonResponse(data, status=200)

    try:
        peso_toneladas = payload['peso_toneladas']
    except KeyError:
        return JsonResponse({'success': False, 'error': 'Falta peso_toneladas'}, status=400)

    agencia, _ = Agencia.objects.get_or_create(nombre=str(payload['agencia']).strip())
    terminal_portuaria, _ = TerminalPortuaria.objects.get_or_create(nombre=str(payload['terminal_portuaria']).strip())
    cliente, _ = Cliente.objects.get_or_create(nombre=str(payload['cliente']).strip())

    fecha_recepcion = _parsear_fecha_doda(payload.get('fecha_doda'))
    extra = {'fecha_recepcion': fecha_recepcion} if fecha_recepcion else {}

    try:
        modulacion = Modulacion.objects.create(
            agencia=agencia,
            terminal_portuaria=terminal_portuaria,
            tipo_contenedor=str(payload['tipo_contenedor']).strip(),
            peso_toneladas=peso_toneladas,
            contenedor=contenedor,
            cliente=cliente,
            num_pedimento=str(payload.get('num_pedimento', '') or '').strip(),
            num_doda=num_doda,
            origen='HAL9MIL',
            estado='PENDIENTE',
            **extra,
        )
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f'No se pudo crear la modulación: {exc}'}, status=400)

    data = {'success': True, 'id': modulacion.id, 'folio': modulacion.folio}
    url = _completar_datos_url(request, modulacion)
    if url:
        data['completar_datos_url'] = url
    return JsonResponse(data, status=201)
