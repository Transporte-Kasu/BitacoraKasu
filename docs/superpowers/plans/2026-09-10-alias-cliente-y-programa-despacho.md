# Alias de Cliente + reporte "Programa de despacho" (.xlsx) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar `Cliente.alias` (código corto que agrupa viajes y modulaciones) y una vista en `modulacion` que descarga un `.xlsx` "Programa de despacho" con las modulaciones de una fecha, agrupadas y ordenadas por el alias del cliente.

**Architecture:** El alias vive en `modulos/bitacoras/models.py` (`Cliente`). El reporte tiene un builder puro `modulos/modulacion/reportes.py::construir_programa_despacho(fecha) -> openpyxl.Workbook` (testeable sin HTTP) y una vista fina que lo envuelve en una `HttpResponse` de descarga. Dos campos nuevos alimentan el reporte: `TerminalPortuaria.nombre_corto` y `Modulacion.sello_colocado`.

**Tech Stack:** Django 5.2.7, Python 3.12 (`.venvKasu`), `openpyxl==3.1.5` (ya en `requirements.txt`), SQLite en tests.

## Global Constraints

- Django `5.2.7`; ejecutar todo con `.venvKasu/bin/python`.
- Pruebas: `.venvKasu/bin/python manage.py test <ruta> --settings=test_settings` (SQLite en memoria). No hay pytest.
- Idioma español en nombres de modelo/campo, `verbose_name`, comentarios y textos de UI.
- `TIME_ZONE = 'America/Mexico_City'`; los `DateTimeField` se guardan aware; para mostrar horas usar `django.utils.timezone.localtime`.
- Vistas con `LoginRequiredMixin` (CBV) o `@login_required` (FBV).
- `openpyxl` ya está instalado y fijado; no tocar `requirements.txt`.
- El reporte se ordena/agrupa **por alias de cliente** (no por terminal como la captura del usuario). Cada bloque de un mismo alias lleva una fila-encabezado combinada `"{alias} — N maniobra(s)"`.
- El reporte **solo** se entrega como `.xlsx` (sin tabla en pantalla). DODA y las columnas A–E de la captura quedan fuera; el reporte arranca en la columna A = "FECHA DE DESPACHO".
- Los tests nuevos del reporte van en `modulos/modulacion/tests_reporte.py` (archivo nuevo; `tests.py` y `tests_estados.py`/`tests_lctpc.py` ya existen).
- Fecha "28-ago-26": mapa de meses ES propio, sin depender del locale del SO.
- Ruido conocido en stderr al correr tests: `Invalid line: MODULACION_LCTPC_* = '...'` del `.env` local — preexistente, ignorar.

---

## Estructura de archivos

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `modulos/bitacoras/models.py` | Modificar | `Cliente.alias` + `Cliente.etiqueta` |
| `modulos/bitacoras/forms.py` | Modificar | `alias` en `ClienteForm` |
| `modulos/bitacoras/admin.py` | Modificar | `alias` en `ClienteAdmin` |
| `modulos/bitacoras/views.py` | Modificar | `alias` en la búsqueda de `ClienteListView` |
| `templates/bitacoras/cliente_form.html` | Modificar | campo Alias |
| `templates/bitacoras/cliente_list.html` | Modificar | columna Alias |
| `modulos/bitacoras/migrations/0010_cliente_alias.py` | Crear (auto) | `AddField` |
| `modulos/bitacoras/tests_alias.py` | Crear | pruebas de `Cliente.etiqueta` y el form |
| `modulos/modulacion/models.py` | Modificar | `TerminalPortuaria.nombre_corto` + `etiqueta`; `Modulacion.sello_colocado` |
| `modulos/modulacion/forms.py` | Modificar | `sello_colocado` en `ModulacionForm` |
| `modulos/modulacion/admin.py` | Modificar | `nombre_corto` / `sello_colocado` |
| `templates/modulacion/modulacion_detail.html` | Modificar | mostrar `Sello` |
| `modulos/modulacion/migrations/0009_terminal_nombre_corto_y_sello.py` | Crear (auto) | 2 `AddField` |
| `modulos/modulacion/reportes.py` | Crear | `construir_programa_despacho()` + helpers |
| `modulos/modulacion/views.py` | Modificar | `ReporteProgramaDespachoView`, `descargar_programa_despacho` |
| `modulos/modulacion/urls.py` | Modificar | 2 rutas |
| `templates/modulacion/reporte_despacho.html` | Crear | form de fecha + botón descargar |
| `templates/modulacion/dashboard.html` | Modificar | enlace "Programa de despacho" |
| `modulos/modulacion/tests_reporte.py` | Crear | pruebas del builder y la vista |

---

## Task 1: `Cliente.alias` (app bitacoras)

