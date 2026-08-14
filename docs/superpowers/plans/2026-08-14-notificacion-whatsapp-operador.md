# Notificación WhatsApp al Operador Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar un botón manual en el detalle de bitácora que envíe por WhatsApp al operador asignado los datos de su próximo viaje (contenedor/peso, destino, horario de entrega, observaciones), reutilizando la plantilla de Twilio ya aprobada para clientes.

**Architecture:** Extensión aditiva del servicio existente `config/services/twilio_service.py` (mismo Content SID de Twilio, nueva función `enviar_notificacion_operador`), una vista funcional nueva en `modulos/bitacoras/views.py` siguiendo el patrón exacto de `enviar_notificacion_cliente`, y un botón nuevo en `templates/bitacoras/bitacora_detail.html`. No se toca el flujo de cliente existente salvo una extracción sin cambio de comportamiento (`_var_info_carga`).

**Tech Stack:** Django 5.2.7, Twilio SDK (`twilio.rest.Client`), Django TestCase con `unittest.mock.patch` y `override_settings`.

## Global Constraints

- Todo el código, comentarios y verbose_name en español (convención del proyecto, `CLAUDE.md`).
- Ningún método de servicio externo debe propagar excepciones al llamador — siempre capturar y loggear (`logger.error`/`logger.warning`), retornando un dict de resultado (patrón ya usado en `twilio_service.py` y `whatsapp_service.py`).
- No se agrega correo para operador — solo WhatsApp.
- No se dispara automáticamente al guardar la bitácora — solo botón manual.
- No se modifica `Operador.telefono` (campo/migración) ni se migran datos existentes.
- Reutilizar `settings.TWILIO_CONTENT_SID_BITACORA` — no se crea plantilla nueva en Twilio.
- Spec completo: `docs/superpowers/specs/2026-08-14-notificacion-whatsapp-operador-design.md`.

---

## File Structure

- **Modify:** `config/services/twilio_service.py` — extraer `_var_info_carga`, agregar `_numero_wa_mx` y `enviar_notificacion_operador`.
- **Modify:** `modulos/bitacoras/views.py` — nueva vista `enviar_notificacion_operador`.
- **Modify:** `modulos/bitacoras/urls.py` — nueva ruta `notificar_operador`.
- **Modify:** `templates/bitacoras/bitacora_detail.html` — nuevo botón.
- **Modify:** `modulos/bitacoras/tests.py` — nuevas clases de test para todo lo anterior (el proyecto no tiene tests previos de `twilio_service`, así que se crean todos aquí, consumiendo `config.services.twilio_service` directamente, siguiendo la decisión ya tomada en el spec).

---

### Task 1: Extraer `_var_info_carga` de `enviar_notificacion_bitacora`

Refactor puro (sin cambio de comportamiento) que deja lista la lógica de `{{1}}` para reutilizarse en el mensaje del operador (Task 3).

**Files:**
- Modify: `config/services/twilio_service.py:39-76`
- Test: `modulos/bitacoras/tests.py`

**Interfaces:**
- Produces: `_var_info_carga(bitacora) -> str` en `config/services/twilio_service.py` — recibe una instancia de `BitacoraViaje` (no guardada en DB necesariamente, solo necesita los atributos `modalidad`, `contenedor`, `contenedor_2`, `peso`, `peso_2`, `tipo_contenedor`, `destino`), retorna el string de `{{1}}`.

- [ ] **Step 1: Escribir el test que fija el comportamiento actual**

Al inicio de `modulos/bitacoras/tests.py` (después de los imports existentes, línea 11), agregar el import del servicio y una nueva clase de test:

```python
from config.services.twilio_service import _var_info_carga
```

Agregar al final del archivo:

