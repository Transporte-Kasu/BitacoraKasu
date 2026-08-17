import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from modulos.bitacoras.models import Cliente

from .models import Agencia, Modulacion, TerminalPortuaria

REQUIRED_FIELDS = ['agencia', 'terminal_portuaria', 'tipo_contenedor', 'peso_toneladas', 'contenedor', 'cliente']


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
      "num_doda": "<opcional>"
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
        existente = Modulacion.objects.filter(num_doda=num_doda, contenedor=contenedor).first()
        if existente:
            return JsonResponse({'success': True, 'id': existente.id, 'folio': existente.folio, 'duplicado': True}, status=200)

    try:
        peso_toneladas = payload['peso_toneladas']
    except KeyError:
        return JsonResponse({'success': False, 'error': 'Falta peso_toneladas'}, status=400)

    agencia, _ = Agencia.objects.get_or_create(nombre=str(payload['agencia']).strip())
    terminal_portuaria, _ = TerminalPortuaria.objects.get_or_create(nombre=str(payload['terminal_portuaria']).strip())
    cliente, _ = Cliente.objects.get_or_create(nombre=str(payload['cliente']).strip())

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
        )
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f'No se pudo crear la modulación: {exc}'}, status=400)

    return JsonResponse({'success': True, 'id': modulacion.id, 'folio': modulacion.folio}, status=201)
