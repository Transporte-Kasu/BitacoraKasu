# Notificación separada por contenedor en viajes con reparto — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cuando un viaje `BitacoraViaje` tiene `reparto=True`, dividir la notificación al cliente en dos envíos independientes (uno por contenedor), soportando distinto cliente y/o distinto horario de entrega por contenedor, sin cambiar la notificación combinada al operador ni el caso sin reparto.

**Architecture:** Dos campos nuevos opcionales en el modelo (`cliente_2`, `fecha_hora_entrega_2`) más una regla de validación condicional (`cp_destino_2` obligatorio con reparto). El formulario y el detalle exponen esos campos. En `twilio_service.py` se factoriza el envío WA+email a un helper compartido, se agrega un constructor de `{{1}}` por-contenedor y una función `enviar_notificaciones_reparto()` que arma y envía dos mensajes independientes. La vista `enviar_notificacion_cliente` bifurca según `bitacora.reparto`.

**Tech Stack:** Django 5.2.7, `django.test.TestCase`, `unittest.mock.patch`/`MagicMock` para Twilio, SQLite en pruebas.

## Global Constraints

- Todo el código, comentarios de modelo (`verbose_name`) y texto de UI en español (es-mx), conforme `CLAUDE.md`.
- Campos nuevos (`cliente_2`, `fecha_hora_entrega_2`) son `null=True, blank=True` — ningún dato existente se rompe ni se vuelve obligatorio salvo lo indicado.
- `cp_destino_2` pasa a ser obligatorio (a nivel `clean()` de modelo y formulario) únicamente cuando `reparto=True`; puede coincidir con `cp_destino` — no se valida que sean distintos.
- La notificación al operador (`enviar_notificacion_operador` en `twilio_service.py` y `views.py`) no se modifica.
- El caso sin reparto (`enviar_notificacion_bitacora`) debe mantener el mismo comportamiento observable — cualquier refactor ahí es puramente interno.
- No se toca la carga masiva por Excel (`carga_masiva_upload`/`carga_masiva_preview`, `excel_parser.py`).
- Cada tarea termina con `python manage.py test modulos.bitacoras` en verde antes de pasar a la siguiente.

---

### Task 1: Modelo — `cliente_2`, `fecha_hora_entrega_2` y validación de reparto

**Files:**
- Modify: `modulos/bitacoras/models.py:44-51` (junto a `cliente`), `models.py:115-119` (junto a `fecha_hora_entrega`), `models.py:327-341` (`clean()`)
- Modify: `modulos/bitacoras/admin.py:44-47` (fieldset `'Contenedor 2 (FULL)'`)
- Create: migración Django generada por `makemigrations` (`modulos/bitacoras/migrations/0009_*.py`)
- Test: `modulos/bitacoras/tests.py` (nueva clase `RepartoValidacionModeloTests`, al final del archivo)

**Interfaces:**
- Produces: `BitacoraViaje.cliente_2` (FK a `Cliente`, `on_delete=SET_NULL`, `null=True, blank=True`, `related_name='bitacoras_contenedor_2'`); `BitacoraViaje.fecha_hora_entrega_2` (`DateTimeField`, `null=True, blank=True`); `clean()` lanza `ValidationError({'cp_destino_2': ...})` si `reparto=True` y `cp_destino_2` vacío.

- [ ] **Step 1: Escribir el test que falla — reparto sin `cp_destino_2` es inválido**

Agregar `from django.core.exceptions import ValidationError` al bloque de imports del inicio de `modulos/bitacoras/tests.py` (junto a las líneas 8-11, con los demás imports de `django.*`).

Agregar al final de `modulos/bitacoras/tests.py`:

```python
class RepartoValidacionModeloTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-950')
        self.operador = _crear_operador()
        self.cliente = Cliente.objects.create(nombre='Cliente Uno', celular='+5217531234567')
        self.cliente_2 = Cliente.objects.create(nombre='Cliente Dos', celular='+5217539876543')

    def _crear_viaje_full(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='FULL',
            fecha_carga=_aware(2026, 6, 1),
            fecha_salida=_aware(2026, 6, 1),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            contenedor_2='PONU8765436',
            peso_2=Decimal('15.65'),
            cp_destino='64000',
            reparto=True,
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    def test_reparto_sin_cp_destino_2_es_invalido(self):
        viaje = self._crear_viaje_full(cp_destino_2='')

        with self.assertRaises(ValidationError) as ctx:
            viaje.clean()

        self.assertIn('cp_destino_2', ctx.exception.message_dict)

    def test_reparto_con_cp_destino_2_igual_a_cp_destino_es_valido(self):
        viaje = self._crear_viaje_full(cp_destino_2='64000')

        viaje.clean()  # no debe lanzar

    def test_reparto_con_cliente_2_y_fecha_hora_entrega_2_se_guardan(self):
        viaje = self._crear_viaje_full(
            cp_destino_2='64010',
            cliente=self.cliente,
            cliente_2=self.cliente_2,
            fecha_hora_entrega=_aware(2026, 6, 2, 10),
            fecha_hora_entrega_2=_aware(2026, 6, 2, 15),
        )
        viaje.full_clean()
        viaje.save()

        viaje_desde_db = BitacoraViaje.objects.get(pk=viaje.pk)
        self.assertEqual(viaje_desde_db.cliente_2, self.cliente_2)
        self.assertEqual(viaje_desde_db.fecha_hora_entrega_2, _aware(2026, 6, 2, 15))

    def test_reparto_sin_cliente_2_ni_fecha_hora_entrega_2_es_valido(self):
        viaje = self._crear_viaje_full(cp_destino_2='64010')

        viaje.clean()  # no debe lanzar — ambos campos son opcionales
```

