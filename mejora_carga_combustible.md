# Plan: Flujo Diferenciado de Carga de Combustible por Tipo de Unidad

## Contexto y objetivo

Actualmente el wizard de carga de combustible tiene **6 pasos fijos** que se aplican igual a todas las unidades (FORANEA, LOCAL, ESPERANZA). El objetivo es:

1. **Flujo LOCAL (3 pasos):** Paso 1 → Paso 4 → Paso 6
2. **Flujo FORANEO/ESPERANZA (6 pasos):** Sin cambios, igual que hoy
3. **Futuro (no implementar ahora):** Campo `control_combustible_total` en `Unidad` para forzar el flujo completo en unidades locales marcadas

La detección del flujo ocurre automáticamente en el Paso 1 al seleccionar la unidad.

---

## Pasos del wizard por flujo

| Paso | Descripción | LOCAL | FORANEO / ESPERANZA |
|------|-------------|-------|---------------------|
| 1 | Foto número económico + selección de unidad | ✅ | ✅ |
| 2 | Foto tablero + kilometraje + nivel combustible | ❌ omitir | ✅ |
| 3 | Foto candado anterior + estado candado | ❌ omitir | ✅ |
| 4 | Control de litros cargados (cronómetro + litros) | ✅ | ✅ |
| 5 | Fotos del candado nuevo | ❌ omitir | ✅ |
| 6 | Foto del ticket + notas + finalizar | ✅ | ✅ |

---

## Principios de la implementación

- **Backend (BD):** Los campos omitidos en flujo LOCAL (`foto_tablero`, `foto_candado_anterior`) se hacen `null=True, blank=True` en el modelo para que la BD los acepte vacíos.
- **Frontend FORANEO:** Los templates existentes de pasos 2, 3 y 5 **no se tocan** — siguen con sus campos requeridos exactamente como hoy.
- **Frontend LOCAL:** Se crea un nuevo template exclusivo solo para el paso 4 (`wizard_local_paso4.html`). Los pasos 1 y 6 se adaptan sobre los templates existentes con cambios mínimos.

---

## Análisis de templates: decisión por paso

### Por qué template propio para Paso 4 LOCAL

Revisando `wizard_paso4.html`, tiene dos problemas para el flujo LOCAL:

1. **Resumen engañoso:** muestra `carga.kilometraje_actual` (queda en `0`) y `carga.nivel_combustible_inicial` (queda en `'VACIO'`) — datos que nunca se capturaron y que confundirían al despachador.
2. **Botón "Atrás" hardcodeado:** apunta a `paso=3` (candado anterior), paso que no existe en flujo LOCAL.

**Decisión:** Crear `wizard_local_paso4.html` — copia del paso 4 foráneo pero sin la sección de resumen y con "Atrás" → `paso=1`.

### Por qué adaptar Paso 6 (sin template nuevo)

Revisando `wizard_paso6.html`, la única diferencia para LOCAL es:
- Botón "Atrás" hardcodeado en `paso=5` → debe ir a `paso=4`

El contenido (foto ticket + notas) es idéntico en ambos flujos. Se resuelve pasando `paso_anterior` como variable de contexto desde la vista, sin condicionales en el template.

### Paso 1 — Adaptar existente

Solo se agrega un badge informativo bajo el selector de unidad. Sin cambios estructurales.

### Resumen de decisiones

| Template | Estrategia | Motivo |
|----------|-----------|--------|
| `wizard_paso1.html` | Adaptar existente | Solo se agrega badge + JSON de tipos |
| `wizard_paso2.html` | Solo `paso_visible` | Foraneo no cambia; LOCAL nunca lo ve |
| `wizard_paso3.html` | Solo `paso_visible` | Foraneo no cambia; LOCAL nunca lo ve |
| `wizard_paso4.html` | Adaptar existente (foraneo) | Solo `paso_visible` + `paso_anterior` |
| `wizard_local_paso4.html` | **Template nuevo** | Sin resumen engañoso; "Atrás" → paso 1 |
| `wizard_paso5.html` | Solo `paso_visible` | Foraneo no cambia; LOCAL nunca lo ve |
| `wizard_paso6.html` | Adaptar existente | Solo `paso_visible` + `paso_anterior` por contexto |
| `carga_detail.html` | Adaptar existente | Badge tipo flujo; fotos condicionales |