**Files:**
- Modify: `modulos/bitacoras/models.py`
- Modify: `modulos/bitacoras/forms.py`
- Modify: `modulos/bitacoras/admin.py`
- Modify: `modulos/bitacoras/views.py`
- Modify: `templates/bitacoras/cliente_form.html`
- Modify: `templates/bitacoras/cliente_list.html`
- Create: `modulos/bitacoras/migrations/0010_cliente_alias.py` (auto)
- Create: `modulos/bitacoras/tests_alias.py`

**Interfaces:**
- Produces:
  - `Cliente.alias: str` (`CharField(max_length=20, blank=True)`)
  - `Cliente.etiqueta -> str` (property) — `self.alias or self.nombre`

- [ ] **Step 1: Escribir `tests_alias.py` (falla)**

Crear `modulos/bitacoras/tests_alias.py`:

```python
from django.test import TestCase

from modulos.bitacoras.forms import ClienteForm
from modulos.bitacoras.models import Cliente


class ClienteAliasTests(TestCase):
    def test_etiqueta_usa_alias_si_hay(self):
        c = Cliente(nombre='Transportes Moya SA', alias='MOY')
        self.assertEqual(c.etiqueta, 'MOY')

    def test_etiqueta_cae_al_nombre_si_no_hay_alias(self):
        c = Cliente(nombre='Nolasco SA')
        self.assertEqual(c.etiqueta, 'Nolasco SA')

    def test_form_guarda_alias(self):
        form = ClienteForm(data={
            'nombre': 'Zeta SA', 'alias': 'ZEEV', 'email': '', 'celular': '',
            'activo': True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        cliente = form.save()
        self.assertEqual(cliente.alias, 'ZEEV')
```

- [ ] **Step 2: Correr — falla**

Run: `.venvKasu/bin/python manage.py test modulos.bitacoras.tests_alias --settings=test_settings -v 2`
Expected: FAIL — `AttributeError: 'Cliente' object has no attribute 'etiqueta'` / el form ignora `alias`.

- [ ] **Step 3: Agregar el campo y la property**

En `modulos/bitacoras/models.py`, dentro de `class Cliente`, después de `nombre = models.CharField(...)`:

```python
    alias = models.CharField(
        max_length=20, blank=True, verbose_name="Alias",
        help_text="Código corto para agrupar viajes y modulaciones en reportes.",
    )
```

Y después de `def __str__`:

```python
    @property
    def etiqueta(self):
        """Alias corto si hay; si no, el nombre completo."""
        return self.alias or self.nombre
```

- [ ] **Step 4: Form**

En `modulos/bitacoras/forms.py`, `ClienteForm.Meta.fields`, agregar `'alias'` después de `'nombre'`:

```python
        fields = ['nombre', 'alias', 'email', 'celular', 'activo']
```

Y en `widgets`, agregar:

```python
            'alias': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'MOY'}),
```

- [ ] **Step 5: Template del form**

En `templates/bitacoras/cliente_form.html`, justo después del bloque `<!-- Nombre -->` (antes de `<!-- Email -->`):

```html
            <!-- Alias -->
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Alias</label>
                {{ form.alias }}
                <p class="text-xs text-gray-400 mt-1">Código corto para agrupar en reportes (ej. MOY, NOLASCO).</p>
                {% if form.alias.errors %}
                <p class="text-xs text-red-500 mt-1">{{ form.alias.errors.0 }}</p>
                {% endif %}
            </div>
```

- [ ] **Step 6: Admin y búsqueda de la lista**

En `modulos/bitacoras/admin.py`, `ClienteAdmin`:

```python
    list_display = ['nombre', 'alias', 'email', 'celular', 'activo', 'created_at']
    list_editable = ['alias']
    list_filter = ['activo']
    search_fields = ['nombre', 'alias', 'email', 'celular']
```

En `modulos/bitacoras/views.py`, `ClienteListView.get_queryset`, agregar `alias` al `Q`:

```python
            qs = qs.filter(
                Q(nombre__icontains=q) | Q(alias__icontains=q)
                | Q(email__icontains=q) | Q(celular__icontains=q)
            )
```

En `templates/bitacoras/cliente_list.html`, agregar la columna Alias: un `<th class="px-4 py-3">Alias</th>` después del de "Nombre", y una celda `<td class="px-4 py-3 text-gray-600">{{ cliente.alias|default:"—" }}</td>` después de la de `cliente.nombre`.

- [ ] **Step 7: Migración**

```bash
.venvKasu/bin/python manage.py makemigrations bitacoras --name cliente_alias
.venvKasu/bin/python manage.py migrate --settings=test_settings
```

Expected: crea `0010_cliente_alias.py` con un solo `AddField`; `migrate` sin errores.

- [ ] **Step 8: Correr — verde**

Run: `.venvKasu/bin/python manage.py test modulos.bitacoras.tests_alias --settings=test_settings -v 2`
Expected: PASS (3 tests).

- [ ] **Step 9: Regresión de bitacoras**