- [ ] **Step 2: Correr los tests nuevos y verificar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.RepartoValidacionModeloTests -v 2`
Expected: `FAIL` — `test_reparto_sin_cp_destino_2_es_invalido` no lanza `ValidationError` (la regla no existe todavía) y los tests que usan `cliente_2`/`fecha_hora_entrega_2` fallan con `TypeError: 'cliente_2' is an invalid keyword argument` (los campos no existen).

- [ ] **Step 3: Agregar los campos al modelo**

En `modulos/bitacoras/models.py`, inmediatamente después del campo `cliente` (línea 51, antes de `operador = models.ForeignKey(...)`):

```python
    cliente_2 = models.ForeignKey(
        'Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bitacoras_contenedor_2',
        verbose_name="Cliente (contenedor 2)",
    )
```

Inmediatamente después del campo `fecha_hora_entrega` (línea 119, antes del comentario `# Combustible y kilometraje`):

```python
    fecha_hora_entrega_2 = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha/hora de entrega (contenedor 2)",
    )
```

- [ ] **Step 4: Agregar la validación en `clean()`**

En `modulos/bitacoras/models.py`, al final del método `clean()` (después de la línea `raise ValidationError({'reparto': 'Local Full no usa reparto.'})`, línea 341):

```python
        if self.reparto and not self.cp_destino_2:
            raise ValidationError({'cp_destino_2': 'El reparto requiere el CP del segundo destino.'})
```

- [ ] **Step 5: Generar y revisar la migración**

Run: `python manage.py makemigrations bitacoras`
Expected: crea `modulos/bitacoras/migrations/0009_bitacoraviaje_cliente_2_and_more.py` (o nombre similar) con dos operaciones `AddField` (`cliente_2`, `fecha_hora_entrega_2`).

Abrir el archivo generado y confirmar que ambos `AddField` tienen `null=True, blank=True` y que `cliente_2` referencia `to='bitacoras.cliente'`. Si el nombre de archivo difiere, usar el que Django generó (no renombrar a mano).

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.RepartoValidacionModeloTests -v 2`
Expected: `OK` (4 tests).

- [ ] **Step 7: Actualizar el admin**

En `modulos/bitacoras/admin.py:45`, cambiar:

```python
        ('Contenedor 2 (FULL)', {
            'fields': ('contenedor_2', 'peso_2', 'sellos_2', 'reparto'),
            'classes': ('collapse',)
        }),
```

por:

```python
        ('Contenedor 2 (FULL)', {
            'fields': ('contenedor_2', 'peso_2', 'sellos_2', 'reparto', 'cliente_2', 'fecha_hora_entrega_2'),
            'classes': ('collapse',)
        }),
```

- [ ] **Step 8: Correr la suite completa del módulo**

Run: `python manage.py test modulos.bitacoras -v 2`
Expected: `OK`, sin regresiones sobre los tests preexistentes.

- [ ] **Step 9: Commit**

```bash
git add modulos/bitacoras/models.py modulos/bitacoras/admin.py modulos/bitacoras/migrations/ modulos/bitacoras/tests.py
git commit -m "Agrega cliente_2 y fecha_hora_entrega_2 a BitacoraViaje para reparto"
```

---

### Task 2: Formulario y UI de captura

**Files:**
- Modify: `modulos/bitacoras/forms.py:24-42` (`Meta.fields`), `forms.py:44-46` (widget `cliente`), `forms.py:70-73` (widget `fecha_hora_entrega`), `forms.py:111-113` (widget `reparto`), `forms.py:162-180` (`clean()`)
- Modify: `templates/bitacoras/bitacora_form.html:507-531` (`#seccion-cp-destino-2`)
- Test: `modulos/bitacoras/tests.py` (nueva clase `BitacoraViajeFormRepartoValidacionTests`)

**Interfaces:**
- Consumes: `BitacoraViaje.cliente_2`, `BitacoraViaje.fecha_hora_entrega_2`, `BitacoraViaje.clean()` (Task 1).
- Produces: `BitacoraViajeForm` acepta y valida `cliente_2`, `fecha_hora_entrega_2`; rechaza `reparto=True` sin `cp_destino_2`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `modulos/bitacoras/tests.py`:

```python
class BitacoraViajeFormRepartoValidacionTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-960')
        self.operador = _crear_operador()
        self.cliente = Cliente.objects.create(nombre='Cliente Uno', celular='+5217531234567')

    def _datos_full_reparto(self, **overrides):
        datos = dict(
            modalidad='FULL',
            operador=self.operador.pk,
            unidad=self.unidad.pk,
            fecha_carga='2026-06-22T08:00',
            fecha_salida='2026-06-22T17:00',
            contenedor='MSKU1234567',
            tipo_contenedor='40',
            peso='28.05',
            contenedor_2='PONU8765436',
            peso_2='15.65',
            cp_origen='40812',
            cp_destino='64000',
            destino='Bodega Norte, Monterrey',
            reparto=True,
        )
        datos.update(overrides)
        return datos

    def test_reparto_sin_cp_destino_2_es_invalido(self):
        form = BitacoraViajeForm(data=self._datos_full_reparto(cp_destino_2=''))

        self.assertFalse(form.is_valid())
        self.assertIn('cp_destino_2', form.errors)

    def test_reparto_con_cp_destino_2_es_valido(self):
        form = BitacoraViajeForm(data=self._datos_full_reparto(cp_destino_2='64010'))

        self.assertTrue(form.is_valid(), form.errors)

    def test_reparto_cliente_2_y_fecha_hora_entrega_2_son_opcionales(self):
        form = BitacoraViajeForm(data=self._datos_full_reparto(cp_destino_2='64010'))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['cliente_2'])
        self.assertIsNone(form.cleaned_data['fecha_hora_entrega_2'])

    def test_reparto_con_cliente_2_y_fecha_hora_entrega_2_presentes(self):
        form = BitacoraViajeForm(data=self._datos_full_reparto(
            cp_destino_2='64010',
            cliente_2=self.cliente.pk,
            fecha_hora_entrega_2='2026-06-23T09:00',
        ))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['cliente_2'], self.cliente)
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.BitacoraViajeFormRepartoValidacionTests -v 2`
Expected: `FAIL` — `cliente_2`/`fecha_hora_entrega_2` no son campos del formulario (`KeyError` en `cleaned_data`) y no hay error en `cp_destino_2` cuando falta.

- [ ] **Step 3: Agregar los campos a `Meta.fields`**

En `modulos/bitacoras/forms.py:24-42`, cambiar la línea `'reparto',` (dentro del bloque "Contenedor 2 (solo FULL)") por:

```python
            'reparto', 'cliente_2', 'fecha_hora_entrega_2',
```

- [ ] **Step 4: Agregar los widgets**

En `modulos/bitacoras/forms.py`, inmediatamente después del widget `'cliente'` (líneas 44-46):

```python
            'cliente_2': forms.Select(attrs={
                'class': 'form-control',
            }),
```

Inmediatamente después del widget `'fecha_hora_entrega'` (líneas 70-73):

```python
            'fecha_hora_entrega_2': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
```

- [ ] **Step 5: Agregar la validación en `clean()`**

En `modulos/bitacoras/forms.py:162-180`, agregar tras la línea `contenedor_2 = cleaned_data.get('contenedor_2')`:

```python
        cp_destino_2 = cleaned_data.get('cp_destino_2')
```

Y agregar, junto a las validaciones existentes de `reparto` (después del bloque `if modalidad == 'LOCAL_FULL' and reparto: ...`):

```python
        if reparto and not cp_destino_2:
            self.add_error('cp_destino_2', 'El reparto requiere el CP del segundo destino.')
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.BitacoraViajeFormRepartoValidacionTests -v 2`
Expected: `OK` (4 tests).

- [ ] **Step 7: Actualizar la plantilla del formulario**

En `templates/bitacoras/bitacora_form.html:507-531`, cambiar el texto de ayuda de `cp_destino_2` (línea 514) de:

```html
                                    <span class="text-slate-400 font-normal text-xs">(reparto — opcional si igual)</span>
```

a:

```html
                                    <span class="text-slate-400 font-normal text-xs">(reparto — obligatorio)</span>
```

E insertar, justo antes del `</div>` que cierra `#seccion-cp-destino-2` (línea 531, el segundo `</div>` de cierre — el que cierra `id="seccion-cp-destino-2"`):

```html
                        <div class="grid grid-cols-2 gap-4 mt-4">
                            <div>
                                <label for="{{ form.cliente_2.id_for_label }}" class="block text-sm font-medium text-slate-700 mb-1.5">
                                    Cliente (contenedor 2)
                                    <span class="text-slate-400 font-normal text-xs">(vacío = mismo cliente)</span>
                                </label>
                                {{ form.cliente_2 }}
                                {% if form.cliente_2.errors %}
                                <p class="mt-1 text-xs text-red-600" role="alert">{{ form.cliente_2.errors|join:", " }}</p>
                                {% endif %}
                            </div>
                            <div>
                                <label for="{{ form.fecha_hora_entrega_2.id_for_label }}" class="block text-sm font-medium text-slate-700 mb-1.5">
                                    Fecha/hora de entrega (contenedor 2)
                                    <span class="text-slate-400 font-normal text-xs">(vacío = mismo horario)</span>
                                </label>
                                {{ form.fecha_hora_entrega_2 }}
                                {% if form.fecha_hora_entrega_2.errors %}
                                <p class="mt-1 text-xs text-red-600" role="alert">{{ form.fecha_hora_entrega_2.errors|join:", " }}</p>
                                {% endif %}
                            </div>
                        </div>
```

