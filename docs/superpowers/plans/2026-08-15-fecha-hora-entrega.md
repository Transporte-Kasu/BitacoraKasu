# Campo fecha_hora_entrega Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar un campo real `fecha_hora_entrega` (DateTimeField opcional) a `BitacoraViaje`, poblado desde la carga masiva de Excel y el formulario manual, y usarlo como fuente prioritaria en la notificación WhatsApp al operador.

**Architecture:** Extensión aditiva del modelo `BitacoraViaje` (nueva migración), del parser de Excel (`excel_parser.py`, extrae hora que hoy se descarta), de la vista/plantilla de carga masiva, del formulario/plantilla manual, del admin, del detalle, y de `enviar_notificacion_operador` (prioriza el dato real sobre el cálculo aproximado). No se modifica ni rompe ningún flujo existente.

**Tech Stack:** Django 5.2.7, openpyxl (parser de Excel), Django TestCase.

## Global Constraints

- Todo el código, comentarios y verbose_name en español.
- El campo es opcional (`null=True, blank=True`) — no todos los viajes traen cita de entrega.
- Un solo `DateTimeField` combinado (no fecha/hora separados), mismo patrón que `fecha_carga`/`fecha_salida`/`fecha_llegada`.
- Se captura tanto en la carga masiva por Excel como en el formulario manual de crear/editar bitácora.
- La notificación WhatsApp al operador usa `fecha_hora_entrega` cuando existe; si no, cae al cálculo aproximado ya existente (`fecha_salida + duracion_estimada`, o `fecha_salida` sola) — cascada de fallback, sin romper los casos ya cubiertos.
- No se modifica el cálculo existente de `fecha_salida`/`fecha_carga` como "día anterior a la hora configurada" en la carga masiva.
- No se agrega validación cruzada (ej. `fecha_hora_entrega` posterior a `fecha_salida`).
- Spec completo: `docs/superpowers/specs/2026-08-15-fecha-hora-entrega-design.md`.

---

## File Structure

- **Modify:** `modulos/bitacoras/models.py` — nuevo campo `fecha_hora_entrega`.
- **Create:** nueva migración en `modulos/bitacoras/migrations/` (autogenerada).
- **Modify:** `modulos/bitacoras/excel_parser.py` — `_parse_fecha_entrega` captura hora; `parse_confirmacion_excel` expone `fecha_hora_entrega` y `fecha_entrega_display` con hora.
- **Modify:** `modulos/bitacoras/views.py` — `carga_masiva_preview` (POST) lee y persiste `fecha_hora_entrega`.
- **Modify:** `templates/bitacoras/carga_masiva_preview.html` — nuevo input.
- **Modify:** `templates/bitacoras/carga_masiva.html` — texto "Formato esperado".
- **Modify:** `modulos/bitacoras/forms.py` — `BitacoraViajeForm` incluye el campo.
- **Modify:** `templates/bitacoras/bitacora_form.html` — grid de fechas a 3 columnas.
- **Modify:** `modulos/bitacoras/admin.py` — fieldset `'Fechas'`.
- **Modify:** `templates/bitacoras/bitacora_detail.html` — nuevo `dato-group` condicional.
- **Modify:** `config/services/twilio_service.py` — `enviar_notificacion_operador` prioriza el campo real.
- **Modify:** `modulos/bitacoras/tests.py` — todos los tests nuevos de este plan.

---

### Task 1: Modelo — campo `fecha_hora_entrega` y migración

**Files:**
- Modify: `modulos/bitacoras/models.py:103-114`
- Create: migración nueva (autogenerada por `makemigrations`)
- Test: `modulos/bitacoras/tests.py`

**Interfaces:**
- Produces: `BitacoraViaje.fecha_hora_entrega` (DateTimeField, `null=True, blank=True`) — consumido por Tasks 2-6.

- [ ] **Step 1: Escribir los tests que fijan el comportamiento del nuevo campo**

Agregar al final de `modulos/bitacoras/tests.py`:

```python
class FechaHoraEntregaModeloTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-400')
        self.operador = _crear_operador()

    def _crear_viaje(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            cp_origen='40812',
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    def test_por_defecto_es_none(self):
        viaje = self._crear_viaje()
        viaje.save()

        viaje_desde_db = BitacoraViaje.objects.get(pk=viaje.pk)

        self.assertIsNone(viaje_desde_db.fecha_hora_entrega)

    def test_se_guarda_y_recupera_correctamente(self):
        viaje = self._crear_viaje(fecha_hora_entrega=_aware(2026, 6, 25, 8, 0))
        viaje.save()

        viaje_desde_db = BitacoraViaje.objects.get(pk=viaje.pk)

        self.assertEqual(
            viaje_desde_db.fecha_hora_entrega.strftime('%Y-%m-%d %H:%M'),
            '2026-06-25 08:00'
        )
```

- [ ] **Step 2: Ejecutar los tests y confirmar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.FechaHoraEntregaModeloTests -v 2 --keepdb`
Expected: FAIL — `TypeError: BitacoraViaje() got unexpected keyword arguments: 'fecha_hora_entrega'`

- [ ] **Step 3: Agregar el campo al modelo**

En `modulos/bitacoras/models.py`, después de `fecha_llegada` (después de la línea 114, antes de la línea en blanco previa a "Combustible y kilometraje"):

```python
    fecha_hora_entrega = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha/hora de entrega",
    )
```

- [ ] **Step 4: Generar la migración**

Run: `python manage.py makemigrations bitacoras`
Expected: crea un archivo nuevo `modulos/bitacoras/migrations/0008_*.py` con una operación `AddField` sobre `fecha_hora_entrega`. Verificar el contenido del archivo generado — debe ser solo `AddField`, sin `RunPython`.

- [ ] **Step 5: Aplicar la migración**

Run: `python manage.py migrate bitacoras`
Expected: `Applying bitacoras.0008_..._fecha_hora_entrega... OK` (el nombre exacto lo decide Django).

- [ ] **Step 6: Ejecutar los tests y confirmar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.FechaHoraEntregaModeloTests -v 2 --keepdb`
Expected: PASS (2 tests)

- [ ] **Step 7: Ejecutar toda la suite de bitácoras**

Run: `python manage.py test modulos.bitacoras --keepdb -v 2`
Expected: todos los tests existentes siguen en PASS (18 + 2 nuevos = 20).

- [ ] **Step 8: Commit**

```bash
git add modulos/bitacoras/models.py modulos/bitacoras/migrations/ modulos/bitacoras/tests.py
git commit -m "Agrega campo fecha_hora_entrega a BitacoraViaje"
```

---

### Task 2: Parser de Excel — capturar hora de entrega

**Files:**
- Modify: `modulos/bitacoras/excel_parser.py`
- Test: `modulos/bitacoras/tests.py`

**Interfaces:**
- Consumes: nada nuevo (función pura).
- Produces: `_parse_fecha_entrega(raw) -> datetime | None` ahora incluye hora (antes solo fecha a medianoche). `parse_confirmacion_excel(...)` agrega la clave `'fecha_hora_entrega'` (string `%Y-%m-%dT%H:%M`, compatible con `<input type="datetime-local">`) a cada dict de viaje, y `'fecha_entrega_display'` cambia de formato `'%d/%m/%Y'` a `'%d/%m/%Y %H:%M'`. Consumido por Task 3 (template de preview) y por quien construya `BitacoraViaje` en `views.py`.

- [ ] **Step 1: Escribir los tests**

Agregar el import y las clases de test en `modulos/bitacoras/tests.py`:

```python
from io import BytesIO
import openpyxl
from modulos.bitacoras.excel_parser import _parse_fecha_entrega, parse_confirmacion_excel
```