Run: `.venvKasu/bin/python manage.py test modulos.bitacoras --settings=test_settings`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add modulos/bitacoras/ templates/bitacoras/cliente_form.html templates/bitacoras/cliente_list.html
git commit -m "feat(bitacoras): Cliente.alias para agrupar viajes y modulaciones

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0181M3c92rVYQawQxK2fgyFv"
```

---

## Task 2: `TerminalPortuaria.nombre_corto` + `Modulacion.sello_colocado`

**Files:**
- Modify: `modulos/modulacion/models.py`
- Modify: `modulos/modulacion/forms.py`
- Modify: `modulos/modulacion/admin.py`
- Modify: `templates/modulacion/modulacion_detail.html`
- Create: `modulos/modulacion/migrations/0009_terminal_nombre_corto_y_sello.py` (auto)
- Modify: `modulos/modulacion/tests_estados.py` (añadir una clase pequeña de pruebas de estos campos)

**Interfaces:**
- Produces:
  - `TerminalPortuaria.nombre_corto: str` (`CharField(max_length=30, blank=True)`)
  - `TerminalPortuaria.etiqueta -> str` (property) — `self.nombre_corto or self.nombre`
  - `Modulacion.sello_colocado: bool` (`BooleanField(default=False)`)

- [ ] **Step 1: Escribir las pruebas (fallan)**

Añadir a `modulos/modulacion/tests_estados.py` (al final):

```python
class CamposReporteTests(TestCase):
    def test_terminal_etiqueta_usa_nombre_corto(self):
        t = TerminalPortuaria(nombre='L.C. Terminal...', nombre_corto='LCTPC')
        self.assertEqual(t.etiqueta, 'LCTPC')

    def test_terminal_etiqueta_cae_al_nombre(self):
        t = TerminalPortuaria(nombre='APM Terminals')
        self.assertEqual(t.etiqueta, 'APM Terminals')

    def test_sello_colocado_default_false(self):
        m = _modulacion()
        self.assertFalse(m.sello_colocado)

    def test_modulacion_form_acepta_sello_colocado(self):
        from modulos.modulacion.forms import ModulacionForm
        self.assertIn('sello_colocado', ModulacionForm.base_fields)
```

- [ ] **Step 2: Correr — falla**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_estados.CamposReporteTests --settings=test_settings -v 2`
Expected: FAIL — `AttributeError: ... 'etiqueta'` / `sello_colocado` no existe.

- [ ] **Step 3: Campos y property en `models.py`**

En `modulos/modulacion/models.py`, `class TerminalPortuaria`, después de `nombre = models.CharField(...)`:

```python
    nombre_corto = models.CharField(
        max_length=30, blank=True, verbose_name="Nombre corto",
        help_text="Etiqueta corta para reportes (ej. LCTPC, HUTCHINSON, APM).",
    )
```

Y después de su `def __str__`:

```python
    @property
    def etiqueta(self):
        return self.nombre_corto or self.nombre
```

En `class Modulacion`, junto a `hora_carga` (después de la línea `hora_carga = models.DateTimeField(...)`):

```python
    sello_colocado = models.BooleanField(
        default=False, verbose_name="Sello colocado",
        help_text="El contenedor sale con sello/candado colocado.",
    )
```

- [ ] **Step 4: Form**

En `modulos/modulacion/forms.py`, `ModulacionForm.Meta.fields`, agregar `'sello_colocado'` al final de la lista:

```python
        fields = [
            'agencia', 'terminal_portuaria', 'tipo_contenedor', 'peso_toneladas',
            'contenedor', 'cliente', 'num_pedimento', 'num_doda', 'observaciones',
            'sello_colocado',
        ]
```

Y en `widgets`:

```python
            'sello_colocado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
```

- [ ] **Step 5: Admin**

En `modulos/modulacion/admin.py`:

`TerminalPortuariaAdmin`:
```python
    list_display = [
        'nombre', 'nombre_corto', 'activo', 'requiere_datos_extra',
        'requiere_carril', 'requiere_hora_ingreso', 'requiere_hora_carga', 'created_at',
    ]
    list_editable = ['nombre_corto']
```

`ModulacionAdmin`: agregar `'sello_colocado'` a `list_display` (después de `'tipo_cita'`) y a `list_filter`.

- [ ] **Step 6: Detalle**

En `templates/modulacion/modulacion_detail.html`, dentro del `<div class="px-6 py-5 grid grid-cols-2 gap-4 text-sm">` (rejilla de datos), agregar una celda:

```html
            <div><span class="text-gray-500">Sello:</span> <span class="font-medium">{% if modulacion.sello_colocado %}Sí{% else %}No{% endif %}</span></div>
```

- [ ] **Step 7: Migración**

```bash
.venvKasu/bin/python manage.py makemigrations modulacion --name terminal_nombre_corto_y_sello
.venvKasu/bin/python manage.py migrate --settings=test_settings
```