Estos dos campos quedan dentro de `#seccion-cp-destino-2`, que ya se muestra/oculta con el JS existente del toggle de `reparto` (`templates/bitacoras/bitacora_form.html:693-705`) — no se requiere JS adicional.

- [ ] **Step 8: Verificar manualmente en el navegador**

Run: `python manage.py runserver` y abrir `/bitacoras/crear/` (o la URL de creación de bitácora). Seleccionar modalidad FULL, llenar contenedor 2, activar el toggle "Viaje con reparto" y confirmar que aparecen los campos "CP destino 2", "Cliente (contenedor 2)" y "Fecha/hora de entrega (contenedor 2)" juntos, y que desaparecen al desactivar el toggle.

- [ ] **Step 9: Commit**

```bash
git add modulos/bitacoras/forms.py templates/bitacoras/bitacora_form.html modulos/bitacoras/tests.py
git commit -m "Formulario de bitácora captura cliente_2 y fecha_hora_entrega_2 en reparto"
```

---

### Task 3: Servicio Twilio — notificación dividida por contenedor

**Files:**
- Modify: `config/services/twilio_service.py:91-158` (refactor de `enviar_notificacion_bitacora`), agregar funciones nuevas junto a ella
- Test: `modulos/bitacoras/tests.py` (nueva clase `EnviarNotificacionesRepartoTests`)

**Interfaces:**
- Consumes: `BitacoraViaje.cliente`, `.cliente_2`, `.cp_destino`, `.cp_destino_2`, `.fecha_hora_entrega`, `.fecha_hora_entrega_2`, `.contenedor`, `.contenedor_2`, `.peso`, `.peso_2`, `.tipo_contenedor`, `.observaciones`, `.fecha_salida`, `.operador`, `.unidad` (Task 1 + campos ya existentes).
- Produces: `enviar_notificaciones_reparto(bitacora) -> dict` con claves `'contenedor_1'` y `'contenedor_2'`, cada una `None` (sin cliente asignado a ese contenedor) o `{'wa_ok': bool, 'email_ok': bool}` (mismo formato que `enviar_notificacion_bitacora`). `_var_info_carga_contenedor(bitacora, numero)` — función interna, `numero` es `1` o `2`.

- [ ] **Step 1: Escribir los tests que fallan**

En el bloque de imports del inicio de `modulos/bitacoras/tests.py` (líneas 20-27), agregar `enviar_notificaciones_reparto` y `_var_info_carga_contenedor` a la lista ya importada desde `config.services.twilio_service`:

```python
from config.services.twilio_service import (
    _var_info_carga,
    _var_info_carga_contenedor,
    _numero_wa_mx,
    _sanitizar_texto,
    enviar_notificacion_bitacora,
    enviar_notificaciones_reparto,
    enviar_notificacion_operador,
    _cuerpo_email,
)
```

Agregar al final de `modulos/bitacoras/tests.py`:

```python
@override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
class EnviarNotificacionesRepartoTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-970')
        self.operador = Operador.objects.create(
            nombre='Kevin Márquez', tipo='LOCAL', telefono='7531573954'
        )
        self.cliente = Cliente.objects.create(nombre='Cliente Uno', celular='+5217531111111', email='uno@acme.mx')
        self.cliente_2 = Cliente.objects.create(nombre='Cliente Dos', celular='+5217532222222', email='dos@acme.mx')

    def _crear_viaje(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='FULL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            contenedor_2='PONU8765436',
            peso_2=Decimal('15.65'),
            tipo_contenedor='40',
            cp_destino='64000',
            cp_destino_2='64010',
            reparto=True,
            cliente=self.cliente,
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    def test_var_info_carga_contenedor_usa_datos_propios(self):
        viaje = self._crear_viaje()

        self.assertEqual(
            _var_info_carga_contenedor(viaje, 1),
            "Contenedor: MSKU1234567 | Especificaciones: Tipo 40 con peso de 28.05t | Destino Final: CP 64000"
        )
        self.assertEqual(
            _var_info_carga_contenedor(viaje, 2),
            "Contenedor: PONU8765436 | Especificaciones: Tipo 40 con peso de 15.65t | Destino Final: CP 64010"
        )

    @patch('config.services.twilio_service._twilio_client')
    def test_mismo_cliente_recibe_dos_notificaciones_independientes(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje()  # cliente_2 no asignado

        resultado = enviar_notificaciones_reparto(viaje)

        self.assertTrue(resultado['contenedor_1']['wa_ok'])
        self.assertTrue(resultado['contenedor_2']['wa_ok'])
        self.assertEqual(mock_messages.create.call_count, 2)

        llamadas = mock_messages.create.call_args_list
        destinos = {json.loads(c.kwargs['content_variables'])['1'] for c in llamadas}
        self.assertIn('Contenedor: MSKU1234567', ''.join(destinos))
        self.assertIn('Contenedor: PONU8765436', ''.join(destinos))
        for c in llamadas:
            self.assertEqual(c.kwargs['to'], 'whatsapp:+5217531111111')

    @patch('config.services.twilio_service._twilio_client')
    def test_cliente_2_distinto_recibe_su_propio_mensaje(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(cliente_2=self.cliente_2)

        resultado = enviar_notificaciones_reparto(viaje)

        self.assertTrue(resultado['contenedor_1']['wa_ok'])
        self.assertTrue(resultado['contenedor_2']['wa_ok'])
        llamadas = mock_messages.create.call_args_list
        destinatarios = {c.kwargs['to'] for c in llamadas}
        self.assertEqual(destinatarios, {'whatsapp:+5217531111111', 'whatsapp:+5217532222222'})

    @patch('config.services.twilio_service._twilio_client')
    def test_fecha_hora_entrega_2_vacia_usa_fecha_hora_entrega(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(fecha_hora_entrega=_aware(2026, 6, 23, 9))

        enviar_notificaciones_reparto(viaje)

        llamadas = mock_messages.create.call_args_list
        var2s = [json.loads(c.kwargs['content_variables'])['2'] for c in llamadas]
        self.assertTrue(all('Entrega: 23 jun 2026 09:00' in v for v in var2s))

    @patch('config.services.twilio_service._twilio_client')
    def test_fecha_hora_entrega_2_presente_se_usa_para_contenedor_2(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(
            fecha_hora_entrega=_aware(2026, 6, 23, 9),
            fecha_hora_entrega_2=_aware(2026, 6, 23, 15),
        )

        enviar_notificaciones_reparto(viaje)

        llamadas = mock_messages.create.call_args_list
        variables_por_llamada = [json.loads(c.kwargs['content_variables']) for c in llamadas]
        var2_contenedor_1 = next(v['2'] for v in variables_por_llamada if 'MSKU1234567' in v['1'])
        var2_contenedor_2 = next(v['2'] for v in variables_por_llamada if 'PONU8765436' in v['1'])
        self.assertIn('Entrega: 23 jun 2026 09:00', var2_contenedor_1)
        self.assertIn('Entrega: 23 jun 2026 15:00', var2_contenedor_2)

    @patch('config.services.twilio_service._twilio_client')
    def test_sin_cliente_en_contenedor_1_no_envia_esa_notificacion(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(cliente=None, cliente_2=self.cliente_2)

        resultado = enviar_notificaciones_reparto(viaje)

        self.assertIsNone(resultado['contenedor_1'])
        self.assertTrue(resultado['contenedor_2']['wa_ok'])
        self.assertEqual(mock_messages.create.call_count, 1)
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.EnviarNotificacionesRepartoTests -v 2`
Expected: `FAIL` con `ImportError: cannot import name 'enviar_notificaciones_reparto'` (ni `_var_info_carga_contenedor` existen todavía).

- [ ] **Step 3: Extraer el helper de envío WA+email**

En `config/services/twilio_service.py`, reemplazar el cuerpo de `enviar_notificacion_bitacora` (líneas 91-158) por una versión que usa un helper nuevo. Primero, agregar el helper **antes** de `enviar_notificacion_bitacora` (antes de la línea 91):

```python
def _enviar_wa_y_email_cliente(bitacora, cliente, variables: dict) -> dict:
    """
    Envía WhatsApp (template Twilio) + email a `cliente` con `variables` ya armadas.
    Mecanismo compartido entre la notificación combinada y las notificaciones
    divididas por contenedor (reparto).
    """
    resultado = {'wa_ok': False, 'email_ok': False}

    # ── WhatsApp ──────────────────────────────────────────────────────────────
    if cliente.celular and settings.TWILIO_CONTENT_SID_BITACORA:
        try:
            client = _twilio_client()
            client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=_numero_wa(cliente.celular),
                content_sid=settings.TWILIO_CONTENT_SID_BITACORA,
                content_variables=json.dumps(variables, ensure_ascii=False),
            )
            resultado['wa_ok'] = True
            logger.info("WA enviado a cliente %s (%s)", cliente.nombre, cliente.celular)
        except Exception as exc:
            logger.error("Error WA Twilio para cliente %s: %s", cliente.nombre, exc)
    else:
        if not cliente.celular:
            logger.warning("Cliente %s sin celular — WA omitido.", cliente.nombre)
        if not settings.TWILIO_CONTENT_SID_BITACORA:
            logger.warning("TWILIO_CONTENT_SID_BITACORA no configurado.")

    # ── Email ─────────────────────────────────────────────────────────────────
    if cliente.email:
        try:
            asunto = f"Programación de contenedores — {bitacora.fecha_salida.strftime('%d/%m/%Y') if bitacora.fecha_salida else ''}"
            cuerpo = _cuerpo_email(bitacora, variables)
            send_mail(
                subject=asunto,
                message=cuerpo,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[cliente.email],
                fail_silently=False,
            )
            resultado['email_ok'] = True
            logger.info("Email enviado a cliente %s (%s)", cliente.nombre, cliente.email)
        except Exception as exc:
            logger.error("Error email para cliente %s: %s", cliente.nombre, exc)
    else:
        logger.warning("Cliente %s sin email — correo omitido.", cliente.nombre)

    return resultado
```

Luego reemplazar el cuerpo completo de `enviar_notificacion_bitacora` (todo el rango original líneas 91-158) por:

```python
def enviar_notificacion_bitacora(bitacora, cliente) -> dict:
    """
    Envía WhatsApp (template Twilio) + email al cliente con los datos del viaje.

    Returns dict con claves 'wa_ok' (bool) y 'email_ok' (bool).
    """
    operador = bitacora.operador
    unidad = bitacora.unidad
    var1 = _var_info_carga(bitacora)

    # {{2}} — Detalles del Traslado
    telefono = getattr(operador, 'telefono', '') or ''
    var2 = (
        f"Unidad: {unidad.numero_economico} (Placas {unidad.placa}) | "
        f"Operador: {operador.nombre} {telefono} | "
        f"Salida: {_fecha_es(bitacora.fecha_salida)}"
    )

    # {{3}} — Notas Adicionales
    obs = _sanitizar_texto(bitacora.observaciones or 'SIN CUSTODIA')
    tipo_servicio = 'REPARTO' if bitacora.reparto else 'DIRECTO'
    var3 = f"Servicio {tipo_servicio} ejecutado {obs}."

    variables = {'1': var1, '2': var2, '3': var3}

    return _enviar_wa_y_email_cliente(bitacora, cliente, variables)
```

Esto es un refactor puro: mismo `var1`/`var2`/`var3`, mismo resultado observable — solo se extrajo el envío WA+email a `_enviar_wa_y_email_cliente`.

- [ ] **Step 4: Correr la suite existente y confirmar que no hay regresión**

Run: `python manage.py test modulos.bitacoras.tests.EnviarNotificacionBitacoraObservacionesTests modulos.bitacoras.tests.VarInfoCargaSaneamientoTests modulos.bitacoras.tests.VarInfoCargaTests -v 2`
Expected: `OK` — el refactor del Step 3 no cambió ningún resultado.

- [ ] **Step 5: Agregar `_var_info_carga_contenedor` y `enviar_notificaciones_reparto`**

En `config/services/twilio_service.py`, agregar después de `enviar_notificacion_bitacora` (y antes de `enviar_notificacion_operador`):

```python
def _var_info_carga_contenedor(bitacora, numero) -> str:
    """{{1}} para un solo contenedor — usado en notificaciones de reparto."""
    if numero == 2:
        contenedor = bitacora.contenedor_2 or '-'
        peso = bitacora.peso_2 or '-'
        cp_destino = bitacora.cp_destino_2 or '-'
    else:
        contenedor = bitacora.contenedor or '-'
        peso = bitacora.peso or '-'
        cp_destino = bitacora.cp_destino or '-'

    tipo = bitacora.tipo_contenedor or '-'
    especificaciones = f"Tipo {tipo} con peso de {peso}t"

    return f"Contenedor: {contenedor} | Especificaciones: {especificaciones} | Destino Final: CP {cp_destino}"


def _enviar_notificacion_contenedor(bitacora, numero, cliente, fecha_entrega) -> dict:
    """Arma variables para un solo contenedor (con su propio horario de entrega) y envía WA+email."""
    operador = bitacora.operador
    unidad = bitacora.unidad
    var1 = _var_info_carga_contenedor(bitacora, numero)

    telefono = getattr(operador, 'telefono', '') or ''
    var2 = (
        f"Unidad: {unidad.numero_economico} (Placas {unidad.placa}) | "
        f"Operador: {operador.nombre} {telefono} | "
        f"Salida: {_fecha_es(bitacora.fecha_salida)} | "
        f"Entrega: {_fecha_es(fecha_entrega)}"
    )

    obs = _sanitizar_texto(bitacora.observaciones or 'SIN CUSTODIA')
    var3 = f"Servicio REPARTO ejecutado (contenedor {numero}) {obs}."

    variables = {'1': var1, '2': var2, '3': var3}
    return _enviar_wa_y_email_cliente(bitacora, cliente, variables)


def enviar_notificaciones_reparto(bitacora) -> dict:
    """
    Envía dos notificaciones de cliente independientes (una por contenedor)
    para viajes con reparto=True. Cada una usa los datos propios de su
    contenedor (destino, cliente, horario de entrega), con fallback al
    contenedor 1 cuando el campo _2 correspondiente está vacío.

    Returns dict: {'contenedor_1': {...} | None, 'contenedor_2': {...} | None},
    mismo formato de resultado que enviar_notificacion_bitacora en cada entrada
    (None cuando ese contenedor no tiene cliente asignado).
    """
    resultado = {'contenedor_1': None, 'contenedor_2': None}

    if bitacora.cliente:
        resultado['contenedor_1'] = _enviar_notificacion_contenedor(
            bitacora, numero=1, cliente=bitacora.cliente,
            fecha_entrega=bitacora.fecha_hora_entrega,
        )

    cliente_2 = bitacora.cliente_2 or bitacora.cliente
    if cliente_2:
        resultado['contenedor_2'] = _enviar_notificacion_contenedor(
            bitacora, numero=2, cliente=cliente_2,
            fecha_entrega=bitacora.fecha_hora_entrega_2 or bitacora.fecha_hora_entrega,
        )

    return resultado
```

