# Diseño: Notificación WhatsApp al operador desde bitácora de viaje

**Fecha:** 2026-08-14
**Estado:** Aprobado

---

## Objetivo

Cuando se termina de capturar una `BitacoraViaje`, el usuario debe poder notificar por WhatsApp al **operador** (chofer) asignado — reutilizando la misma plantilla de Twilio (Content API) que ya se usa para notificar al **cliente** — con los datos de su próximo viaje: contenedor(es) y peso, destino y horario de entrega, y las observaciones del viaje.

Esto es una extensión del flujo existente de notificación a cliente (`config/services/twilio_service.py`, botón manual "Notificar a {cliente}" en `bitacora_detail.html`), no una integración nueva de WhatsApp. No se modifica ni se rompe el flujo de cliente existente — todos los cambios son aditivos.

**Disparo:** manual, vía botón en el detalle de la bitácora — igual que el flujo de cliente, no automático al guardar.

**Canal:** solo WhatsApp (sin correo). Los operadores son personal de campo; el correo no aporta valor aquí y evita depender de que tengan email capturado.

---

## 1. Refactor menor: extraer construcción de `{{1}}` a un helper compartido

Hoy `enviar_notificacion_bitacora()` construye la variable `{{1}}` (Información de Carga) inline (`config/services/twilio_service.py:54-61`). Como el mensaje al operador usa exactamente la misma lógica para `{{1}}`, se extrae sin cambiar comportamiento:

```python
def _var_info_carga(bitacora) -> str:
    """{{1}} — Información de Carga (contenedores, tipo, peso)."""
    es_full = bitacora.modalidad in ('FULL', 'LOCAL_FULL')
    tipo = bitacora.tipo_contenedor or '-'
    destino = (bitacora.destino or '-').upper()

    if es_full and bitacora.contenedor_2:
        contenedores = f"{bitacora.contenedor or '-'} / {bitacora.contenedor_2}"
        especificaciones = f"Tipo {tipo} (ambos) con pesos de {bitacora.peso or '-'} y {bitacora.peso_2 or '-'} respectivamente"
    else:
        contenedores = bitacora.contenedor or '-'
        especificaciones = f"Tipo {tipo} con peso de {bitacora.peso or '-'}t"

    return f"Contenedores: {contenedores} | Especificaciones: {especificaciones} | Destino Final: {destino}"
```

`enviar_notificacion_bitacora()` pasa a llamar `_var_info_carga(bitacora)` en vez de tener la lógica inline. Comportamiento idéntico, sin cambio de tests existentes de cliente.

---

## 2. Nueva función de servicio — `enviar_notificacion_operador`

**`config/services/twilio_service.py`**

```python
def enviar_notificacion_operador(bitacora) -> dict:
    """
    Envía WhatsApp (mismo template Twilio que cliente) al operador asignado
    con los datos de su próximo viaje.

    Returns dict con clave 'wa_ok' (bool).
    """
    resultado = {'wa_ok': False}
    operador = bitacora.operador

    var1 = _var_info_carga(bitacora)

    # {{2}} — Detalles del Traslado (versión operador: destino + horario de entrega)
    if bitacora.duracion_estimada:
        hora_entrega = bitacora.fecha_salida + timedelta(minutes=bitacora.duracion_estimada)
    else:
        hora_entrega = bitacora.fecha_salida
    destino = (bitacora.destino or '-').upper()
    var2 = f"Destino: {destino} | Horario de entrega: {_fecha_es(hora_entrega)}"

    # {{3}} — Notas Adicionales (igual que cliente)
    obs = bitacora.observaciones or 'SIN CUSTODIA'
    tipo_servicio = 'REPARTO' if bitacora.reparto else 'DIRECTO'
    var3 = f"Servicio {tipo_servicio} ejecutado {obs}."

    variables = {'1': var1, '2': var2, '3': var3}

    telefono = (operador.telefono or '').strip()
    if telefono and settings.TWILIO_CONTENT_SID_BITACORA:
        try:
            client = _twilio_client()
            client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=_numero_wa_mx(telefono),
                content_sid=settings.TWILIO_CONTENT_SID_BITACORA,
                content_variables=json.dumps(variables, ensure_ascii=False),
            )
            resultado['wa_ok'] = True
            logger.info("WA enviado a operador %s (%s)", operador.nombre, telefono)
        except Exception as exc:
            logger.error("Error WA Twilio para operador %s: %s", operador.nombre, exc)
    else:
        if not telefono:
            logger.warning("Operador %s sin teléfono — WA omitido.", operador.nombre)
        if not settings.TWILIO_CONTENT_SID_BITACORA:
            logger.warning("TWILIO_CONTENT_SID_BITACORA no configurado.")

    return resultado
```

Requiere `from datetime import timedelta` al inicio del módulo (no está importado hoy).

Reutiliza el mismo `settings.TWILIO_CONTENT_SID_BITACORA` — no se necesita una plantilla nueva en Twilio/Meta, ya que la plantilla aprobada solo define 3 slots de variables genéricos (`Información de Carga` / `Detalles del Traslado` / `Notas Adicionales`), y el contenido de cada slot es libre en cada llamada.

**Fallback sin `duracion_estimada`:** si Google Maps no ha calculado la distancia/duración todavía (campo `null` hasta que se llama `calcular_distancia_google()`), `hora_entrega` cae a `bitacora.fecha_salida` tal cual — el operador recibe la hora de salida programada en vez de una hora de llegada estimada. No bloquea el envío ni genera error.