Expected: `0009_terminal_nombre_corto_y_sello.py` con dos `AddField` (`TerminalPortuaria.nombre_corto`, `Modulacion.sello_colocado`); `migrate` sin errores.

- [ ] **Step 8: Correr — verde**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_estados --settings=test_settings -v 2`
Expected: PASS.

- [ ] **Step 9: Regresión del módulo**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion --settings=test_settings`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add modulos/modulacion/models.py modulos/modulacion/forms.py modulos/modulacion/admin.py modulos/modulacion/migrations/0009_terminal_nombre_corto_y_sello.py templates/modulacion/modulacion_detail.html modulos/modulacion/tests_estados.py
git commit -m "feat(modulacion): TerminalPortuaria.nombre_corto y Modulacion.sello_colocado

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0181M3c92rVYQawQxK2fgyFv"
```

---

## Task 3: Builder puro `construir_programa_despacho` (`reportes.py`)

**Files:**
- Create: `modulos/modulacion/reportes.py`
- Create: `modulos/modulacion/tests_reporte.py`

**Interfaces:**
- Consumes: `Modulacion`, `Cliente.etiqueta` (Task 1), `TerminalPortuaria.etiqueta` + `Modulacion.sello_colocado` (Task 2), `openpyxl`.
- Produces:
  - `construir_programa_despacho(fecha: datetime.date) -> openpyxl.Workbook` — hoja `"Programa de despacho"`, 14 columnas (A–N), 1 fila de encabezado (con `J1:L1` combinado = `"REGISTRO"`), una fila-encabezado combinada `"{etiqueta} — N maniobra(s)"` antes de cada bloque de alias, y una fila por modulación de `fecha_modulacion_aduana == fecha`, ordenadas por `(etiqueta_cliente.casefold(), terminal.etiqueta.casefold(), hora_registro)`.
  - Helpers de módulo: `_fecha_es(d)`, `_hora_es(dt)`.

- [ ] **Step 1: Escribir `tests_reporte.py` (falla)**

Crear `modulos/modulacion/tests_reporte.py`:

```python
import datetime
from decimal import Decimal
from io import BytesIO

import openpyxl
from django.test import TestCase
from django.utils import timezone

from modulos.bitacoras.models import Cliente
from modulos.modulacion.models import Agencia, Modulacion, TerminalPortuaria
from modulos.modulacion.reportes import construir_programa_despacho
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad

FECHA = datetime.date(2026, 8, 28)


def _aware(y, mo, d, h, mi):
    return timezone.make_aware(datetime.datetime(y, mo, d, h, mi))


def _mod(**kw):
    kw.setdefault('agencia', Agencia.objects.get_or_create(nombre='LOGINCO')[0])
    kw.setdefault(
        'terminal_portuaria',
        TerminalPortuaria.objects.get_or_create(
            nombre='L.C. Terminal', defaults={'nombre_corto': 'LCTPC'})[0],
    )
    kw.setdefault('tipo_contenedor', '40HC')
    kw.setdefault('peso_toneladas', Decimal('9.82'))
    kw.setdefault('contenedor', 'TLLU7742369')
    kw.setdefault('fecha_modulacion_aduana', FECHA)
    return Modulacion.objects.create(**kw)


def _rows(ws):
    return list(ws.iter_rows(values_only=True))