---

## Cambios requeridos

### 1. Modelo `Unidad` (`modulos/unidades/models.py`)

Agregar campo para la funcionalidad futura (checkbox, **sin conectar a lógica todavía**):

```python
control_combustible_total = models.BooleanField(
    default=False,
    verbose_name="Control total de combustible",
    help_text="Si está activo, esta unidad local requerirá el proceso completo de 6 pasos al cargar combustible"
)
```

- Migración: `python manage.py makemigrations unidades`
- Agregar al `admin.py` de unidades (solo visible, no afecta flujo aún)

---

### 2. Modelo `CargaCombustible` (`modulos/combustible/models.py`)

#### 2a. Campo `tipo_flujo` — trazabilidad

```python
TIPO_FLUJO_CHOICES = [
    ('FORANEO', 'Foráneo / Completo'),
    ('LOCAL', 'Local / Simplificado'),
]

tipo_flujo = models.CharField(
    max_length=10,
    choices=TIPO_FLUJO_CHOICES,
    default='FORANEO',
    verbose_name="Tipo de flujo de registro"
)
```

Permite saber después con qué proceso se registró cada carga.

#### 2b. Hacer nullable los campos omitidos en flujo LOCAL

Solo `foto_tablero` y `foto_candado_anterior` son ImageFields sin `null=True` que el flujo LOCAL no capturará. Los demás campos ya reciben defaults temporales en el Paso 1 (`kilometraje_actual=0`, `nivel_combustible_inicial='VACIO'`, `estado_candado_anterior='NORMAL'`) y no requieren cambio de esquema.

```python
foto_tablero = models.ImageField(
    storage=MediaStorage(),
    upload_to='combustible/tablero/%Y/%m/',
    null=True,          # ← agregar
    blank=True,         # ← agregar
    verbose_name="Foto del tablero"
)

foto_candado_anterior = models.ImageField(
    storage=MediaStorage(),
    upload_to='combustible/candado_anterior/%Y/%m/',
    null=True,          # ← agregar
    blank=True,         # ← agregar
    verbose_name="Foto candado anterior"
)
```

> **Los formularios `Paso2Form` y `Paso3Form` no se modifican.** Sus campos siguen siendo `required=True`. Esa validación del frontend aplica solo a FORANEO (son los únicos que ven esos pasos). El flujo LOCAL nunca llega a esos templates.

- Migración: `python manage.py makemigrations combustible`

---

### 3. Sesión: almacenar el tipo de flujo

En el POST del Paso 1, al crear la `CargaCombustible`, detectar el tipo de unidad y guardar el flujo en sesión:

```python
# views.py — CargaCombustibleWizardView.post(), paso == 1
unidad = form.cleaned_data['unidad']
tipo_flujo = 'LOCAL' if unidad.tipo == 'LOCAL' else 'FORANEO'

carga = CargaCombustible(
    tipo_flujo=tipo_flujo,
    ...
)
carga.save()
request.session['carga_combustible_id'] = carga.id
request.session['carga_tipo_flujo'] = tipo_flujo  # ← nuevo

# Routing diferenciado desde el paso 1
if tipo_flujo == 'LOCAL':
    return redirect('combustible:wizard', paso=4)
else:
    return redirect('combustible:wizard', paso=2)
```

**Nota futura (no implementar ahora):** cuando se active `control_combustible_total`:
```python
es_local_simplificado = (unidad.tipo == 'LOCAL' and not unidad.control_combustible_total)
tipo_flujo = 'LOCAL' if es_local_simplificado else 'FORANEO'
```

---

### 4. Vista `CargaCombustibleWizardView` (`modulos/combustible/views.py`)

#### 4a. Leer tipo de flujo al inicio de cada método

```python
def get(self, request, paso=1):
    tipo_flujo = request.session.get('carga_tipo_flujo', 'FORANEO')
    es_local = (tipo_flujo == 'LOCAL')
    ...

def post(self, request, paso=1):
    tipo_flujo = request.session.get('carga_tipo_flujo', 'FORANEO')
    es_local = (tipo_flujo == 'LOCAL')
    ...
```