```python
class ParseFechaEntregaTests(TestCase):
    def test_con_hora(self):
        resultado = _parse_fecha_entrega('25/06/2026    08:00 HRS')
        self.assertEqual(resultado, datetime(2026, 6, 25, 8, 0))

    def test_sin_hora_usa_medianoche(self):
        resultado = _parse_fecha_entrega('25/06/2026')
        self.assertEqual(resultado, datetime(2026, 6, 25, 0, 0))

    def test_vacio_retorna_none(self):
        self.assertIsNone(_parse_fecha_entrega(None))
        self.assertIsNone(_parse_fecha_entrega(''))


def _construir_excel_confirmacion(filas):
    """Construye un .xlsx en memoria con el encabezado esperado por parse_confirmacion_excel."""
    wb = openpyxl.Workbook()
    ws = wb.active
    header = [
        'FECHA ENTREGA / HORARIO', 'CONTENEDOR', 'CUSTODIA', 'DIRECCION CARTA PORTE',
        'DIRECCION DE ENTREGA', 'MODALIDAD', 'CONTACTO BODEGA', 'CODIGO SAT',
        'MERCANCIA', 'UNIDAD MEDIDA', 'CANTIDAD', 'PESOS (KG)', 'PEDIMENTO',
    ]
    ws.append(header)
    for fila in filas:
        ws.append(fila)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class ParseConfirmacionExcelFechaHoraEntregaTests(TestCase):
    def test_expone_fecha_hora_entrega_y_display_con_hora(self):
        archivo = _construir_excel_confirmacion([
            [
                '25/06/2026    08:00 HRS', 'MSKU1234567', 'CUSTORESCA',
                'Dirección carta porte X', 'Bodega Norte CP 90200',
                'SENCILLO', 'Juan', None, 'Caja fuerte', None, None, 28050, 'PED123',
            ],
        ])

        viajes = parse_confirmacion_excel(archivo, '17:00', '08:00', '40')

        self.assertEqual(len(viajes), 1)
        self.assertEqual(viajes[0]['fecha_hora_entrega'], '2026-06-25T08:00')
        self.assertEqual(viajes[0]['fecha_entrega_display'], '25/06/2026 08:00')

    def test_fila_sin_hora_en_la_celda_expone_medianoche(self):
        archivo = _construir_excel_confirmacion([
            [
                '25/06/2026', 'MSKU1234567', 'CUSTORESCA',
                'Dirección carta porte X', 'Bodega Norte CP 90200',
                'SENCILLO', 'Juan', None, 'Caja fuerte', None, None, 28050, 'PED123',
            ],
        ])

        viajes = parse_confirmacion_excel(archivo, '17:00', '08:00', '40')

        self.assertEqual(viajes[0]['fecha_hora_entrega'], '2026-06-25T00:00')
        self.assertEqual(viajes[0]['fecha_entrega_display'], '25/06/2026 00:00')
```

- [ ] **Step 2: Ejecutar los tests y confirmar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.ParseFechaEntregaTests modulos.bitacoras.tests.ParseConfirmacionExcelFechaHoraEntregaTests -v 2 --keepdb`
Expected: FAIL — `test_con_hora` falla porque `_parse_fecha_entrega` hoy descarta la hora (`datetime(2026, 6, 25, 0, 0) != datetime(2026, 6, 25, 8, 0)`); los tests de `parse_confirmacion_excel` fallan con `KeyError: 'fecha_hora_entrega'`.

- [ ] **Step 3: Extender `_parse_fecha_entrega` para capturar la hora**

En `modulos/bitacoras/excel_parser.py`, reemplazar (líneas 13-21):

```python
def _parse_fecha_entrega(raw):
    if not raw:
        return None
    s = str(raw).strip()
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if not m:
        return None
    day, month, year = m.groups()
    return datetime(int(year), int(month), int(day))
```

por:

```python
def _parse_fecha_entrega(raw):
    if not raw:
        return None
    s = str(raw).strip()
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if not m:
        return None
    day, month, year = m.groups()
    hora, minuto = 0, 0
    m_hora = re.search(r'(\d{1,2}):(\d{2})', s)
    if m_hora:
        hora, minuto = int(m_hora.group(1)), int(m_hora.group(2))
    return datetime(int(year), int(month), int(day), hora, minuto)
```

- [ ] **Step 4: Exponer `fecha_hora_entrega` y actualizar `fecha_entrega_display` en el dict de salida**

En `modulos/bitacoras/excel_parser.py`, dentro de la construcción de `current` (línea 118), reemplazar:

```python
                'fecha_entrega_display': fecha_entrega.strftime('%d/%m/%Y') if fecha_entrega else '',
