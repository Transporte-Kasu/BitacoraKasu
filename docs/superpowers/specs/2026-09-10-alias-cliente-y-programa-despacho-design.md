# Alias de Cliente + reporte "Programa de despacho" (.xlsx) — Diseño

**Fecha:** 2026-09-10
**Módulos:** `modulos/bitacoras/` (Cliente), `modulos/modulacion/` (reporte + campos)

## Objetivo

1. Agregar un **alias corto** a `Cliente` (app `bitacoras`) para agrupar tanto
   viajes como modulaciones en reportes.
2. Nueva vista en `modulacion` que **descarga un `.xlsx`** ("Programa de
   despacho") con las modulaciones de una fecha, con el formato de la captura
   que dio el usuario (columnas F–S de esa imagen), usando el alias del cliente
   en la columna Cliente y **agrupando/ordenando por alias**.

Para el reporte hacen falta dos campos nuevos que hoy no existen:
`TerminalPortuaria.nombre_corto` y `Modulacion.sello_colocado`.

---

## Parte 1 — `Cliente.alias`

### Cambios

- `modulos/bitacoras/models.py`, `class Cliente`:
  ```python
  alias = models.CharField(
      max_length=20, blank=True, verbose_name="Alias",
      help_text="Código corto para agrupar viajes y modulaciones en reportes.",
  )
  ```
  Property:
  ```python
  @property
  def etiqueta(self):
      """Alias corto si hay; si no, el nombre completo."""
      return self.alias or self.nombre
  ```
- `modulos/bitacoras/forms.py`, `ClienteForm.Meta.fields`: agregar `'alias'`
  (después de `'nombre'`).
- Template del form de cliente (`templates/bitacoras/cliente_form.html` o el que
  use `ClienteCreateView`/`ClienteUpdateView`): renderizar el nuevo campo
  (si el template itera `form` genéricamente, no hay cambio).
- `modulos/bitacoras/admin.py`, `ClienteAdmin`: `alias` en `list_display`,
  `list_editable` y `search_fields`.
- Migración `modulos/bitacoras/migrations/0010_cliente_alias.py` (un `AddField`).

### Sin cambios

`BitacoraViaje.cliente` y `Modulacion.cliente` ya son FK a `Cliente`; el alias
está disponible en ambos sin tocar nada más.

---

## Parte 2 — Campos nuevos para el reporte

### `TerminalPortuaria.nombre_corto`

- `modulos/modulacion/models.py`, `class TerminalPortuaria`:
  ```python
  nombre_corto = models.CharField(
      max_length=30, blank=True, verbose_name="Nombre corto",
      help_text="Etiqueta corta para reportes (ej. LCTPC, HUTCHINSON, APM).",
  )
  ```
  Property:
  ```python
  @property
  def etiqueta(self):
      return self.nombre_corto or self.nombre
  ```
- `modulos/modulacion/admin.py`, `TerminalPortuariaAdmin`: `nombre_corto` en
  `list_display` y `list_editable`.

### `Modulacion.sello_colocado`

- `modulos/modulacion/models.py`, `class Modulacion` (junto a `carril` /
  `hora_*`):
  ```python
  sello_colocado = models.BooleanField(
      default=False, verbose_name="Sello colocado",
      help_text="El contenedor sale con sello/candado colocado.",
  )
  ```
- `modulos/modulacion/forms.py`, `ModulacionForm.Meta.fields`: agregar
  `'sello_colocado'`.
- `modulos/modulacion/admin.py`, `ModulacionAdmin`: `sello_colocado` en
  `list_display` y `list_filter`.
- `templates/modulacion/modulacion_detail.html`: mostrarlo en la rejilla de
  datos (`Sello: Sí/No`).

### Migración

`modulos/modulacion/migrations/0009_terminal_nombre_corto_y_sello.py` —
dos `AddField`, sin data migration. (`0008` es la última.)

---

## Parte 3 — Reporte "Programa de despacho" (.xlsx)

### 3.1 Builder puro — `modulos/modulacion/reportes.py` (nuevo)

```python
def construir_programa_despacho(fecha: datetime.date) -> openpyxl.Workbook
```

- **Selección de filas:**
  ```python
  Modulacion.objects
      .filter(fecha_modulacion_aduana=fecha)
      .select_related('cliente', 'operador', 'unidad', 'agencia', 'terminal_portuaria')
  ```
- **Orden (en Python, el volumen diario es de decenas):**
  clave = `(cliente.etiqueta.lower() if cliente else '~~~', terminal.etiqueta.lower(), m.hora_registro is None, m.hora_registro)`.
  (`hora_registro` es `DateTimeField`; el `is None` primero evita comparar
  `datetime` con `None`.) Resultado: cada alias en un bloque contiguo; dentro del
  bloque, por terminal y hora; los sin cliente van al final.
- **Filas del sheet:**
  - Fila 1: encabezados. `REGISTRO` combinado sobre las 3 columnas de hora.
  - Antes de cada bloque de alias: una fila **combinada A–N** con
    `f"{etiqueta} — {n} maniobra(s)"`, negrita, relleno gris claro.
  - Una fila por modulación.
- **Columnas (A–N, 14):**

  | Col | Encabezado | Valor |
  |---|---|---|
  | A | FECHA DE DESPACHO | `fecha` formateada `%d-%b-%y` en español → `28-ago-26` (usar un mapa de meses ES; no depender del locale del SO) |
  | B | TERMINAL DE DESPACHO | `terminal_portuaria.etiqueta` |
  | C | AGENCIA | `agencia.nombre` |
  | D | TIPO | dígitos iniciales de `tipo_contenedor` (`'40HC'` → `'40'`); si no hay dígitos, el valor tal cual |
  | E | PESO | `float(peso_toneladas)`, número, `number_format = '0.00'` |
  | F | CONTENEDOR | `contenedor` |
  | G | OPERADOR | `f"{operador.nombre}\n{linea_unidad}"` en una sola celda, `alignment=wrap_text, vertical='center'`; `linea_unidad = f"ECO {unidad.numero_economico} PLACAS {unidad.placa}"` o `''` si no hay unidad; si no hay operador → `''` |
  | H | CLIENTE | `cliente.etiqueta` o `'—'`; **negrita** |
  | I | CARRIL | `carril` o `'NA'` |
  | J·K·L | (bajo REGISTRO) | `hora_registro` · `hora_ingreso` · `hora_carga` — ver reglas |
  | M | SELLO | `'SÍ'` si `sello_colocado` else `'NO'` |
  | N | Nº DE MANIOBRA | contador corrido 1..N sobre las filas de datos (no cuenta las filas-encabezado de grupo); no se guarda en BD |

- **Reglas sección REGISTRO (J·K·L):**
  - Formato de hora: `%I:%M %p` normalizado a minúsculas con espacios →
    `9:30 a. m.` / `12:30 p. m.` (helper propio; sin ceros a la izquierda en la
    hora).
  - Si el `.date()` de la hora `== fecha` → se le agrega `' (HOY)'`.
  - **≥ 2 de las 3 presentes:** se escriben las 3 celdas (la que falte, vacía).
    Fondos: J verde (`C6EFCE`), K morado (`E4DFEC`), L azul (`DDEBF7`) — tonos
    aproximados a la imagen.
  - **Exactamente 1 presente:** `merge J:L`, centrada, esa hora, **sin fondo**.
  - **Ninguna:** `merge J:L`, `'CITA PENDIENTE'`, centrada, sin fondo.
- **Estilo general:**
  - Fila de encabezado: negrita, `fill` gris, borde; `H1` (CLIENTE) y `G1`
    (OPERADOR) con `fill` morado suave (como la imagen).
  - `ws.freeze_panes = 'A2'`.
  - Anchos de columna fijos (A≈12, B≈16, C≈10, D≈6, E≈8, F≈16, G≈34, H≈12,
    I≈8, J/K/L≈14, M≈7, N≈10).
  - Borde fino en todas las celdas de datos.
  - Altura de las filas de datos suficiente para 2 líneas del operador
    (`row_dimensions[r].height = 30`).
  - Nombre de la hoja: `"Programa de despacho"`.

### 3.2 Vista y URLs — `modulos/modulacion/views.py`, `modulos/modulacion/urls.py`

- `class ReporteProgramaDespachoView(LoginRequiredMixin, TemplateView)`
  - `template_name = 'modulacion/reporte_despacho.html'`
  - contexto: `fecha` (del `?fecha=` o `timezone.localdate()`), como `YYYY-MM-DD`
    para el `value` del input.
- `@login_required def descargar_programa_despacho(request)`
  - `fecha = _parse_fecha(request.GET.get('fecha')) or timezone.localdate()`
    (`_parse_fecha`: `datetime.date.fromisoformat`, `except ValueError → None`).
  - `wb = construir_programa_despacho(fecha)`
  - `resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')`
  - `resp['Content-Disposition'] = f'attachment; filename="programa_despacho_{fecha.isoformat()}.xlsx"'`
  - `wb.save(resp); return resp`
- `urls.py` (antes del bloque `# API de recepción (HAL9MIL)`):
  ```python
  path('reporte-despacho/', views.ReporteProgramaDespachoView.as_view(), name='reporte_despacho'),
  path('reporte-despacho/xlsx/', views.descargar_programa_despacho, name='reporte_despacho_xlsx'),
  ```

### 3.3 Template — `templates/modulacion/reporte_despacho.html` (nuevo)

Extiende `base.html`. Contenido: título "Programa de despacho", un
`<form method="get" action="{% url 'modulacion:reporte_despacho_xlsx' %}">`
con `<input type="date" name="fecha" value="{{ fecha }}">` y un botón
`Descargar Excel`. Sin tabla en pantalla (decisión: solo `.xlsx`).

### 3.4 Enlace en el dashboard

`templates/modulacion/dashboard.html`, dentro de `.dash-page-actions`
(junto a "Atención a Clientes" / "Ver lista"):
```html
<a href="{% url 'modulacion:reporte_despacho' %}"
   class="inline-flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg font-semibold text-sm transition min-h-[44px]">
    Programa de despacho
</a>
```

---

## Estructura de archivos

| Archivo | Acción |
|---|---|
| `modulos/bitacoras/models.py` | Modificar — `Cliente.alias` + `Cliente.etiqueta` |
| `modulos/bitacoras/forms.py` | Modificar — `alias` en `ClienteForm` |
| `modulos/bitacoras/admin.py` | Modificar — `alias` en `ClienteAdmin` |
| `modulos/bitacoras/migrations/0010_cliente_alias.py` | Crear (auto) |
| `templates/bitacoras/cliente_form.html` | Modificar solo si no itera el form genéricamente |
| `modulos/modulacion/models.py` | Modificar — `TerminalPortuaria.nombre_corto` + `etiqueta`; `Modulacion.sello_colocado` |
| `modulos/modulacion/forms.py` | Modificar — `sello_colocado` en `ModulacionForm` |
| `modulos/modulacion/admin.py` | Modificar — `nombre_corto` en `TerminalPortuariaAdmin`; `sello_colocado` en `ModulacionAdmin` |
| `modulos/modulacion/migrations/0009_terminal_nombre_corto_y_sello.py` | Crear (auto) |
| `modulos/modulacion/reportes.py` | Crear — `construir_programa_despacho()` + helpers de formato |
| `modulos/modulacion/views.py` | Modificar — `ReporteProgramaDespachoView`, `descargar_programa_despacho` |
| `modulos/modulacion/urls.py` | Modificar — 2 rutas |
| `templates/modulacion/reporte_despacho.html` | Crear |
| `templates/modulacion/modulacion_detail.html` | Modificar — mostrar `Sello` |
| `templates/modulacion/dashboard.html` | Modificar — enlace |
| `modulos/modulacion/tests_reporte.py` | Crear — pruebas del builder y la vista |
| `modulos/bitacoras/tests*.py` | Modificar/crear — prueba de `Cliente.etiqueta` |

---

## Testing

### Parte 1
- `Cliente(alias='MOY').etiqueta == 'MOY'`; `Cliente(nombre='Nolasco SA').etiqueta == 'Nolasco SA'`.
- `ClienteForm` acepta y guarda `alias`.

### Parte 2
- `TerminalPortuaria(nombre_corto='LCTPC').etiqueta == 'LCTPC'`; fallback a `nombre`.
- `ModulacionForm` acepta `sello_colocado`.
- `sello_colocado` default `False`.

### Parte 3 — `construir_programa_despacho(fecha)`
Con un set fijo de `Modulacion` para una `fecha`:
- La fila 1 tiene los 14 encabezados esperados y `J1` (celda combinada) dice `REGISTRO`.
- Una modulación completa produce una fila con: A `28-ago-26`, B = etiqueta de terminal (`nombre_corto`), G contiene el nombre del operador **y** `ECO <eco> PLACAS <placa>`, H = alias del cliente, I = carril, M = `NO`, N = `1`.
- **3 horas presentes** → celdas J/K/L con las 3 horas formateadas `9:30 a. m.` y con los fills verde/morado/azul.
- **1 hora presente** → `J:L` combinada, centrada, con esa hora, sin fill.
- **0 horas** → `J:L` combinada = `CITA PENDIENTE`.
- Una hora cuyo `.date()` es la `fecha` del reporte lleva ` (HOY)`.
- **Orden por alias:** con clientes `MOY`, `NOLASCO` y uno sin alias (nombre `Zeta`), y varias modulaciones, las filas de datos salen agrupadas `MOY…`, `NOLASCO…`, `Zeta…`; y hay una fila-encabezado combinada `MOY — N maniobra(s)` antes de cada bloque.
- `N` (Nº de maniobra) es 1..total y **no** se incrementa en las filas-encabezado de grupo.
- Modulación sin operador / sin unidad → G no revienta (líneas vacías donde falte).
- `PESO` se escribe como número (`cell.value` es float, `number_format == '0.00'`).

### Parte 3 — vista
- `GET /modulacion/reporte-despacho/` sin login → 302.
- Con login → 200, el HTML trae un `<input type="date">` con `value` = hoy.
- `GET /modulacion/reporte-despacho/xlsx/?fecha=2026-08-28` → 200,
  `Content-Type` de xlsx, `Content-Disposition` con
  `attachment; filename="programa_despacho_2026-08-28.xlsx"`, y el body abre con
  `openpyxl.load_workbook(BytesIO(resp.content))`.
- `?fecha=` ausente o inválida → usa hoy (no 500).

### Regresión
- Suites completas de `modulos.modulacion` y `modulos.bitacoras` en verde.
- `manage.py check` sin errores; `makemigrations --check --dry-run` sin cambios
  pendientes de `modulacion` ni `bitacoras`.

---

## Fuera de alcance

- DODA en el reporte (se deja fuera por ahora).
- Columnas A–E de la captura original (folio, etc.) — el reporte arranca en la
  columna A con "FECHA DE DESPACHO".
- Tabla en pantalla del reporte (solo `.xlsx`).
- Tags múltiples por cliente (solo un `alias`).
- Rango de fechas / otros filtros (solo una fecha).
- Reproducir pixel-perfect los colores/tipografías de la captura (se busca
  parecido razonable).
- Programar el reporte por correo vía `modulos/reportes/` (es descarga manual).