#### 4b. Proteger pasos omitidos en flujo LOCAL

Al inicio del `get()`, antes de procesar el paso:

```python
PASOS_OMITIDOS_LOCAL = [2, 3, 5]

if es_local and paso in PASOS_OMITIDOS_LOCAL:
    return redirect('combustible:wizard', paso=4)
```

Evita que alguien acceda manualmente a `/combustible/nueva-carga/paso/3/` durante una sesión LOCAL.

#### 4c. Routing diferenciado en el POST del Paso 4

```python
elif paso == 4:
    form = Paso4Form(request.POST)
    if form.is_valid() and carga_id:
        carga.cantidad_litros = form.cleaned_data['cantidad_litros']
        carga.save()
        messages.success(request, '✓ Cantidad de litros registrada')
        if es_local:
            return redirect('combustible:wizard', paso=6)  # salta paso 5
        return redirect('combustible:wizard', paso=5)
```

#### 4d. Selección de template para Paso 4

```python
elif paso == 4:
    template = 'combustible/wizard_local_paso4.html' if es_local else 'combustible/wizard_paso4.html'
    ...
    return render(request, template, context)
```

#### 4e. Helper de contexto de progreso dinámico

Extraer la lógica de progreso a un método privado de la vista:

```python
PASOS_LOCALES = [1, 4, 6]
PASOS_FORANEOS = [1, 2, 3, 4, 5, 6]

def _contexto_progreso(self, paso, es_local):
    pasos = PASOS_LOCALES if es_local else PASOS_FORANEOS
    total = len(pasos)
    paso_visible = (pasos.index(paso) + 1) if paso in pasos else paso
    progreso = int((paso_visible / total) * 100)
    return {
        'paso': paso,
        'paso_visible': paso_visible,
        'total_pasos': total,
        'progreso': progreso,
        'es_flujo_local': es_local,
        'paso_anterior': self._paso_anterior(paso, es_local),
    }

def _paso_anterior(self, paso, es_local):
    """Calcula el paso anterior según el flujo."""
    if es_local:
        mapa = {4: 1, 6: 4}
    else:
        mapa = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
    return mapa.get(paso, 1)
```

Usar este helper en cada `render()` del wizard:
```python
context = {
    'form': form,
    **self._contexto_progreso(paso, es_local),
}
```

---

### 5. Templates

#### 5a. Cambios comunes a todos los templates de wizard existentes

En los 6 templates actuales, cambiar en la barra de progreso:

```html
<!-- Antes (hardcodeado) -->
<h2 class="text-lg font-semibold text-gray-800">Paso {{ paso }} de {{ total_pasos }}</h2>
<span class="text-sm text-gray-600">{{ progreso }}%</span>
<div style="width: {{ progreso }}%"></div>

<!-- Después (dinámico) -->
<h2 class="text-lg font-semibold text-gray-800">Paso {{ paso_visible }} de {{ total_pasos }}</h2>
<span class="text-sm text-gray-600">{{ progreso }}%</span>
<div style="width: {{ progreso }}%"></div>
```

Y en el botón "Atrás" de los pasos 4 y 6, reemplazar el número hardcodeado:

```html
<!-- wizard_paso4.html — Antes -->
<a href="{% url 'combustible:wizard' paso=3 %}">← Atrás</a>

<!-- wizard_paso4.html — Después -->
<a href="{% url 'combustible:wizard' paso=paso_anterior %}">← Atrás</a>

<!-- wizard_paso6.html — Antes -->
<a href="{% url 'combustible:wizard' paso=5 %}">← Atrás</a>

<!-- wizard_paso6.html — Después -->
<a href="{% url 'combustible:wizard' paso=paso_anterior %}">← Atrás</a>
```

Esto soluciona automáticamente el "Atrás" para ambos flujos sin condicionales en el template.

#### 5b. `wizard_paso1.html` — badge de tipo de unidad

Agregar bajo el selector de unidad:

```html
<!-- Badge informativo (aparece al seleccionar unidad) -->
<div id="flujo-badge" class="hidden mt-2 px-3 py-2 rounded-lg text-sm font-medium">
    <span id="flujo-texto"></span>
</div>
```