```python
class VarInfoCargaTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad()
        self.operador = _crear_operador()

    def _crear_viaje(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 1),
            fecha_salida=_aware(2026, 6, 1),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            tipo_contenedor='40',
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    def test_un_solo_contenedor(self):
        viaje = self._crear_viaje()

        resultado = _var_info_carga(viaje)

        self.assertEqual(
            resultado,
            "Contenedores: MSKU1234567 | Especificaciones: Tipo 40 con peso de 28.05t | Destino Final: BODEGA NORTE, MONTERREY"
        )

    def test_modalidad_full_con_dos_contenedores(self):
        viaje = self._crear_viaje(
            modalidad='FULL',
            contenedor_2='PONU8765436',
            peso_2=Decimal('15.65'),
        )

        resultado = _var_info_carga(viaje)

        self.assertEqual(
            resultado,
            "Contenedores: MSKU1234567 / PONU8765436 | Especificaciones: Tipo 40 (ambos) con pesos de 28.05 y 15.65 respectivamente | Destino Final: BODEGA NORTE, MONTERREY"
        )
```

- [ ] **Step 2: Ejecutar el test y confirmar que falla**

Run: `python manage.py test modulos.bitacoras.tests.VarInfoCargaTests -v 2`
Expected: FAIL — `ImportError: cannot import name '_var_info_carga' from 'config.services.twilio_service'`

- [ ] **Step 3: Extraer la función en `twilio_service.py`**

En `config/services/twilio_service.py`, insertar la nueva función antes de `enviar_notificacion_bitacora` (antes de la línea 39):

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

Luego, dentro de `enviar_notificacion_bitacora`, reemplazar las líneas 50-61 (bloque que construye `es_full`, `tipo`, `destino`, `var1`) por:

```python
    var1 = _var_info_carga(bitacora)
```

Verificar que `operador` y `unidad` (línea 48-49) se sigan usando más abajo en `var2` — no se tocan esas líneas.

- [ ] **Step 4: Ejecutar el test y confirmar que pasa**

Run: `python manage.py test modulos.bitacoras.tests.VarInfoCargaTests -v 2`
Expected: PASS (2 tests)

- [ ] **Step 5: Ejecutar toda la suite de bitácoras para confirmar que no hay regresión**

Run: `python manage.py test modulos.bitacoras -v 2`
Expected: todos los tests existentes (`IngresoCalculadoTests`, etc.) siguen en PASS.

- [ ] **Step 6: Commit**

```bash
git add config/services/twilio_service.py modulos/bitacoras/tests.py
git commit -m "Extrae _var_info_carga de twilio_service para reutilizar en notificación a operador"
```

---

### Task 2: Normalización de teléfono mexicano — `_numero_wa_mx`

**Files:**
- Modify: `config/services/twilio_service.py`
- Test: `modulos/bitacoras/tests.py`

**Interfaces:**
- Consumes: `_numero_wa(celular: str) -> str` (ya existente en `twilio_service.py:19-26`).
- Produces: `_numero_wa_mx(telefono: str) -> str` en `config/services/twilio_service.py` — recibe un string de teléfono (10 dígitos locales, o ya con código de país), retorna `whatsapp:+521XXXXXXXXXX` o equivalente.

- [ ] **Step 1: Escribir los tests**

Agregar el import y la clase de test en `modulos/bitacoras/tests.py`:

```python
from config.services.twilio_service import _numero_wa_mx
```

```python
class NumeroWaMxTests(TestCase):
    def test_diez_digitos_antepone_codigo_pais(self):
        self.assertEqual(_numero_wa_mx('7531573954'), 'whatsapp:+5217531573954')

    def test_diez_digitos_con_espacios_y_guiones(self):
        self.assertEqual(_numero_wa_mx('753 157 3954'), 'whatsapp:+5217531573954')
        self.assertEqual(_numero_wa_mx('753-157-3954'), 'whatsapp:+5217531573954')

    def test_numero_ya_con_codigo_de_pais_no_se_modifica(self):
        self.assertEqual(_numero_wa_mx('+5217531573954'), 'whatsapp:+5217531573954')
```