```

por:

```python
                'fecha_entrega_display': fecha_entrega.strftime('%d/%m/%Y %H:%M') if fecha_entrega else '',
                'fecha_hora_entrega':    fecha_entrega.strftime('%Y-%m-%dT%H:%M') if fecha_entrega else '',
```

- [ ] **Step 5: Ejecutar los tests y confirmar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.ParseFechaEntregaTests modulos.bitacoras.tests.ParseConfirmacionExcelFechaHoraEntregaTests -v 2 --keepdb`
Expected: PASS (5 tests)

- [ ] **Step 6: Ejecutar toda la suite de bitácoras**

Run: `python manage.py test modulos.bitacoras --keepdb -v 2`
Expected: todos los tests en PASS.

- [ ] **Step 7: Commit**

```bash
git add modulos/bitacoras/excel_parser.py modulos/bitacoras/tests.py
git commit -m "Parser de Excel captura hora de entrega (antes se descartaba)"
```

---

### Task 3: Carga masiva — vista y plantilla

**Files:**
- Modify: `modulos/bitacoras/views.py:510-552` (función `carga_masiva_preview`, rama POST)
- Modify: `templates/bitacoras/carga_masiva_preview.html:287-302`
- Modify: `templates/bitacoras/carga_masiva.html:180-193`
- Test: `modulos/bitacoras/tests.py`

**Interfaces:**
- Consumes: `BitacoraViaje.fecha_hora_entrega` (Task 1). El dict `viaje.fecha_hora_entrega` (string `%Y-%m-%dT%H:%M` o `''`) que produce `parse_confirmacion_excel` (Task 2) llega al template vía `viajes` en sesión — no requiere cambios adicionales de wiring, ya que la vista GET ya pasa `viajes` completo al template.
- Produces: nada nuevo para otras tasks — es el punto final de la carga masiva.

- [ ] **Step 1: Escribir los tests de la vista**

Agregar la clase de test en `modulos/bitacoras/tests.py` (requiere `from django.urls import reverse`, ya importado):

```python
class CargaMasivaFechaHoraEntregaTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester_carga', password='clave-segura-123')
        self.client.force_login(self.user)
        self.unidad = _crear_unidad(numero_economico='ECO-500')
        self.operador = _crear_operador()

    def _datos_post(self, **overrides):
        datos = {
            'total_viajes': '1',
            'v0_modalidad': 'SENCILLO',
            'v0_contenedor': 'MSKU1234567',
            'v0_peso': '28.05',
            'v0_destino': 'Bodega Norte, Monterrey',
            'v0_cp_destino': '90200',
            'v0_fecha_salida': '2026-06-24T17:00',
            'v0_fecha_carga': '2026-06-24T08:00',
            'v0_tipo_contenedor': '40',
            'v0_operador': str(self.operador.pk),
            'v0_unidad': str(self.unidad.pk),
        }
        datos.update(overrides)
        return datos

    def test_post_con_fecha_hora_entrega_la_persiste(self):
        response = self.client.post(
            reverse('bitacoras:carga_masiva_preview'),
            self._datos_post(v0_fecha_hora_entrega='2026-06-25T08:00'),
        )

        self.assertEqual(response.status_code, 302)
        viaje = BitacoraViaje.objects.get(contenedor='MSKU1234567')
        self.assertEqual(
            viaje.fecha_hora_entrega.strftime('%Y-%m-%d %H:%M'),
            '2026-06-25 08:00'
        )

    def test_post_sin_fecha_hora_entrega_guarda_none(self):
        response = self.client.post(
            reverse('bitacoras:carga_masiva_preview'),
            self._datos_post(),
        )

        self.assertEqual(response.status_code, 302)
        viaje = BitacoraViaje.objects.get(contenedor='MSKU1234567')
        self.assertIsNone(viaje.fecha_hora_entrega)
```