En la vista GET del paso 1, inyectar el tipo de cada unidad:

```python
# views.py
import json
if paso == 1:
    form = Paso1Form()
    context['unidades_tipo_json'] = json.dumps({
        str(u.pk): u.tipo
        for u in Unidad.objects.filter(activa=True)
    })
```

En el `extra_js` del template, ampliar el listener del selector de unidad:

```javascript
const unidadesTipo = {{ unidades_tipo_json|safe }};

unidadSelect.addEventListener('change', function() {
    const tipo = unidadesTipo[this.value];
    const badge = document.getElementById('flujo-badge');
    const texto = document.getElementById('flujo-texto');

    if (!this.value) {
        badge.classList.add('hidden');
        return;
    }
    if (tipo === 'LOCAL') {
        badge.className = 'mt-2 px-3 py-2 rounded-lg text-sm font-medium bg-green-100 text-green-800';
        texto.textContent = '✓ Unidad local — proceso simplificado (3 pasos)';
    } else {
        badge.className = 'mt-2 px-3 py-2 rounded-lg text-sm font-medium bg-blue-100 text-blue-800';
        texto.textContent = '→ Unidad foránea/esperanza — proceso completo (6 pasos)';
    }
    badge.classList.remove('hidden');
    checkFormValid();
});
```

#### 5c. `wizard_local_paso4.html` — NUEVO template para LOCAL

Basado en `wizard_paso4.html` con las siguientes diferencias:

- **Eliminar** la sección `<!-- Resumen de la unidad -->` completa (muestra kilometraje=0 y nivel=Vacío, datos que no se capturaron)
- Mostrar solo el número económico y tipo de la unidad en un resumen mínimo:

```html
<!-- Resumen mínimo solo para LOCAL -->
<div class="bg-gray-50 rounded-lg p-4 mb-6">
    <h3 class="font-semibold text-gray-800 mb-2">📋 Unidad</h3>
    <div class="flex gap-4 text-sm">
        <div>
            <span class="text-gray-600">Número económico:</span>
            <span class="font-semibold text-gray-900 ml-1">{{ carga.unidad.numero_economico }}</span>
        </div>
        <div>
            <span class="text-gray-600">Tipo:</span>
            <span class="font-semibold text-gray-900 ml-1">{{ carga.unidad.get_tipo_display }}</span>
        </div>
    </div>
</div>
```

- **El botón "Atrás"** usa `paso_anterior` (que será `1` para LOCAL):

```html
<a href="{% url 'combustible:wizard' paso=paso_anterior %}">← Atrás</a>
```

- **El resto del template** (cronómetro AJAX, sección de litros, JS del timer) se mantiene idéntico al foráneo.

#### 5d. `carga_detail.html` — badge de flujo y fotos condicionales

Agregar badge del tipo de flujo usado:

```html
{% if carga.tipo_flujo == 'LOCAL' %}
    <span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-800">
        Flujo Local (simplificado)
    </span>
{% else %}
    <span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-blue-100 text-blue-800">
        Flujo Completo
    </span>
{% endif %}
```

Las secciones de fotos que no se capturan en LOCAL ya se manejan con `{% if carga.foto_tablero %}` (el campo ahora acepta null, así que Django no mostrará nada si está vacío). Verificar que el template actual usa estos checks — si no, agregarlos.

---

### 6. Signals (`modulos/combustible/signals.py`)

Las alertas de candado y el OCR deben ignorarse en flujo LOCAL (no hay foto de candado que procesar):

Refactorizar el signal actual en funciones privadas por tipo de verificación:

```python
@receiver(post_save, sender=CargaCombustible)
def generar_alertas_y_ocr(sender, instance, created, **kwargs):
    if instance.estado != 'COMPLETADO':
        return

    if instance.tipo_flujo == 'LOCAL':
        # Solo alertas aplicables sin datos de candado
        _verificar_exceso_litros(instance)
        _verificar_kilometraje_menor(instance)
        return

    # Flujo completo: todas las verificaciones
    _verificar_estado_candado(instance)
    _verificar_exceso_litros(instance)
    _verificar_kilometraje_menor(instance)
    _procesar_ocr_candado_anterior(instance)


def _verificar_estado_candado(carga): ...
def _verificar_exceso_litros(carga): ...
def _verificar_kilometraje_menor(carga): ...
def _procesar_ocr_candado_anterior(carga): ...
```