class ConstruirProgramaDespachoTests(TestCase):
    def test_encabezados_y_registro_combinado(self):
        wb = construir_programa_despacho(FECHA)
        ws = wb.active
        self.assertEqual(ws.title, 'Programa de despacho')
        fila1 = _rows(ws)[0]
        self.assertEqual(fila1[0], 'FECHA DE DESPACHO')
        self.assertEqual(fila1[6], 'OPERADOR')
        self.assertEqual(fila1[7], 'CLIENTE')
        self.assertEqual(fila1[12], 'SELLO')
        self.assertEqual(fila1[13], 'Nº DE MANIOBRA')
        # J1:L1 combinado = "REGISTRO"
        self.assertEqual(ws['J1'].value, 'REGISTRO')

    def test_fila_de_datos_mapea_los_campos(self):
        cli = Cliente.objects.create(nombre='Transportes Moya', alias='MOY')
        op = Operador.objects.create(nombre='Jose Alberto Garcia', tipo='LOCAL', activo=True)
        uni = Unidad.objects.create(
            numero_economico='LE08', placa='ND0814D', tipo='LOCAL', activa=True,
            año=2020, capacidad_combustible=Decimal('300'),
            rendimiento_esperado=Decimal('2.5'),
        )
        _mod(cliente=cli, operador=op, unidad=uni, carril='5C', sello_colocado=False,
             hora_registro=_aware(2026, 8, 28, 9, 30),
             hora_ingreso=_aware(2026, 8, 28, 11, 0),
             hora_carga=_aware(2026, 8, 28, 12, 30))
        ws = construir_programa_despacho(FECHA).active
        datos = [r for r in _rows(ws) if r[5] == 'TLLU7742369'][0]
        self.assertEqual(datos[0], '28-ago-26')
        self.assertEqual(datos[1], 'LCTPC')
        self.assertEqual(datos[2], 'LOGINCO')
        self.assertEqual(datos[3], '40')
        self.assertEqual(datos[4], 9.82)
        self.assertIn('Jose Alberto Garcia', datos[6])
        self.assertIn('ECO LE08 PLACAS ND0814D', datos[6])
        self.assertEqual(datos[7], 'MOY')
        self.assertEqual(datos[8], '5C')
        self.assertEqual(datos[12], 'NO')
        self.assertEqual(datos[13], 1)

    def test_tres_horas_llevan_fondo(self):
        _mod(hora_registro=_aware(2026, 8, 28, 9, 30),
             hora_ingreso=_aware(2026, 8, 28, 11, 0),
             hora_carga=_aware(2026, 8, 28, 12, 30))
        ws = construir_programa_despacho(FECHA).active
        fila = [i for i, r in enumerate(_rows(ws), start=1) if r[5] == 'TLLU7742369'][0]
        self.assertIn('9:30 a. m.', ws.cell(row=fila, column=10).value)
        self.assertIn('11:00 a. m.', ws.cell(row=fila, column=11).value)
        self.assertIn('12:30 p. m.', ws.cell(row=fila, column=12).value)
        self.assertEqual(ws.cell(row=fila, column=10).fill.fill_type, 'solid')
        self.assertEqual(ws.cell(row=fila, column=12).fill.fill_type, 'solid')
        # (HOY) porque la fecha de la hora == fecha del reporte
        self.assertIn('(HOY)', ws.cell(row=fila, column=10).value)

    def test_una_sola_hora_se_combina_sin_fondo(self):
        _mod(hora_ingreso=_aware(2026, 8, 28, 2, 0))
        ws = construir_programa_despacho(FECHA).active
        fila = [i for i, r in enumerate(_rows(ws), start=1) if r[5] == 'TLLU7742369'][0]
        self.assertIn('2:00 a. m.', ws.cell(row=fila, column=10).value)
        self.assertIn(ws.cell(row=fila, column=10).fill.fill_type, (None, 'none'))

    def test_sin_horas_dice_cita_pendiente(self):
        _mod()
        ws = construir_programa_despacho(FECHA).active
        fila = [i for i, r in enumerate(_rows(ws), start=1) if r[5] == 'TLLU7742369'][0]
        self.assertEqual(ws.cell(row=fila, column=10).value, 'CITA PENDIENTE')

    def test_agrupa_por_alias_con_fila_encabezado(self):
        moy = Cliente.objects.create(nombre='Moya', alias='MOY')
        nol = Cliente.objects.create(nombre='Nolasco SA')  # sin alias
        _mod(cliente=moy, contenedor='AAAU1111111')
        _mod(cliente=moy, contenedor='AAAU2222222')
        _mod(cliente=nol, contenedor='BBBU3333333')
        ws = construir_programa_despacho(FECHA).active
        filas = _rows(ws)
        # una fila-encabezado combinada por grupo, con el conteo
        encabezados_grupo = [r[0] for r in filas if r[0] and 'maniobra(s)' in str(r[0])]
        self.assertIn('MOY — 2 maniobra(s)', encabezados_grupo)
        self.assertIn('Nolasco SA — 1 maniobra(s)', encabezados_grupo)
        # Nº de maniobra corre 1..3 y NO cuenta las filas-encabezado
        nums = [r[13] for r in filas if r[5] in ('AAAU1111111', 'AAAU2222222', 'BBBU3333333')]
        self.assertEqual(sorted(nums), [1, 2, 3])

    def test_sin_operador_ni_unidad_no_revienta(self):
        _mod()  # sin operador ni unidad
        ws = construir_programa_despacho(FECHA).active
        datos = [r for r in _rows(ws) if r[5] == 'TLLU7742369'][0]
        self.assertEqual(datos[6], '')

    def test_peso_es_numero(self):
        _mod(peso_toneladas=Decimal('10.37'))
        ws = construir_programa_despacho(FECHA).active
        fila = [i for i, r in enumerate(_rows(ws), start=1) if r[5] == 'TLLU7742369'][0]
        c = ws.cell(row=fila, column=5)
        self.assertEqual(c.value, 10.37)
        self.assertEqual(c.number_format, '0.00')
```

> Nota: si `Unidad` / `Operador` exigen más campos obligatorios de los usados aquí, ajusta con el mínimo que pida el modelo (ver `modulos/unidades/models.py`, `modulos/operadores/models.py`) y anótalo.

- [ ] **Step 2: Correr — falla**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_reporte --settings=test_settings -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'modulos.modulacion.reportes'`.

- [ ] **Step 3: Implementar `reportes.py`**

Crear `modulos/modulacion/reportes.py`:

```python
"""
Reporte "Programa de despacho": un .xlsx con las modulaciones de una fecha,
agrupadas y ordenadas por el alias del cliente, con el formato de la hoja de
control de la terminal.

Módulo puro: construye el Workbook; no toca request/response.
"""
import datetime
from itertools import groupby

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from django.utils import timezone

from .models import Modulacion

_MESES_ES = {
    1: 'ene', 2: 'feb', 3: 'mar', 4: 'abr', 5: 'may', 6: 'jun',
    7: 'jul', 8: 'ago', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dic',
}

ENCABEZADOS = [
    'FECHA DE DESPACHO', 'TERMINAL DE DESPACHO', 'AGENCIA', 'TIPO', 'PESO',
    'CONTENEDOR', 'OPERADOR', 'CLIENTE', 'CARRIL',
    'REGISTRO', '', '',
    'SELLO', 'Nº DE MANIOBRA',
]
_ANCHOS = [12, 16, 10, 6, 8, 16, 34, 12, 8, 14, 14, 14, 7, 12]

_FILL_HEADER = PatternFill('solid', fgColor='D9D9D9')
_FILL_MORADO = PatternFill('solid', fgColor='E4DFEC')
_FILL_GRUPO = PatternFill('solid', fgColor='F2F2F2')
_FILL_REG = {
    10: PatternFill('solid', fgColor='C6EFCE'),   # J verde
    11: PatternFill('solid', fgColor='E4DFEC'),   # K morado
    12: PatternFill('solid', fgColor='DDEBF7'),   # L azul
}
_THIN = Side(border_style='thin', color='BFBFBF')
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTRO = Alignment(horizontal='center', vertical='center')
_CENTRO_WRAP = Alignment(horizontal='center', vertical='center', wrap_text=True)
_WRAP = Alignment(wrap_text=True, vertical='center')


def _fecha_es(d):
    return f'{d.day:02d}-{_MESES_ES[d.month]}-{d:%y}'


def _hora_es(dt):
    h = dt.hour % 12 or 12
    sufijo = 'a. m.' if dt.hour < 12 else 'p. m.'
    return f'{h}:{dt.minute:02d} {sufijo}'


def _texto_hora(dt, fecha_reporte):
    if dt is None:
        return ''
    local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    txt = _hora_es(local)
    if local.date() == fecha_reporte:
        txt += ' (HOY)'
    return txt


def _linea_unidad(unidad):
    if unidad is None:
        return ''
    return f'ECO {unidad.numero_economico} PLACAS {unidad.placa}'


def _tipo(m):
    digitos = ''.join(c for c in (m.tipo_contenedor or '') if c.isdigit())
    return digitos or (m.tipo_contenedor or '')


def _etiqueta_grupo(m):
    return m.cliente.etiqueta if m.cliente_id else '(sin cliente)'


def _clave_orden(m):
    term = m.terminal_portuaria.etiqueta if m.terminal_portuaria_id else ''
    return (
        _etiqueta_grupo(m).casefold(),
        term.casefold(),
        m.hora_registro is None,
        m.hora_registro or datetime.datetime.min,
    )


def construir_programa_despacho(fecha):
    modulaciones = sorted(
        Modulacion.objects
        .filter(fecha_modulacion_aduana=fecha)
        .select_related('cliente', 'operador', 'unidad', 'agencia', 'terminal_portuaria'),
        key=_clave_orden,
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Programa de despacho'

    for col, texto in enumerate(ENCABEZADOS, start=1):
        c = ws.cell(row=1, column=col, value=texto)
        c.font = Font(bold=True)
        c.fill = _FILL_HEADER
        c.border = _BORDER
        c.alignment = _CENTRO_WRAP
    ws.merge_cells('J1:L1')
    ws['J1'].value = 'REGISTRO'
    ws['G1'].fill = _FILL_MORADO
    ws['H1'].fill = _FILL_MORADO
    for i, ancho in enumerate(_ANCHOS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.freeze_panes = 'A2'

    fila = 2
    maniobra = 0
    for etiqueta, grupo in groupby(modulaciones, key=_etiqueta_grupo):
        grupo = list(grupo)
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=14)
        gc = ws.cell(row=fila, column=1,
                     value=f'{etiqueta} — {len(grupo)} maniobra(s)')
        gc.font = Font(bold=True)
        gc.fill = _FILL_GRUPO
        fila += 1

        for m in grupo:
            maniobra += 1
            horas = [m.hora_registro, m.hora_ingreso, m.hora_carga]
            presentes = [h for h in horas if h is not None]
            operador_txt = (
                f'{m.operador.nombre}\n{_linea_unidad(m.unidad)}'.rstrip()
                if m.operador_id else _linea_unidad(m.unidad)
            )
            valores = [
                _fecha_es(fecha),
                m.terminal_portuaria.etiqueta if m.terminal_portuaria_id else '',
                m.agencia.nombre if m.agencia_id else '',
                _tipo(m),
                float(m.peso_toneladas) if m.peso_toneladas is not None else None,
                m.contenedor,
                operador_txt,
                m.cliente.etiqueta if m.cliente_id else '—',
                m.carril or 'NA',
                None, None, None,
                'SÍ' if m.sello_colocado else 'NO',
                maniobra,
            ]
            for col, v in enumerate(valores, start=1):
                c = ws.cell(row=fila, column=col, value=v)
                c.border = _BORDER
            ws.cell(row=fila, column=5).number_format = '0.00'
            ws.cell(row=fila, column=7).alignment = _WRAP
            ws.cell(row=fila, column=8).font = Font(bold=True)
            ws.row_dimensions[fila].height = 30

            if len(presentes) >= 2:
                for col, h in ((10, horas[0]), (11, horas[1]), (12, horas[2])):
                    c = ws.cell(row=fila, column=col, value=_texto_hora(h, fecha))
                    c.border = _BORDER
                    c.alignment = _CENTRO
                    if h is not None:
                        c.fill = _FILL_REG[col]
            else:
                ws.merge_cells(start_row=fila, start_column=10, end_row=fila, end_column=12)
                texto = _texto_hora(presentes[0], fecha) if presentes else 'CITA PENDIENTE'
                c = ws.cell(row=fila, column=10, value=texto)
                c.alignment = _CENTRO
                for col in (10, 11, 12):
                    ws.cell(row=fila, column=col).border = _BORDER
            fila += 1

    return wb
```