- [ ] **Step 2: Ejecutar los tests y confirmar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.CargaMasivaFechaHoraEntregaTests -v 2 --keepdb`
Expected: ambos tests PASAN en `guarda_none` (ya es el comportamiento actual, el campo no existía) pero `test_post_con_fecha_hora_entrega_la_persiste` FALLA porque la vista no lee `v0_fecha_hora_entrega` — `viaje.fecha_hora_entrega` queda en `None` en vez de la fecha esperada.

- [ ] **Step 3: Leer y persistir el campo en la vista**

En `modulos/bitacoras/views.py`, dentro del `for i in range(total):` de `carga_masiva_preview` (POST), agregar la lectura junto a las demás (después de la línea `fecha_car_str = request.POST.get(f'{p}fecha_carga', '')`, línea 523):

```python
            fecha_entrega_str = request.POST.get(f'{p}fecha_hora_entrega', '').strip()
```

Y en la construcción de `BitacoraViaje(...)` (líneas 535-552), agregar el campo junto a `fecha_carga`/`fecha_salida`:

```python
                fecha_hora_entrega = datetime.fromisoformat(fecha_entrega_str) if fecha_entrega_str else None,
```

A diferencia de `fecha_salida`/`fecha_carga`, **no** se agrega a la validación de la línea 531-533 (`if not fecha_sal_str or not fecha_car_str: ... continue`) — el campo es opcional, una fila sin este dato no debe generar error.

- [ ] **Step 4: Agregar el input en el template de preview**

En `templates/bitacoras/carga_masiva_preview.html`, dentro de "Fechas calculadas" (después de la línea 300, antes del `</div>` de la línea 301):

```html
                            <div>
                                <label class="block text-[11px] text-slate-400 mb-0.5">Fecha y hora de entrega</label>
                                <input type="datetime-local" name="v{{ idx }}_fecha_hora_entrega"
                                       value="{{ viaje.fecha_hora_entrega }}" class="form-control text-xs">
                            </div>
```

Nótese: sin `required`, a diferencia de los inputs de `fecha_carga`/`fecha_salida`.

- [ ] **Step 5: Actualizar el texto de "Formato esperado"**

En `templates/bitacoras/carga_masiva.html`, reemplazar la línea 184:

```html
                    <li><span class="font-semibold">Col A</span> — Fecha de entrega (DD/MM/YYYY)</li>
```

por:

```html
                    <li><span class="font-semibold">Col A</span> — Fecha y hora de entrega (DD/MM/YYYY HH:MM)</li>
```

- [ ] **Step 6: Ejecutar los tests y confirmar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.CargaMasivaFechaHoraEntregaTests -v 2 --keepdb`
Expected: PASS (2 tests)

- [ ] **Step 7: Ejecutar toda la suite de bitácoras**

Run: `python manage.py test modulos.bitacoras --keepdb -v 2`
Expected: todos los tests en PASS.

- [ ] **Step 8: Commit**

```bash
git add modulos/bitacoras/views.py templates/bitacoras/carga_masiva_preview.html templates/bitacoras/carga_masiva.html modulos/bitacoras/tests.py
git commit -m "Carga masiva persiste fecha_hora_entrega desde el Excel"
```

---

### Task 4: Formulario manual — captura y plantilla

**Files:**
- Modify: `modulos/bitacoras/forms.py:25-41,61-68`
- Modify: `templates/bitacoras/bitacora_form.html:317-346`
- Test: `modulos/bitacoras/tests.py`

**Interfaces:**
- Consumes: `BitacoraViaje.fecha_hora_entrega` (Task 1).
- Produces: `BitacoraViajeForm` valida y persiste `fecha_hora_entrega` como campo opcional — consumido por el flujo estándar de creación/edición manual (`BitacoraCreateView`/`BitacoraUpdateView`, sin cambios de código ahí ya que usan el form tal cual).

- [ ] **Step 1: Escribir los tests del formulario**

Agregar el import y la clase de test en `modulos/bitacoras/tests.py`:

```python
from .forms import BitacoraViajeForm
```