> **Nota:** El OCR de `FotoCandadoNuevo` (signal separado `post_save FotoCandadoNuevo`) no aplica en LOCAL porque no se registran fotos de candado nuevo. No requiere cambios — simplemente nunca se dispara.

---

### 7. Admin (`modulos/combustible/admin.py`)

Agregar `tipo_flujo` a:
- `list_display` — columna visible en el listado
- `list_filter` — filtro lateral por flujo
- `readonly_fields` — visible en la vista de detalle de cada carga

---

## Archivos a crear / modificar

| Archivo | Acción | Qué cambia |
|---------|--------|-----------|
| `modulos/unidades/models.py` | Modificar | Campo `control_combustible_total` (futuro) |
| `modulos/unidades/admin.py` | Modificar | Mostrar nuevo campo |
| `modulos/combustible/models.py` | Modificar | `tipo_flujo`; `null=True` en `foto_tablero` y `foto_candado_anterior` |
| `modulos/combustible/views.py` | Modificar | Routing diferenciado, helper de progreso, selección de template |
| `modulos/combustible/signals.py` | Modificar | Refactorizar en funciones privadas; omitir candado en LOCAL |
| `modulos/combustible/admin.py` | Modificar | Mostrar `tipo_flujo` |
| `templates/combustible/wizard_paso1.html` | Modificar | Badge + JSON de tipos; `paso_visible` |
| `templates/combustible/wizard_paso2.html` | Modificar | Solo `paso_visible` en barra de progreso |
| `templates/combustible/wizard_paso3.html` | Modificar | Solo `paso_visible` en barra de progreso |
| `templates/combustible/wizard_paso4.html` | Modificar | `paso_visible`; `paso_anterior` en "Atrás" |
| `templates/combustible/wizard_local_paso4.html` | **Crear** | Sin resumen engañoso; "Atrás" a paso 1 |
| `templates/combustible/wizard_paso5.html` | Modificar | Solo `paso_visible` en barra de progreso |
| `templates/combustible/wizard_paso6.html` | Modificar | `paso_visible`; `paso_anterior` en "Atrás" |
| `templates/combustible/carga_detail.html` | Modificar | Badge de flujo; verificar fotos condicionales |

---

## Migraciones

```bash
python manage.py makemigrations unidades     # control_combustible_total
python manage.py makemigrations combustible  # tipo_flujo, nullable foto_tablero/foto_candado_anterior
python manage.py migrate
```

---

## Funcionalidad futura: `control_combustible_total` (NO implementar ahora)

El campo ya existirá en la BD desde la migración. Para activarlo en el futuro, **un solo cambio** en `views.py`:

```python
# Cambiar esto:
tipo_flujo = 'LOCAL' if unidad.tipo == 'LOCAL' else 'FORANEO'

# Por esto:
es_local_simplificado = (unidad.tipo == 'LOCAL' and not unidad.control_combustible_total)
tipo_flujo = 'LOCAL' if es_local_simplificado else 'FORANEO'
```

Y actualizar el badge en `wizard_paso1.html` para mostrar el caso de "LOCAL con control total = proceso completo".

---

## Orden de implementación sugerido

1. **Migraciones** — `Unidad` y `CargaCombustible` (base para todo lo demás)
2. **`signals.py`** — refactorizar antes de cambiar la vista para no romper cargas existentes
3. **`views.py`** — routing diferenciado + helper de progreso + selección de template
4. **Barra de progreso** — `paso_visible` y `paso_anterior` en los 6 templates existentes (cambio pequeño, bajo riesgo)
5. **`wizard_local_paso4.html`** — crear el template nuevo
6. **`wizard_paso1.html`** — badge + JSON de tipos
7. **`carga_detail.html`** — badge de flujo y fotos condicionales
8. **Admin** — agregar `tipo_flujo`
9. **Pruebas manuales** — verificar flujo LOCAL y FORANEO end-to-end