- [ ] **Step 4: Correr — verde**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_reporte --settings=test_settings -v 2`
Expected: PASS (8 tests).

- [ ] **Step 5: Regresión del módulo**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion --settings=test_settings`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modulos/modulacion/reportes.py modulos/modulacion/tests_reporte.py
git commit -m "feat(modulacion): builder del reporte Programa de despacho (xlsx)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0181M3c92rVYQawQxK2fgyFv"
```

---

## Task 4: Vista de descarga + template + enlace en el dashboard

**Files:**
- Modify: `modulos/modulacion/views.py`
- Modify: `modulos/modulacion/urls.py`
- Create: `templates/modulacion/reporte_despacho.html`
- Modify: `templates/modulacion/dashboard.html`
- Modify: `modulos/modulacion/tests_reporte.py`

**Interfaces:**
- Consumes: `construir_programa_despacho` (Task 3).
- Produces:
  - URL `modulacion:reporte_despacho` (`reporte-despacho/`) → `ReporteProgramaDespachoView(LoginRequiredMixin, TemplateView)`.
  - URL `modulacion:reporte_despacho_xlsx` (`reporte-despacho/xlsx/`) → `descargar_programa_despacho` (`@login_required`); `?fecha=YYYY-MM-DD` (default hoy si falta/invalida); responde el `.xlsx` como `attachment`.

- [ ] **Step 1: Tests en `tests_reporte.py` (fallan)**

Añadir a `modulos/modulacion/tests_reporte.py`:

```python
from django.contrib.auth import get_user_model
from django.urls import reverse


class ReporteDespachoViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')

    def test_form_requiere_login(self):
        resp = self.client.get(reverse('modulacion:reporte_despacho'))
        self.assertEqual(resp.status_code, 302)

    def test_form_muestra_input_de_fecha_con_hoy(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('modulacion:reporte_despacho'))
        self.assertEqual(resp.status_code, 200)
        hoy = timezone.localdate().isoformat()
        self.assertContains(resp, 'type="date"')
        self.assertContains(resp, f'value="{hoy}"')

    def test_descarga_xlsx(self):
        self.client.force_login(self.user)
        _mod()
        resp = self.client.get(
            reverse('modulacion:reporte_despacho_xlsx'), {'fecha': '2026-08-28'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment; filename="programa_despacho_2026-08-28.xlsx"',
                      resp['Content-Disposition'])
        wb = openpyxl.load_workbook(BytesIO(resp.getvalue()))
        self.assertEqual(wb.active['A1'].value, 'FECHA DE DESPACHO')

    def test_descarga_sin_fecha_usa_hoy(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('modulacion:reporte_despacho_xlsx'))
        self.assertEqual(resp.status_code, 200)
        hoy = timezone.localdate().isoformat()
        self.assertIn(f'programa_despacho_{hoy}.xlsx', resp['Content-Disposition'])

    def test_descarga_fecha_invalida_usa_hoy(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse('modulacion:reporte_despacho_xlsx'), {'fecha': 'no-es-fecha'})
        self.assertEqual(resp.status_code, 200)
```

- [ ] **Step 2: Correr — falla**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_reporte.ReporteDespachoViewTests --settings=test_settings -v 2`
Expected: FAIL — `NoReverseMatch: 'reporte_despacho'`.

- [ ] **Step 3: Vistas**

En `modulos/modulacion/views.py`:

Asegura estos imports (agrega lo que falte):
```python
import datetime

from django.http import HttpResponse
from django.views.generic import TemplateView   # si no está ya en el import de django.views.generic

from .reportes import construir_programa_despacho
```

Al final del archivo:
```python
class ReporteProgramaDespachoView(LoginRequiredMixin, TemplateView):
    """Form con selector de fecha para descargar el Programa de despacho (.xlsx)."""
    template_name = 'modulacion/reporte_despacho.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['fecha'] = timezone.localdate().isoformat()
        return ctx


def _parse_fecha(texto):
    try:
        return datetime.date.fromisoformat(texto or '')
    except (TypeError, ValueError):
        return None


@login_required
def descargar_programa_despacho(request):
    fecha = _parse_fecha(request.GET.get('fecha')) or timezone.localdate()
    wb = construir_programa_despacho(fecha)
    resp = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    resp['Content-Disposition'] = (
        f'attachment; filename="programa_despacho_{fecha.isoformat()}.xlsx"'
    )
    wb.save(resp)
    return resp
```

- [ ] **Step 4: URLs**

En `modulos/modulacion/urls.py`, dentro de `urlpatterns`, antes del bloque `# API de recepción (HAL9MIL)`:
```python
    # Reporte "Programa de despacho" (.xlsx)
    path('reporte-despacho/', views.ReporteProgramaDespachoView.as_view(), name='reporte_despacho'),
    path('reporte-despacho/xlsx/', views.descargar_programa_despacho, name='reporte_despacho_xlsx'),
```

- [ ] **Step 5: Template**

Crear `templates/modulacion/reporte_despacho.html`:
```html
{% extends "base.html" %}

{% block title %}Programa de despacho{% endblock %}

{% block content %}
<div class="max-w-lg mx-auto py-6">
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div class="px-6 py-5 border-b border-gray-100">
            <h1 class="text-lg font-bold text-gray-900">Programa de despacho</h1>
            <p class="text-sm text-gray-500 mt-0.5">
                Descarga el Excel con las modulaciones de una fecha, agrupadas por cliente.
            </p>
        </div>
        <form method="get" action="{% url 'modulacion:reporte_despacho_xlsx' %}" class="px-6 py-5 space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Fecha de despacho</label>
                <input type="date" name="fecha" value="{{ fecha }}"
                       class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
            </div>
            <div class="flex justify-end pt-2 border-t border-gray-100">
                <button type="submit"
                        class="px-4 py-2 text-sm font-medium text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 transition min-h-[44px]">
                    Descargar Excel
                </button>
            </div>
        </form>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Enlace en el dashboard**

En `templates/modulacion/dashboard.html`, dentro de `<div class="dash-page-actions">`, después del enlace "Atención a Clientes" y antes de "Ver lista":
```html
            <a href="{% url 'modulacion:reporte_despacho' %}"
               class="inline-flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg font-semibold text-sm transition min-h-[44px]">
                Programa de despacho
            </a>
```

- [ ] **Step 7: Correr — verde**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_reporte --settings=test_settings -v 2`
Expected: PASS.

- [ ] **Step 8: Regresión + checks**

```bash
.venvKasu/bin/python manage.py test modulos.modulacion modulos.bitacoras --settings=test_settings
.venvKasu/bin/python manage.py check
.venvKasu/bin/python manage.py makemigrations --check --dry-run
```
Expected: suites en verde; `check` sin errores; sin migraciones pendientes de `modulacion` ni `bitacoras` (puede seguir apareciendo el drift ajeno y preexistente de `taller`).

- [ ] **Step 9: Commit**

```bash
git add modulos/modulacion/views.py modulos/modulacion/urls.py templates/modulacion/reporte_despacho.html templates/modulacion/dashboard.html modulos/modulacion/tests_reporte.py
git commit -m "feat(modulacion): vista de descarga del Programa de despacho

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0181M3c92rVYQawQxK2fgyFv"
```

---

## Verificación final

- [ ] `.venvKasu/bin/python manage.py test modulos.modulacion modulos.bitacoras --settings=test_settings` → verde.
- [ ] `.venvKasu/bin/python manage.py check` → sin errores.
- [ ] `.venvKasu/bin/python manage.py makemigrations --check --dry-run` → sin cambios de `modulacion` / `bitacoras`.
- [ ] `git log --oneline` → 4 commits, uno por tarea.
- [ ] Smoke manual: en `/modulacion/` aparece "Programa de despacho"; el form descarga un `.xlsx` que abre en Excel con encabezados y una fila-encabezado por alias.

## Notas / fuera de alcance

- DODA y columnas A–E de la captura original: fuera.
- Tabla en pantalla del reporte: fuera (solo `.xlsx`).
- Tags múltiples por cliente: fuera (solo `alias`).
- Rango de fechas u otros filtros: fuera (solo una fecha).
- Colores/tipografías pixel-perfect de la captura: se busca parecido razonable.
- Envío del reporte por correo vía `modulos/reportes/`: fuera.