```python
class BitacoraViajeFormFechaHoraEntregaTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-600')
        self.operador = _crear_operador()

    def _datos_base(self, **overrides):
        datos = dict(
            modalidad='LOCAL',
            operador=self.operador.pk,
            unidad=self.unidad.pk,
            fecha_carga='2026-06-22T08:00',
            fecha_salida='2026-06-22T17:00',
            contenedor='MSKU1234567',
            tipo_contenedor='40',
            peso='28.05',
            cp_origen='40812',
            destino='Bodega Norte, Monterrey',
        )
        datos.update(overrides)
        return datos

    def test_valido_sin_fecha_hora_entrega(self):
        form = BitacoraViajeForm(data=self._datos_base())

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['fecha_hora_entrega'])

    def test_valido_con_fecha_hora_entrega(self):
        form = BitacoraViajeForm(data=self._datos_base(fecha_hora_entrega='2026-06-21T08:00'))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['fecha_hora_entrega'].strftime('%Y-%m-%d %H:%M'),
            '2026-06-21 08:00'
        )
```

- [ ] **Step 2: Ejecutar los tests y confirmar que fallan**

Run: `python manage.py test modulos.bitacoras.tests.BitacoraViajeFormFechaHoraEntregaTests -v 2 --keepdb`
Expected: FAIL — `KeyError: 'fecha_hora_entrega'` en `form.cleaned_data` (el campo no está en `Meta.fields`, así que ni siquiera aparece en el formulario).

- [ ] **Step 3: Agregar el campo al formulario**

En `modulos/bitacoras/forms.py`, en `BitacoraViajeForm.Meta.fields` (líneas 25-41), agregar `'fecha_hora_entrega'` justo después de `'fecha_salida'`:

```python
        fields = [
            'cliente',
            'modalidad',
            'operador', 'unidad',
            'salida_a_ruta',
            'fecha_carga',
            'fecha_salida',
            'fecha_hora_entrega',
            # Contenedor 1
            'contenedor', 'tipo_contenedor', 'peso', 'sellos',
            # Contenedor 2 (solo FULL)
            'contenedor_2', 'peso_2', 'sellos_2',
            'reparto',
            # Destino
            'cp_origen', 'cp_destino', 'cp_destino_2', 'destino', 'domicilio_carta_porte',
            # Opcional
            'observaciones',
        ]
```

Y en `widgets` (después del bloque de `'fecha_salida'`, líneas 65-68):

```python
            'fecha_hora_entrega': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
```

- [ ] **Step 4: Ejecutar los tests y confirmar que pasan**

Run: `python manage.py test modulos.bitacoras.tests.BitacoraViajeFormFechaHoraEntregaTests -v 2 --keepdb`
Expected: PASS (2 tests)

- [ ] **Step 5: Agregar el campo al template del formulario**

En `templates/bitacoras/bitacora_form.html`, card "Fecha" (líneas 317-346): cambiar el grid de `sm:grid-cols-2` a `sm:grid-cols-3` (línea 326) y agregar el tercer campo después del bloque de `form.fecha_salida` (después de la línea 344, antes del `</div>` de cierre del grid en línea 345):

```html
                    <div>
                        <label for="{{ form.fecha_hora_entrega.id_for_label }}" class="block text-sm font-medium text-slate-700 mb-1.5">
                            Fecha/hora de entrega
                        </label>
                        {{ form.fecha_hora_entrega }}
                        {% if form.fecha_hora_entrega.errors %}
                        <p class="mt-1 text-xs text-red-600" role="alert">{{ form.fecha_hora_entrega.errors|join:", " }}</p>
                        {% endif %}
                    </div>
```

Nótese: sin el `<span class="text-red-500" aria-hidden="true">*</span>` que tienen los otros dos labels — este campo es opcional.

- [ ] **Step 6: Ejecutar toda la suite de bitácoras**

Run: `python manage.py test modulos.bitacoras --keepdb -v 2`
Expected: todos los tests en PASS.

- [ ] **Step 7: Verificar manualmente en el navegador**

Run: `python manage.py runserver`

Abrir `http://127.0.0.1:8000/bitacoras/crear/`, confirmar que la card "Fecha" ahora muestra 3 columnas (Fecha de carga, Fecha de salida, Fecha/hora de entrega) y que el tercer campo no tiene asterisco de obligatorio ni bloquea el envío del formulario si se deja vacío.

- [ ] **Step 8: Commit**