- [ ] **Step 6: Correr los tests nuevos y verificar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.EnviarNotificacionesRepartoTests -v 2`
Expected: `OK` (6 tests).

- [ ] **Step 7: Correr toda la suite del módulo**

Run: `python manage.py test modulos.bitacoras -v 2`
Expected: `OK`, sin regresiones.

- [ ] **Step 8: Commit**

```bash
git add config/services/twilio_service.py modulos/bitacoras/tests.py
git commit -m "Agrega envío de notificación dividida por contenedor en viajes con reparto"
```

---

### Task 4: Vista y plantilla de detalle

**Files:**
- Modify: `modulos/bitacoras/views.py:368-392` (`enviar_notificacion_cliente`)
- Modify: `templates/bitacoras/bitacora_detail.html:104-114` (botón "Notificar cliente"), `bitacora_detail.html:216-221` (bloque `fecha_hora_entrega`), `bitacora_detail.html:320-326` (bloque `cp_destino_2`)
- Test: `modulos/bitacoras/tests.py` (nueva clase `NotificarClienteRepartoViewTests`)

**Interfaces:**
- Consumes: `enviar_notificaciones_reparto(bitacora) -> dict` (Task 3), `enviar_notificacion_bitacora(bitacora, cliente) -> dict` (sin cambios), `BitacoraViaje.cliente_2`/`fecha_hora_entrega_2` (Task 1).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `modulos/bitacoras/tests.py`:

```python
class NotificarClienteRepartoViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester2', password='clave-segura-123')
        self.client.force_login(self.user)

        self.unidad = _crear_unidad(numero_economico='ECO-980')
        self.operador = Operador.objects.create(
            nombre='Kevin Márquez', tipo='LOCAL', telefono='7531573954'
        )
        self.cliente = Cliente.objects.create(nombre='Cliente Uno', celular='+5217531111111')
        self.cliente_2 = Cliente.objects.create(nombre='Cliente Dos', celular='+5217532222222')
        self.viaje = BitacoraViaje.objects.create(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='FULL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            contenedor_2='PONU8765436',
            peso_2=Decimal('15.65'),
            cp_destino='64000',
            cp_destino_2='64010',
            reparto=True,
            cliente=self.cliente,
            cliente_2=self.cliente_2,
        )

    @override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_reparto_notifica_a_los_dos_clientes(self, mock_client_fn):
        mock_client_fn.return_value.messages = MagicMock()

        response = self.client.post(
            reverse('bitacoras:notificar_cliente', args=[self.viaje.pk]), follow=True
        )

        self.assertEqual(mock_client_fn.return_value.messages.create.call_count, 2)
        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('Cliente Uno' in m and 'Cliente Dos' in m for m in mensajes))

    def test_reparto_sin_ningun_cliente_asignado_muestra_error(self):
        self.viaje.cliente = None
        self.viaje.cliente_2 = None
        self.viaje.save()

        with patch('config.services.twilio_service._twilio_client') as mock_client_fn:
            response = self.client.post(
                reverse('bitacoras:notificar_cliente', args=[self.viaje.pk]), follow=True
            )
            mock_client_fn.assert_not_called()

        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('no tiene cliente asignado' in m for m in mensajes))

    @override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_sin_reparto_sigue_notificando_a_un_solo_cliente(self, mock_client_fn):
        mock_client_fn.return_value.messages = MagicMock()
        self.viaje.reparto = False
        self.viaje.save()

        response = self.client.post(
            reverse('bitacoras:notificar_cliente', args=[self.viaje.pk]), follow=True
        )

        self.assertEqual(mock_client_fn.return_value.messages.create.call_count, 1)
        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('Cliente Uno' in m and 'WhatsApp enviado' in m for m in mensajes))
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.NotificarClienteRepartoViewTests -v 2`
Expected: `FAIL` — `test_reparto_notifica_a_los_dos_clientes` ve solo 1 llamada a Twilio (la vista todavía usa `enviar_notificacion_bitacora` sin importar el reparto).

- [ ] **Step 3: Reescribir la vista**

En `modulos/bitacoras/views.py`, reemplazar `enviar_notificacion_cliente` (líneas 368-392) por:

```python
@login_required
@require_POST
def enviar_notificacion_cliente(request, pk):
    """Envía WhatsApp + email al cliente asignado a la bitácora (o a los dos clientes, si el viaje tiene reparto)."""
    bitacora = get_object_or_404(BitacoraViaje, pk=pk)

    if bitacora.reparto:
        from config.services.twilio_service import enviar_notificaciones_reparto
        resultados = enviar_notificaciones_reparto(bitacora)
        destinatarios = [(1, bitacora.cliente), (2, bitacora.cliente_2 or bitacora.cliente)]

        if not any(cliente for _, cliente in destinatarios):
            messages.error(request, 'Esta bitácora no tiene cliente asignado.')
            return redirect('bitacoras:detail', pk=pk)

        partes = []
        for numero, cliente in destinatarios:
            if not cliente:
                partes.append(f"Contenedor {numero}: sin cliente asignado.")
                continue
            resultado = resultados[f'contenedor_{numero}']
            envios = []
            if resultado['wa_ok']:
                envios.append('WhatsApp enviado')
            if resultado['email_ok']:
                envios.append('correo enviado')
            estado = ', '.join(envios) if envios else 'no se pudo enviar'
            partes.append(f"Contenedor {numero} → {cliente.nombre}: {estado}.")

        messages.success(request, ' '.join(partes))
        return redirect('bitacoras:detail', pk=pk)

    if not bitacora.cliente:
        messages.error(request, 'Esta bitácora no tiene cliente asignado.')
        return redirect('bitacoras:detail', pk=pk)

    from config.services.twilio_service import enviar_notificacion_bitacora
    resultado = enviar_notificacion_bitacora(bitacora, bitacora.cliente)

    partes = []
    if resultado['wa_ok']:
        partes.append('WhatsApp enviado')
    if resultado['email_ok']:
        partes.append('correo enviado')

    if partes:
        messages.success(request, f"Notificación a {bitacora.cliente.nombre}: {', '.join(partes)}.")
    else:
        messages.error(request, f"No se pudo enviar la notificación a {bitacora.cliente.nombre}. Verifica celular, email y configuración de Twilio.")

    return redirect('bitacoras:detail', pk=pk)
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.NotificarClienteRepartoViewTests -v 2`
Expected: `OK` (3 tests).

- [ ] **Step 5: Actualizar el botón "Notificar cliente" en el detalle**

En `templates/bitacoras/bitacora_detail.html:104-114`, reemplazar:

```html
                {% if bitacora.cliente %}
                <form method="post" action="{% url 'bitacoras:notificar_cliente' bitacora.pk %}" class="inline">
                    {% csrf_token %}
                    <button type="submit"
                            class="inline-flex items-center gap-1.5 bg-green-50 hover:bg-green-100 text-green-700
                                   px-4 py-2 rounded-lg font-semibold text-sm transition min-h-[40px] border border-green-200">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
                        Notificar a {{ bitacora.cliente.nombre }}
                    </button>
                </form>
                {% endif %}
