# Asignación de unidad y operador en Modulación + reporte semanal de contenedores por operador

Fecha: 2026-08-27
Módulos afectados: `modulos/modulacion`, `modulos/reportes`

## Contexto

Hoy en el módulo de **modulación** el `operador` y la `unidad` no se
guardan en `Modulacion`; sólo se capturan al momento de "Enviar a Bitácora"
(`PromoverBitacoraForm` → `BitacoraViaje`). El vínculo operador↔unidad ya
existe en `Operador.unidad_asignada`.

Se necesita:

1. Poder asignar una **unidad** y un **operador local** directamente a una
   modulación, mediante una acción dedicada en la página de detalle.
2. Al elegir una unidad que ya tiene un operador ligado
   (`Operador.unidad_asignada`), auto-llenar ese operador, dejando la opción
   de **reasignar solamente el operador** a mano.
3. Un reporte de **cuántos contenedores extrae por semana cada operador**,
   dentro del módulo `reportes` (programable + vista en pantalla).

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Momento de asignación | Acción aparte en el detalle (`/modulacion/<pk>/asignar/`). La modulación se crea sin operador/unidad. |
| Relación con "Enviar a Bitácora" | Flujos **independientes**. `PromoverBitacoraForm` / `EnviarABitacoraView` no se tocan. |
| Auto-llenado del operador | Auto-llena al cambiar la unidad, pero **editable** (permite reasignar sólo el operador). |
| Ubicación del reporte | Módulo `reportes`: `ConfiguracionReporte` programable **+** vista en pantalla bajo demanda. |
| Base del conteo del reporte | `fecha_retiro` de la modulación, dentro de la semana; sólo modulaciones con `operador` asignado. |
| Fuente del operador del reporte | **Sólo** el campo nuevo `Modulacion.operador`. No hay fallback al operador del `BitacoraViaje`. |

## Supuesto explícito

El reporte cuenta **sólo** modulaciones con `Modulacion.operador` asignado
vía la nueva acción **y** con `fecha_retiro` dentro del rango. Los viajes
enviados a bitácora sin haber asignado operador en la modulación **no**
aparecen. El equipo debe usar la acción "Asignar unidad y operador" para
que el contenedor cuente en el reporte.

---

## Parte A — Asignar unidad y operador local a una Modulación

### A1. Modelo `Modulacion` (`modulos/modulacion/models.py`)

Nuevos campos:

| Campo | Tipo | Notas |
|---|---|---|
| `unidad` | `FK → unidades.Unidad`, `on_delete=SET_NULL`, `null=True, blank=True`, `related_name='modulaciones'`, `verbose_name="Unidad asignada"` | Unidad local asignada |
| `operador` | `FK → operadores.Operador`, `on_delete=SET_NULL`, `null=True, blank=True`, `related_name='modulaciones'`, `verbose_name="Operador asignado"` | Operador local asignado |
| `fecha_asignacion` | `DateTimeField`, `null=True, blank=True`, `verbose_name="Fecha de asignación"` | Se sella la primera vez que se asigna |

Migración: `0003_modulacion_asignacion.py`. Los tres campos son opcionales a
nivel BD (los registros de HAL9MIL nacen sin operador).

### A2. Formulario (`modulos/modulacion/forms.py`)

`AsignarUnidadOperadorForm(forms.ModelForm)`:

- `Meta.model = Modulacion`, `Meta.fields = ['unidad', 'operador']`
- `unidad.queryset = Unidad.objects.filter(tipo='LOCAL', activa=True)` — **requerido**
- `operador.queryset = Operador.objects.filter(tipo='LOCAL', activo=True)` — **requerido**
- Widgets `Select` con `class="form-control"` (patrón del módulo).

### A3. Auto-llenado editable del operador (JS en el template)

- La vista pasa al contexto `unidad_operador_map`: JSON
  `{ "<unidad_id>": <operador_id> }`, construido con
  `Operador.objects.filter(tipo='LOCAL', activo=True, unidad_asignada__isnull=False).values_list('unidad_asignada_id', 'id')`.
- `<script>` inline: al cambiar `#id_unidad`, si el mapa tiene entrada para
  esa unidad, asigna ese operador en `#id_operador` (sobrescribe). El usuario
  puede luego elegir otro operador local a mano → cubre "reasignar solamente
  el operador".
- Si la unidad no tiene operador ligado, el select de operador queda para
  elección manual.

### A4. Vista + URL (`modulos/modulacion/views.py`, `urls.py`)

- `AsignarUnidadOperadorView(LoginRequiredMixin, UpdateView)`
  - `model = Modulacion`, `form_class = AsignarUnidadOperadorForm`
  - `template_name = 'modulacion/asignar_unidad_operador.html'`
  - `form_valid`: si `self.object.fecha_asignacion` es `None`, la sella con
    `timezone.now()`; guarda; `messages.success("Unidad y operador asignados.")`;
    redirige a `modulacion:detail`.
  - `get_context_data`: agrega `unidad_operador_map`.
- URL: `path('<int:pk>/asignar/', views.AsignarUnidadOperadorView.as_view(), name='asignar')`

**Reasignar** usa la misma vista/formulario (`UpdateView` precarga `unidad` y
`operador` actuales): se cambia sólo el operador y se guarda.

### A5. Templates

**`templates/modulacion/modulacion_detail.html`:**
- En la grilla de datos, dos filas nuevas: "Unidad asignada"
  (`{{ modulacion.unidad.numero_economico|default:"—" }}`) y "Operador asignado"
  (`{{ modulacion.operador.nombre|default:"—" }}`).