```bash
git add modulos/bitacoras/forms.py templates/bitacoras/bitacora_form.html modulos/bitacoras/tests.py
git commit -m "Formulario manual de bitácora captura fecha_hora_entrega"
```

---

### Task 5: Admin y detalle — mostrar `fecha_hora_entrega`

**Files:**
- Modify: `modulos/bitacoras/admin.py:48-50`
- Modify: `templates/bitacoras/bitacora_detail.html:204-234`

**Interfaces:**
- Consumes: `BitacoraViaje.fecha_hora_entrega` (Task 1). Sin producir nada nuevo — es la capa de visualización final.

No hay tests automatizados nuevos en esta tarea (cambios puramente de admin/plantilla, mismo patrón que la Task 5 del plan anterior de notificación WhatsApp) — se verifica por inspección y por la suite completa.

- [ ] **Step 1: Agregar el campo al fieldset del admin**

En `modulos/bitacoras/admin.py`, reemplazar (línea 48-50):

```python
        ('Fechas', {
            'fields': ('fecha_carga', 'fecha_salida', 'fecha_llegada', 'completado')
        }),
```

por:

```python
        ('Fechas', {
            'fields': ('fecha_carga', 'fecha_salida', 'fecha_hora_entrega', 'fecha_llegada', 'completado')
        }),
```

- [ ] **Step 2: Mostrar el campo en el detalle de bitácora**

En `templates/bitacoras/bitacora_detail.html`, dentro de la tarjeta "Fechas y Combustible" (líneas 204-234), agregar después del bloque de "Fecha de Salida" (después de la línea 215, antes del `{% if bitacora.fecha_llegada %}` de la línea 216):

```html
                    {% if bitacora.fecha_hora_entrega %}
                    <div class="dato-group">
                        <div class="dato-label">Fecha/Hora de Entrega</div>
                        <div class="dato-valor">{{ bitacora.fecha_hora_entrega|date:"d/m/Y H:i" }}</div>
                    </div>
                    {% endif %}
```

- [ ] **Step 3: Ejecutar toda la suite de bitácoras**

Run: `python manage.py test modulos.bitacoras --keepdb -v 2`
Expected: todos los tests en PASS (sin regresión — cambios puramente de visualización).

- [ ] **Step 4: Verificar manualmente en el navegador**

Run: `python manage.py runserver` (si no sigue corriendo de la tarea anterior)

Abrir el detalle de una bitácora con `fecha_hora_entrega` establecida (la creada en la Task 4 o en el admin) y confirmar que la tarjeta "Fechas y Combustible" muestra "Fecha/Hora de Entrega" entre "Fecha de Salida" y "Fecha de Llegada". Abrir una bitácora sin ese dato y confirmar que la fila no aparece (sin `-` vacío ni error).

- [ ] **Step 5: Commit**

```bash
git add modulos/bitacoras/admin.py templates/bitacoras/bitacora_detail.html
git commit -m "Muestra fecha_hora_entrega en admin y detalle de bitácora"
```

---

### Task 6: Notificación WhatsApp — priorizar `fecha_hora_entrega` real

**Files:**
- Modify: `config/services/twilio_service.py:155-159`
- Test: `modulos/bitacoras/tests.py`

**Interfaces:**
- Consumes: `BitacoraViaje.fecha_hora_entrega` (Task 1).
- Produces: `enviar_notificacion_operador(bitacora)` (ya existente) — mismo contrato (`dict` con `'wa_ok'`), solo cambia la prioridad de cálculo de `{{2}}`.

- [ ] **Step 1: Escribir el test**

Agregar el test dentro de `EnviarNotificacionOperadorTests` (después de `test_horario_de_entrega_usa_hora_local_no_utc`, en `modulos/bitacoras/tests.py`):

```python
    @patch('config.services.twilio_service._twilio_client')
    def test_usa_fecha_hora_entrega_real_cuando_esta_presente(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(
            duracion_estimada=411,
            fecha_hora_entrega=_aware(2026, 6, 25, 8, 0),
        )

        resultado = enviar_notificacion_operador(viaje)

        self.assertTrue(resultado['wa_ok'])
        kwargs = mock_messages.create.call_args.kwargs
        variables = json.loads(kwargs['content_variables'])
        self.assertEqual(
            variables['2'],
            "Destino: BODEGA NORTE, MONTERREY | Horario de entrega: 25 jun 2026 08:00"
        )
```