- [ ] **Step 2: Ejecutar los tests y confirmar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.NumeroWaMxTests -v 2`
Expected: FAIL — `ImportError: cannot import name '_numero_wa_mx'`

- [ ] **Step 3: Implementar `_numero_wa_mx`**

En `config/services/twilio_service.py`, agregar después de `_numero_wa` (después de la línea 26):

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

- [ ] **Step 4: Ejecutar los tests y confirmar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.NumeroWaMxTests -v 2`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add config/services/twilio_service.py modulos/bitacoras/tests.py
git commit -m "Agrega normalización de teléfono mexicano para WhatsApp a operador"
```

---

### Task 3: Servicio `enviar_notificacion_operador`

**Files:**
- Modify: `config/services/twilio_service.py`
- Test: `modulos/bitacoras/tests.py`

**Interfaces:**
- Consumes: `_var_info_carga(bitacora)` (Task 1), `_numero_wa_mx(telefono)` (Task 2), `_fecha_es(dt)` (ya existente, `twilio_service.py:32-36`), `_twilio_client()` (ya existente, `twilio_service.py:14-16`), `settings.TWILIO_CONTENT_SID_BITACORA`, `settings.TWILIO_WHATSAPP_FROM`.
- Produces: `enviar_notificacion_operador(bitacora) -> dict` con clave `'wa_ok'` (bool) — usada por la vista en Task 4.

- [ ] **Step 1: Escribir los tests**

Agregar imports en `modulos/bitacoras/tests.py`:

```python
from unittest.mock import patch, MagicMock
from django.test import override_settings