- En la barra de acciones, botón nuevo:
  - Sin asignación → "Asignar unidad y operador"
  - Con asignación → "Reasignar operador"
  - Enlaza a `modulacion:asignar`.

**`templates/modulacion/asignar_unidad_operador.html`** (nuevo): extiende
`base.html`, breadcrumb como los demás, tarjeta blanca con los dos selects,
`<script>` inline del auto-llenado, botones Guardar / Cancelar (vuelve al
detalle).

### A6. Admin (`modulos/modulacion/admin.py`)

- `list_display` += `operador`, `unidad`
- `list_filter` += `operador`
- `autocomplete_fields = ['operador', 'unidad']` (los admins de Operador y
  Unidad ya tienen `search_fields`).
- `list_select_related` / `get_queryset` → agregar `operador`, `unidad`.

### A7. "Enviar a Bitácora" — sin cambios

`PromoverBitacoraForm` y `EnviarABitacoraView` quedan intactos. Flujos
independientes.

### A8. Pruebas (`modulos/modulacion/tests.py`)

- Asignar unidad+operador sella `fecha_asignacion` una sola vez (reasignar no
  la cambia).
- `unidad_operador_map` contiene sólo operadores LOCAL activos con
  `unidad_asignada`.
- Reasignar operador conserva la `unidad`.
- Los querysets del form filtran por `tipo='LOCAL'` y `activa`/`activo`.

---

## Parte B — Reporte "Contenedores extraídos por operador" (módulo `reportes`)

### B1. Choices (`modulos/reportes/models.py`)

- `MODULO_CHOICES` += `('MODULACION', 'Modulación')`
- `TIPO_CHOICES` += `('MODULACION_CONTENEDORES_OPERADOR', 'Modulación — Contenedores extraídos por operador')`
- Migración por el cambio de choices.

### B2. Generador (`modulos/reportes/generadores/modulacion.py`, nuevo)

`generar_contenedores_por_operador(periodo_inicio, periodo_fin) -> dict`:

- Query base:
  `Modulacion.objects.filter(fecha_retiro__date__gte=periodo_inicio, fecha_retiro__date__lte=periodo_fin, operador__isnull=False).select_related('operador')`
- Agrupa en Python por **operador** y por **semana ISO** (de
  `timezone.localtime(fecha_retiro)` → `isocalendar()`), etiqueta tipo
  `"2026-W35 (25 ago – 31 ago)"`.
- Devuelve el dict estándar del sistema:
  - `tipo`, `titulo`, `periodo_inicio`, `periodo_fin`, `generado_en`
  - `resumen`: `total_contenedores`, `operadores_activos`, `operador_top`,
    `contenedores_operador_top`, `promedio_por_operador`
  - `filas`: una por (operador × semana) → `{operador, semana, contenedores}`
  - `tablas`: hoja `"Por operador y semana"` (= `filas`) y hoja
    `"Totales por operador"` (operador → total del período), para el Excel.
- `GENERADORES = {'MODULACION_CONTENEDORES_OPERADOR': generar_contenedores_por_operador}`

### B3. Wiring

- `modulos/reportes/management/commands/generar_reportes.py`:
  `from modulos.reportes.generadores import modulacion as gen_modulacion` y
  `**gen_modulacion.GENERADORES` en el dict `GENERADORES`.
- `modulos/reportes/generadores/narrativa.py`: agregar a `_NOMBRES_REPORTE`
  `'MODULACION_CONTENEDORES_OPERADOR': 'Modulación — Contenedores por Operador'`
  (usa el prompt genérico; sin función de prompt dedicada).

Con esto queda como `ConfiguracionReporte` programable SEMANAL: correo +
Excel + WhatsApp + narrativa IA + historial, igual que los demás.

### B4. Vista en pantalla (`modulos/reportes/views.py`, `urls.py`)

- `ContenedoresPorOperadorView(LoginRequiredMixin, TemplateView)`
  - `template_name = 'reportes/contenedores_por_operador.html'`
  - Params GET `desde` / `hasta` (`YYYY-MM-DD`). Default: últimos 7 días
    terminando ayer (misma convención SEMANAL del command). Inválidos →
    default + `messages.warning`.
  - Llama al **mismo** `generar_contenedores_por_operador(desde, hasta)` y
    pasa `datos` al contexto (sin duplicar lógica).
  - Render: tarjetas del `resumen` + tabla operador × semana (`datos.filas`) +
    tabla totales por operador, con estilo Tailwind del módulo.
- URL: `path('modulacion/contenedores-por-operador/', views.ContenedoresPorOperadorView.as_view(), name='contenedores_por_operador')`
- Acceso: enlace "Contenedores por operador" en la barra superior de
  `reportes/historial.html` (y en el sidebar de `base.html` si el módulo
  reportes ya figura ahí — confirmar al implementar).

### B5. Pruebas (`modulos/reportes/tests.py`)

- El generador cuenta por `fecha_retiro` dentro del rango, excluye
  `operador__isnull=True`, agrupa por semana ISO correctamente.
- `resumen` con totales y `operador_top` correctos.
- La vista responde 200 con rango default y con rango explícito; rango
  inválido → cae a default.

---

## Orden de implementación sugerido

1. Parte A: modelo + migración → form → vista/URL → templates → admin → tests.
2. Parte B: choices + migración → generador → wiring (command + narrativa) →
   vista en pantalla + URL + template → tests.
3. Correr `python manage.py test modulos.modulacion modulos.reportes`.