Nótese que este test fija `duracion_estimada=411` **a la vez** que `fecha_hora_entrega`, para probar que el dato real gana la prioridad sobre el cálculo por duración (que por sí solo daría `22 jun 2026 23:51`, no `25 jun 2026 08:00`).

- [ ] **Step 2: Ejecutar el test y confirmar que falla**

Run: `python manage.py test modulos.bitacoras.tests.EnviarNotificacionOperadorTests.test_usa_fecha_hora_entrega_real_cuando_esta_presente -v 2 --keepdb`
Expected: FAIL — `AssertionError` porque `variables['2']` contiene `22 jun 2026 23:51` (calculado por duración) en vez de `25 jun 2026 08:00` (el dato real, aún no priorizado).

- [ ] **Step 3: Priorizar `fecha_hora_entrega` en el servicio**

En `config/services/twilio_service.py`, reemplazar (líneas 155-159):

```python
    # {{2}} — Detalles del Traslado (versión operador: destino + horario de entrega)
    if bitacora.duracion_estimada:
        hora_entrega = bitacora.fecha_salida + timedelta(minutes=bitacora.duracion_estimada)
    else:
        hora_entrega = bitacora.fecha_salida
```

por:

```python
    # {{2}} — Detalles del Traslado (versión operador: destino + horario de entrega)
    if bitacora.fecha_hora_entrega:
        hora_entrega = bitacora.fecha_hora_entrega
    elif bitacora.duracion_estimada:
        hora_entrega = bitacora.fecha_salida + timedelta(minutes=bitacora.duracion_estimada)
    else:
        hora_entrega = bitacora.fecha_salida
```

- [ ] **Step 4: Ejecutar el test y confirmar que pasa**

Run: `python manage.py test modulos.bitacoras.tests.EnviarNotificacionOperadorTests -v 2 --keepdb`
Expected: PASS (todos los tests de la clase, incluyendo el nuevo — los casos existentes de fallback por duración y por `fecha_salida` sola siguen pasando sin cambios, ya que construyen bitácoras sin `fecha_hora_entrega`, que por defecto es `None`).

- [ ] **Step 5: Ejecutar toda la suite de bitácoras**

Run: `python manage.py test modulos.bitacoras --keepdb -v 2`
Expected: todos los tests en PASS.

- [ ] **Step 6: Commit**

```bash
git add config/services/twilio_service.py modulos/bitacoras/tests.py
git commit -m "Notificación WhatsApp al operador prioriza fecha_hora_entrega real sobre el cálculo aproximado"
```

---

## Self-Review Summary

- **Cobertura del spec:** Task 1 cubre "1. Modelo"; Task 2 cubre "2. Parser de Excel"; Task 3 cubre "3. Carga masiva"; Task 4 cubre "4. Formulario manual"; Task 5 cubre "5. Admin" y "6. Detalle de bitácora"; Task 6 cubre "7. Notificación WhatsApp al operador". La sección "Fuera de alcance" del spec no requiere tareas (confirma explícitamente qué NO se construye).
- **Placeholders:** ninguno — cada step trae código completo y ejecutable, y los fixtures de test (Excel en memoria, datos POST, datos de formulario) están completos.
- **Consistencia de tipos:** `BitacoraViaje.fecha_hora_entrega` (Task 1) es el mismo campo que consumen Tasks 3-6 sin reinterpretación. `parse_confirmacion_excel(...)` (Task 2) produce la clave `'fecha_hora_entrega'` en formato string `%Y-%m-%dT%H:%M` — exactamente el formato que el input `datetime-local` del template (Task 3) espera como `value`, y el mismo formato que ya usan `fecha_salida`/`fecha_carga` en el mismo dict. `enviar_notificacion_operador` (Task 6) sigue devolviendo `dict` con `'wa_ok'` — mismo contrato que ya consume la vista `enviar_notificacion_operador` en `views.py` (feature anterior), sin cambios ahí.