from config.services.twilio_service import enviar_notificacion_operador
```

Agregar la clase de test (usa el mismo helper `_crear_viaje` con datos de operador que incluyan teléfono — como `_crear_operador()` no fija `telefono`, se crea el operador directamente en `setUp`):

```python
@override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
class EnviarNotificacionOperadorTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad()
        self.operador = Operador.objects.create(
            nombre='Kevin Márquez', tipo='LOCAL', telefono='7531573954'
        )

    def _crear_viaje(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            tipo_contenedor='40',
            observaciones='Custodia: CUSTORESCA\nContacto: LEIZOREK',
            reparto=False,
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    @patch('config.services.twilio_service._twilio_client')
    def test_envia_wa_con_horario_calculado_desde_duracion(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(duracion_estimada=411)

        resultado = enviar_notificacion_operador(viaje)

        self.assertTrue(resultado['wa_ok'])
        mock_messages.create.assert_called_once()
        kwargs = mock_messages.create.call_args.kwargs
        self.assertEqual(kwargs['to'], 'whatsapp:+5217531573954')
        self.assertEqual(kwargs['from_'], 'whatsapp:+14155238886')
        self.assertEqual(kwargs['content_sid'], 'HXfake000000000000000000000000')

        variables = json.loads(kwargs['content_variables'])
        self.assertEqual(
            variables['2'],
            "Destino: BODEGA NORTE, MONTERREY | Horario de entrega: 22 jun 2026 23:51"
        )
        self.assertEqual(
            variables['3'],
            "Servicio DIRECTO ejecutado Custodia: CUSTORESCA\nContacto: LEIZOREK."
        )

    @patch('config.services.twilio_service._twilio_client')
    def test_sin_duracion_estimada_usa_fecha_salida_como_fallback(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(duracion_estimada=None)

        resultado = enviar_notificacion_operador(viaje)

        self.assertTrue(resultado['wa_ok'])
        kwargs = mock_messages.create.call_args.kwargs
        variables = json.loads(kwargs['content_variables'])
        self.assertEqual(
            variables['2'],
            "Destino: BODEGA NORTE, MONTERREY | Horario de entrega: 22 jun 2026 17:00"
        )

    def test_sin_telefono_no_envia_y_retorna_wa_ok_false(self):
        self.operador.telefono = ''
        self.operador.save()
        viaje = self._crear_viaje(duracion_estimada=411)

        resultado = enviar_notificacion_operador(viaje)

        self.assertFalse(resultado['wa_ok'])

    @override_settings(TWILIO_CONTENT_SID_BITACORA='')
    def test_sin_content_sid_configurado_no_envia_y_retorna_wa_ok_false(self):
        viaje = self._crear_viaje(duracion_estimada=411)

        resultado = enviar_notificacion_operador(viaje)

        self.assertFalse(resultado['wa_ok'])

    @patch('config.services.twilio_service._twilio_client')
    def test_excepcion_de_twilio_no_se_propaga(self, mock_client_fn):
        mock_client_fn.return_value.messages.create.side_effect = Exception('boom')
        viaje = self._crear_viaje(duracion_estimada=411)

        resultado = enviar_notificacion_operador(viaje)

        self.assertFalse(resultado['wa_ok'])
```

Agregar `import json` a los imports de `modulos/bitacoras/tests.py` (línea 1, junto a `from datetime import date, datetime`).

- [ ] **Step 2: Ejecutar los tests y confirmar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.EnviarNotificacionOperadorTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'enviar_notificacion_operador'`

- [ ] **Step 3: Implementar `enviar_notificacion_operador`**

En `config/services/twilio_service.py`:

1. Agregar `from datetime import timedelta` al inicio del archivo, junto a los otros imports (línea 6, antes de `import json`).
2. Agregar la función después de `enviar_notificacion_bitacora` (después de la línea 117, antes de `_cuerpo_email`):

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

- [ ] **Step 4: Ejecutar los tests y confirmar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.EnviarNotificacionOperadorTests -v 2`
Expected: PASS (5 tests)

- [ ] **Step 5: Ejecutar toda la suite de bitácoras**

Run: `python manage.py test modulos.bitacoras -v 2`
Expected: todos los tests (incluyendo Tasks 1 y 2) en PASS.

- [ ] **Step 6: Commit**

```bash
git add config/services/twilio_service.py modulos/bitacoras/tests.py
git commit -m "Agrega enviar_notificacion_operador reutilizando template de Twilio del cliente"
```

---

### Task 4: Vista y URL — `enviar_notificacion_operador`

**Files:**
- Modify: `modulos/bitacoras/views.py:367-389` (agregar después de `enviar_notificacion_cliente`)
- Modify: `modulos/bitacoras/urls.py:20`
- Test: `modulos/bitacoras/tests.py`

**Interfaces:**
- Consumes: `enviar_notificacion_operador(bitacora) -> dict` (Task 3, importado desde `config.services.twilio_service`).
- Produces: vista `enviar_notificacion_operador(request, pk)` en `modulos/bitacoras/views.py`, ruta `bitacoras:notificar_operador` en `modulos/bitacoras/urls.py`.

- [ ] **Step 1: Escribir los tests de la vista**

Agregar la clase de test en `modulos/bitacoras/tests.py` (requiere `from django.urls import reverse`, agregarlo a los imports del archivo):

```python
from django.urls import reverse


class NotificarOperadorViewTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad()
        self.operador = Operador.objects.create(
            nombre='Kevin Márquez', tipo='LOCAL', telefono='7531573954'
        )
        self.viaje = BitacoraViaje.objects.create(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
        )

    @override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_post_exitoso_redirige_con_mensaje_de_exito(self, mock_client_fn):
        mock_client_fn.return_value.messages = MagicMock()

        response = self.client.post(reverse('bitacoras:notificar_operador', args=[self.viaje.pk]))

        self.assertRedirects(response, reverse('bitacoras:detail', args=[self.viaje.pk]))

    @override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_post_exitoso_incluye_mensaje_de_exito_en_response(self, mock_client_fn):
        mock_client_fn.return_value.messages = MagicMock()

        response = self.client.post(
            reverse('bitacoras:notificar_operador', args=[self.viaje.pk]), follow=True
        )

        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('Kevin Márquez' in m and 'WhatsApp enviado' in m for m in mensajes))

    def test_post_sin_telefono_muestra_mensaje_de_error_y_no_llama_twilio(self):
        self.operador.telefono = ''
        self.operador.save()

        with patch('config.services.twilio_service._twilio_client') as mock_client_fn:
            response = self.client.post(
                reverse('bitacoras:notificar_operador', args=[self.viaje.pk]), follow=True
            )
            mock_client_fn.assert_not_called()

        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('No se pudo enviar' in m for m in mensajes))
```

- [ ] **Step 2: Ejecutar los tests y confirmar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.NotificarOperadorViewTests -v 2`
Expected: FAIL — `django.urls.exceptions.NoReverseMatch: Reverse for 'notificar_operador' not found`

- [ ] **Step 3: Agregar la URL**

En `modulos/bitacoras/urls.py`, después de la línea 20 (`path('<int:pk>/notificar-cliente/', ...)`):

```python
    path('<int:pk>/notificar-operador/', views.enviar_notificacion_operador, name='notificar_operador'),
```

- [ ] **Step 4: Agregar la vista**

En `modulos/bitacoras/views.py`, después de `enviar_notificacion_cliente` (después de la línea 389, antes del comentario `# CARGA MASIVA DESDE EXCEL`):

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

- [ ] **Step 5: Ejecutar los tests y confirmar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.NotificarOperadorViewTests -v 2`
Expected: PASS (3 tests)

- [ ] **Step 6: Ejecutar toda la suite de bitácoras**

Run: `python manage.py test modulos.bitacoras -v 2`
Expected: todos los tests en PASS.

- [ ] **Step 7: Commit**

```bash
git add modulos/bitacoras/views.py modulos/bitacoras/urls.py modulos/bitacoras/tests.py
git commit -m "Agrega vista y ruta para notificar por WhatsApp al operador"
```

---

### Task 5: Botón en el detalle de bitácora

**Files:**
- Modify: `templates/bitacoras/bitacora_detail.html:104-114`

**Interfaces:**
- Consumes: ruta `bitacoras:notificar_operador` (Task 4), `bitacora.operador.nombre` (campo existente del modelo `Operador`).

- [ ] **Step 1: Agregar el botón**

En `templates/bitacoras/bitacora_detail.html`, después del bloque `{% endif %}` que cierra el botón de cliente (línea 114), agregar:

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

El botón queda siempre visible (sin `{% if %}` condicional), ya que `operador` es una FK obligatoria en `BitacoraViaje` — a diferencia del botón de cliente que sí depende de `{% if bitacora.cliente %}`.

- [ ] **Step 2: Verificar manualmente en el navegador**

Levantar el servidor de desarrollo:

Run: `python manage.py runserver`

Abrir `http://127.0.0.1:8000/bitacoras/<id-de-una-bitacora-existente>/` en el navegador (usar el id de cualquier bitácora ya creada en la base de datos local), confirmar que:
- El botón "Notificar a {nombre del operador}" aparece junto al de cliente (o solo, si la bitácora no tiene cliente).
- Al hacer click, redirige de vuelta al detalle y muestra un mensaje (éxito o error, según si `TWILIO_CONTENT_SID_BITACORA` está configurado en el `.env` local y el operador tiene teléfono capturado).

- [ ] **Step 3: Ejecutar toda la suite del proyecto**

Run: `python manage.py test`
Expected: todos los tests del proyecto en PASS (sin regresiones en otros módulos).

- [ ] **Step 4: Commit**

```bash
git add templates/bitacoras/bitacora_detail.html
git commit -m "Agrega botón para notificar por WhatsApp al operador en detalle de bitácora"
```

---

## Self-Review Summary

- **Cobertura del spec:** Task 1 cubre la sección "Refactor menor" del spec; Task 2 cubre "Normalización de teléfono"; Task 3 cubre "Nueva función de servicio" (incluye fallback de `duracion_estimada`); Task 4 cubre "Vista" y "URL"; Task 5 cubre "Template". La sección "Testing" del spec queda repartida en las Steps 1 de cada task. La sección "Fuera de alcance" del spec no requiere tareas (confirma explícitamente qué NO se construye).
- **Placeholders:** ninguno — cada step trae código completo y ejecutable.
- **Consistencia de tipos:** `enviar_notificacion_operador(bitacora) -> dict` (Task 3) es exactamente lo que consume la vista en Task 4 (`resultado['wa_ok']`). `_numero_wa_mx` (Task 2) es exactamente lo que llama Task 3. `_var_info_carga` (Task 1) es exactamente lo que llama Task 3. Nombres de campos (`operador.telefono`, `bitacora.destino`, `bitacora.duracion_estimada`, `bitacora.fecha_salida`, `bitacora.observaciones`, `bitacora.reparto`) verificados contra el modelo real en `modulos/bitacoras/models.py` y `modulos/operadores/models.py`.