```

por:

```html
                {% if bitacora.cliente or bitacora.cliente_2 %}
                <form method="post" action="{% url 'bitacoras:notificar_cliente' bitacora.pk %}" class="inline">
                    {% csrf_token %}
                    <button type="submit"
                            class="inline-flex items-center gap-1.5 bg-green-50 hover:bg-green-100 text-green-700
                                   px-4 py-2 rounded-lg font-semibold text-sm transition min-h-[40px] border border-green-200">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
                        {% if bitacora.reparto %}Notificar clientes{% else %}Notificar a {{ bitacora.cliente.nombre }}{% endif %}
                    </button>
                </form>
                {% endif %}
```

- [ ] **Step 6: Mostrar `fecha_hora_entrega_2` en el detalle**

En `templates/bitacoras/bitacora_detail.html:216-221`, agregar inmediatamente después del bloque de `fecha_hora_entrega`:

```html
                    {% if bitacora.reparto and bitacora.fecha_hora_entrega_2 %}
                    <div class="dato-group">
                        <div class="dato-label">Fecha/Hora de Entrega (contenedor 2)</div>
                        <div class="dato-valor">{{ bitacora.fecha_hora_entrega_2|date:"d/m/Y H:i" }}</div>
                    </div>
                    {% endif %}
```

- [ ] **Step 7: Mostrar `cliente_2` en el detalle**

En `templates/bitacoras/bitacora_detail.html:320-326`, el bloque de "CP Destino 2 (reparto)" cierra el `<div class="grid grid-cols-2 gap-x-4">` en la línea 326. Agregar inmediatamente después de ese cierre (antes del comentario `<!-- Distancia Google Maps -->`):

```html
                {% if bitacora.reparto and bitacora.cliente_2 %}
                <div class="dato-group">
                    <div class="dato-label">Cliente (contenedor 2)</div>
                    <div class="dato-valor">{{ bitacora.cliente_2.nombre }}</div>
                </div>
                {% endif %}
```

- [ ] **Step 8: Verificar manualmente en el navegador**

Run: `python manage.py runserver`. Abrir el detalle de una bitácora FULL con `reparto=True`, `cliente` y `cliente_2` distintos, y `fecha_hora_entrega_2` capturada. Confirmar que se muestran ambos clientes y ambos horarios, y que el botón dice "Notificar clientes". Hacer clic en el botón (con `TWILIO_CONTENT_SID_BITACORA` configurado o no, según el entorno) y confirmar que el mensaje flash menciona ambos contenedores.

- [ ] **Step 9: Correr toda la suite del módulo**

Run: `python manage.py test modulos.bitacoras -v 2`
Expected: `OK`, todos los tests (preexistentes + nuevos) en verde.

- [ ] **Step 10: Commit**

```bash
git add modulos/bitacoras/views.py templates/bitacoras/bitacora_detail.html modulos/bitacoras/tests.py
git commit -m "Vista y detalle de bitácora notifican por separado a cada cliente en reparto"
```

---

## Verificación final

Run: `python manage.py test modulos.bitacoras -v 2`
Expected: `OK`, sin fallos ni errores, incluyendo las 4 clases de test nuevas (`RepartoValidacionModeloTests`, `BitacoraViajeFormRepartoValidacionTests`, `EnviarNotificacionesRepartoTests`, `NotificarClienteRepartoViewTests`) y todos los tests preexistentes intactos.