---

## 3. Normalización de teléfono mexicano — `_numero_wa_mx`

`Operador.telefono` (`modulos/operadores/models.py`) se captura hoy como número local a 10 dígitos, sin código de país (ej. `7531573954`), a diferencia de `Cliente.celular` que exige formato completo con `+52...` (ver `help_text` en `modulos/bitacoras/models.py:14`). Reutilizar `_numero_wa()` tal cual produciría `whatsapp:+7531573954`, inválido.

Nuevo helper en `twilio_service.py`:

```python
def _numero_wa_mx(telefono: str) -> str:
    """
    Normaliza teléfono de operador a formato whatsapp:+521XXXXXXXXXX.
    Si son 10 dígitos (formato actual de Operador.telefono), antepone
    '521' (México + WhatsApp) automáticamente. Si ya trae código de país,
    se respeta tal cual (mismo comportamiento que _numero_wa).
    """
    numero = telefono.strip().replace(' ', '').replace('-', '')
    solo_digitos = numero.lstrip('+')
    if solo_digitos.isdigit() and len(solo_digitos) == 10:
        numero = '521' + solo_digitos
    return _numero_wa(numero)
```

No se modifica `Operador.telefono` (campo, `max_length`, `help_text`) ni se tocan datos existentes — la normalización ocurre solo al momento de enviar.

---

## 4. Vista — `enviar_notificacion_operador`

**`modulos/bitacoras/views.py`**, junto a `enviar_notificacion_cliente` (línea 367-389):

```python
def enviar_notificacion_operador(request, pk):
    """Envía WhatsApp al operador asignado a la bitácora."""
    bitacora = get_object_or_404(BitacoraViaje, pk=pk)

    from config.services.twilio_service import enviar_notificacion_operador as _enviar
    resultado = _enviar(bitacora)

    if resultado['wa_ok']:
        messages.success(request, f"WhatsApp enviado a {bitacora.operador.nombre}.")
    else:
        messages.error(request, f"No se pudo enviar el WhatsApp a {bitacora.operador.nombre}. Verifica su teléfono y la configuración de Twilio.")

    return redirect('bitacoras:detail', pk=pk)
```

`operador` es FK obligatoria en `BitacoraViaje` (no puede ser `null`), así que no hace falta el chequeo condicional que tiene `enviar_notificacion_cliente` para `bitacora.cliente`.

---

## 5. URL

**`modulos/bitacoras/urls.py`**, junto a la ruta existente (línea 20):

```python
path('<int:pk>/notificar-operador/', views.enviar_notificacion_operador, name='notificar_operador'),
```

---

## 6. Template

**`templates/bitacoras/bitacora_detail.html`**, nuevo botón junto al de cliente (después de línea 113), siempre visible:

```html
<form method="post" action="{% url 'bitacoras:notificar_operador' bitacora.pk %}" class="inline">
    {% csrf_token %}
    <button type="submit"
            class="inline-flex items-center gap-1.5 bg-green-50 hover:bg-green-100 text-green-700
                   px-4 py-2 rounded-lg font-semibold text-sm transition min-h-[40px] border border-green-200">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
        Notificar a {{ bitacora.operador.nombre }}
    </button>
</form>
```

Mismo estilo visual que el botón de cliente, para consistencia.

---

## 7. Testing (TDD — tests antes que implementación)

**`modulos/bitacoras/tests.py`**, nueva clase `NotificacionOperadorTests` (o extender la suite de Twilio existente si ya hay una para cliente):

- `_var_info_carga` produce el mismo string para modalidad FULL y no-FULL (regresión: mismo comportamiento que hoy, solo movido).
- `enviar_notificacion_operador(bitacora)`:
  - construye `{{2}}` con `Destino` y `Horario de entrega` calculado (`fecha_salida + duracion_estimada`) cuando `duracion_estimada` existe.
  - fallback a `fecha_salida` solo, cuando `duracion_estimada` es `None`.
  - `{{3}}` idéntico al de cliente (mismo campo `observaciones`, mismo formato REPARTO/DIRECTO).
  - retorna `wa_ok=False` sin excepción cuando `operador.telefono` está vacío.
  - retorna `wa_ok=False` sin excepción cuando `TWILIO_CONTENT_SID_BITACORA` no está configurado.
  - llama a Twilio con `to=_numero_wa_mx(...)` correcto (mock de `_twilio_client`).
- `_numero_wa_mx`:
  - `7531573954` → `whatsapp:+5217531573954`.
  - `+5217531573954` (ya con código de país) → sin cambio, igual que `_numero_wa`.
  - con espacios/guiones (`753-157-3954`) → normalizado igual.
- Vista `enviar_notificacion_operador` (Django test client):
  - POST exitoso → redirect a detail + mensaje de éxito.
  - POST con operador sin teléfono → redirect a detail + mensaje de error, sin llamar a Twilio.

---

## Fuera de alcance

- No se agrega email para el operador.
- No se dispara automáticamente al guardar la bitácora (solo botón manual).
- No se modifica el campo `Operador.telefono` ni se migran datos existentes.
- No se maneja `destino_2` / reparto de forma distinta en el mensaje al operador — mismo nivel de simplificación que ya tiene el mensaje de cliente hoy (el reparto solo se refleja en `{{3}}` como "Servicio REPARTO").
- No se toca `carga_masiva_preview` (creación masiva vía Excel) — el botón de notificación solo aplica al flujo de detalle individual, igual que el de cliente.
