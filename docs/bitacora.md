# Bitácoras — Análisis y Plan de Implementación

## Estructura del Archivo

**6 hojas:** ENERO 2026, FEBRERO 2026, MARZO 2026, ABRIL 2026, MAYO 2026, OPERADORES

**15 columnas:**

| Col | Campo |
|-----|-------|
| A | SALIDA A RUTA |
| B | OPERADOR |
| C | MODALIDAD |
| D | UNIDAD |
| E | PLACAS |
| F | CONTENEDOR |
| G | PESO |
| H | FECHA DE CARGA |
| I | DIESEL CARGADO |
| J | SELLOS |
| K | KM |
| L | CP |
| M | OBSERVACIONES |
| N | REPARTO |
| O | DESTINO |

---

## Interpretación del Relleno Rojo

Las columnas con **relleno rojo** (`#FF6D6D`) identifican los campos que **solo aplican para viajes foráneos** (SENCILLO y FULL). Estos campos están vacíos (`-`) en LOCAL y GRUA.

Columnas en **rojo:** `A (SALIDA A RUTA)`, `C (MODALIDAD)`, `F (CONTENEDOR)`, `G (PESO)`, `L (CP)`, `M (OBSERVACIONES)`, `N (REPARTO)`, `O (DESTINO)`

Columnas **sin rojo** (siempre presentes): `B (OPERADOR)`, `D (UNIDAD)`, `E (PLACAS)`, `H (FECHA DE CARGA)`, `I (DIESEL CARGADO)`, `J (SELLOS)`, `K (KM)`

---

## Campos por Modalidad

### LOCAL

> Viajes locales sin carga de contenedor, sin salida a ruta foránea.

| Campo | Estado | Notas |
|-------|--------|-------|
| SALIDA A RUTA | ❌ No aplica | Siempre vacío |
| OPERADOR | ✅ Obligatorio | |
| MODALIDAD | ✅ Obligatorio | Valor: `LOCAL` |
| UNIDAD | ✅ Obligatorio | |
| PLACAS | ⚠️ Opcional | ~88% de registros lo tienen |
| CONTENEDOR | ❌ No aplica | Siempre vacío |
| PESO | ❌ No aplica | Siempre vacío |
| FECHA DE CARGA | ✅ Obligatorio | |
| DIESEL CARGADO | ✅ Obligatorio | |
| SELLOS | ⚠️ Opcional | Solo ~2% de registros |
| KM | ❌ No aplica | Siempre vacío |
| CP | ❌ No aplica | Siempre vacío |
| OBSERVACIONES | ❌ No aplica | Siempre vacío |
| REPARTO | ❌ No aplica | Siempre vacío |
| DESTINO | ❌ No aplica | Siempre vacío |

**Campos requeridos para registrar:** OPERADOR, MODALIDAD, UNIDAD, FECHA DE CARGA, DIESEL CARGADO

---

### SENCILLO

> Viaje foráneo con un solo contenedor (sin reparto).

| Campo | Estado | Notas |
|-------|--------|-------|
| SALIDA A RUTA | ✅ Obligatorio | |
| OPERADOR | ✅ Obligatorio | |
| MODALIDAD | ✅ Obligatorio | Valor: `SENCILLO` |
| UNIDAD | ✅ Obligatorio | |
| PLACAS | ✅ Obligatorio | |
| CONTENEDOR | ✅ Obligatorio | |
| PESO | ✅ Obligatorio | |
| FECHA DE CARGA | ✅ Obligatorio | |
| DIESEL CARGADO | ✅ Obligatorio | |
| SELLOS | ✅ Obligatorio | |
| KM | ✅ Obligatorio | |
| CP | ✅ Obligatorio | Código postal de destino |
| OBSERVACIONES | ⚠️ Opcional | Solo ~1% de registros |
| REPARTO | ❌ No aplica | Siempre vacío |
| DESTINO | ✅ Obligatorio | |

**Campos requeridos para registrar:** SALIDA A RUTA, OPERADOR, MODALIDAD, UNIDAD, PLACAS, CONTENEDOR, PESO, FECHA DE CARGA, DIESEL CARGADO, SELLOS, KM, CP, DESTINO

---

### FULL

> Viaje foráneo con dos contenedores o con reparto (SI/NO).

| Campo | Estado | Notas |
|-------|--------|-------|
| SALIDA A RUTA | ✅ Obligatorio | |
| OPERADOR | ✅ Obligatorio | |
| MODALIDAD | ✅ Obligatorio | Valor: `FULL` |
| UNIDAD | ✅ Obligatorio | |
| PLACAS | ✅ Obligatorio | |
| CONTENEDOR | ✅ Obligatorio | |
| PESO | ✅ Obligatorio | |
| FECHA DE CARGA | ✅ Obligatorio | |
| DIESEL CARGADO | ✅ Obligatorio | |
| SELLOS | ✅ Obligatorio | |
| KM | ✅ Obligatorio | |
| CP | ✅ Obligatorio | Código postal de destino |
| OBSERVACIONES | ⚠️ Opcional | Solo ~3% de registros |
| REPARTO | ✅ Obligatorio | Valores: `SI` / `NO` — **diferencia clave vs SENCILLO** |
| DESTINO | ✅ Obligatorio | |

**Campos requeridos para registrar:** SALIDA A RUTA, OPERADOR, MODALIDAD, UNIDAD, PLACAS, CONTENEDOR, PESO, FECHA DE CARGA, DIESEL CARGADO, SELLOS, KM, CP, REPARTO, DESTINO

---

## Diferencias Clave entre Modalidades

| Campo | LOCAL | SENCILLO | FULL |
|-------|-------|----------|------|
| SALIDA A RUTA | ❌ | ✅ | ✅ |
| PLACAS | ⚠️ | ✅ | ✅ |
| CONTENEDOR | ❌ | ✅ | ✅ |
| PESO | ❌ | ✅ | ✅ |
| SELLOS | ⚠️ | ✅ | ✅ |
| KM | ❌ | ✅ | ✅ |
| CP | ❌ | ✅ | ✅ |
| REPARTO | ❌ | ❌ | ✅ |
| DESTINO | ❌ | ✅ | ✅ |

> **Regla rápida:** FULL = SENCILLO + campo REPARTO obligatorio

---

## Catálogo de Operadores (Hoja OPERADORES)

Tres categorías, cada una con: nombre, número económico (ECO), placas.

| Columna | Tipo |
|---------|------|
| A | LOCALEROS |
| C | FORÁNEOS |
| E | FORANEOS ESPERANZA |

Coincide con los tipos de operador en el modelo `Operador` del sistema: `LOCAL`, `FORANEO`, `ESPERANZA`.

---

## Otras Modalidades Registradas

| Modalidad | Campos requeridos |
|-----------|-------------------|
| GRUA | OPERADOR, MODALIDAD, UNIDAD, FECHA DE CARGA, DIESEL CARGADO (igual que LOCAL) |
| CAJA SECA | Similar a SENCILLO |
| RETRO | Similar a LOCAL |

---

---

# Plan de Implementación

## Estado actual del módulo

El modelo `BitacoraViaje` existe en `modulos/bitacoras/models.py` con:
- `MODALIDAD_CHOICES`: solo SENCILLO y FULL (falta LOCAL)
- Un solo `contenedor` / `peso` / `sellos` (FULL necesita dos)
- Falta campo `salida_a_ruta`
- `placas` no debe ser campo propio — se obtiene vía `bitacora.unidad.placa`
- No existen templates todavía

---

## Paso 1 — Modelo (`modulos/bitacoras/models.py`)

### Campos a agregar

```python
# MODALIDAD_CHOICES — agregar LOCAL (sin form/views por ahora)
('LOCAL', 'Local'),

# Referencia documental de salida
salida_a_ruta = models.CharField(max_length=50, blank=True, verbose_name="Salida a ruta")

# Segundo contenedor (solo FULL — null/blank porque SENCILLO no los usa)
contenedor_2 = models.CharField(max_length=50, blank=True, verbose_name="Contenedor 2")
peso_2 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Peso 2 (kg)")
sellos_2 = models.CharField(max_length=100, blank=True, verbose_name="Sellos contenedor 2")
```

### Renombrar verbose_name

- `contenedor` → `"Contenedor 1"`
- `sellos` → `"Sellos contenedor 1"`
- `peso` → `"Peso 1 (kg)"`

### Agregar método `clean()`

```python
def clean(self):
    from django.core.exceptions import ValidationError
    if self.modalidad == 'FULL' and not self.contenedor_2:
        raise ValidationError({'contenedor_2': 'FULL requiere segundo contenedor.'})
    if self.modalidad == 'SENCILLO':
        if self.contenedor_2 or self.peso_2 or self.sellos_2:
            raise ValidationError('SENCILLO no puede tener datos del segundo contenedor.')
        if self.reparto:
            raise ValidationError({'reparto': 'SENCILLO no usa reparto.'})
```

---

## Paso 2 — Migración

```bash
python manage.py makemigrations bitacoras
python manage.py migrate
```

Genera `0002_bitacoraviaje_campos_full_y_local.py` con `AddField` para `salida_a_ruta`, `contenedor_2`, `peso_2`, `sellos_2` y `AlterField` para `modalidad`. No requiere `RunPython` ya que todos los campos nuevos son `blank=True / null=True`.

---

## Paso 3 — Form (`modulos/bitacoras/forms.py`)

**Estrategia: un solo form con secciones condicionales** (no forms separados — la diferencia son solo 3 campos + 1 booleano).

Campos del form en orden:

```
modalidad, operador, unidad, salida_a_ruta
fecha_carga, fecha_salida, diesel_cargado, kilometraje_salida
contenedor, peso, sellos                    ← Contenedor 1
contenedor_2, peso_2, sellos_2, reparto     ← Solo FULL (hidden/shown por JS)
cp_origen, cp_destino, destino
observaciones
```

Validación cruzada en `clean()` del form:
- FULL requiere `contenedor_2`
- SENCILLO no puede tener `reparto=True`

---

## Paso 4 — Views (`modulos/bitacoras/views.py`)

### Cambios

| View | Cambio |
|------|--------|
| `BitacoraCreateView` | Redirigir a `detail` tras crear (no a lista) |
| `BitacoraUpdateView` | Aplicar patrón `next` (pendiente según MEMORY) |
| `BitacoraDeleteView` | Aplicar patrón `next` |
| `BitacoraListView` | Agregar filtros por fecha, operador, unidad al context |

### Nuevas views AJAX

```python
# 1. GET /bitacoras/ajax/unidad-info/?unidad_id=X
# Devuelve: { placa, kilometraje_actual, numero_economico }
# Uso: auto-rellenar placa y km en el form al seleccionar unidad
def unidad_info_ajax(request): ...

# 2. GET /bitacoras/ajax/calcular-distancia/?cp_origen=40812&cp_destino=06600
# Devuelve: { success, distancia_km, duracion_min, distancia_texto, duracion_texto }
# Uso: preview de KM en tiempo real mientras se llena el form (sin pk, antes de guardar)
def calcular_distancia_preview_ajax(request): ...
```

El endpoint existente `/<pk>/calcular-distancia/` requiere una bitácora ya guardada — no sirve para el form de creación. El nuevo endpoint preview resuelve esto.

### Bug a corregir

`calcular_distancia_google` usa `from core.services.google_maps` — debe ser `from config.services.google_maps`.

---

## Paso 5 — URLs (`modulos/bitacoras/urls.py`)

Agregar:

```python
path('ajax/unidad-info/', views.unidad_info_ajax, name='unidad_info_ajax'),
path('ajax/calcular-distancia/', views.calcular_distancia_preview_ajax, name='calcular_distancia_preview'),
```

---

## Paso 6 — Templates (`templates/bitacoras/`)

| Template | Descripción |
|----------|-------------|
| `bitacora_form.html` | Form crear/editar con sección FULL dinámica (JS) |
| `bitacora_list.html` | Lista con filtros, tabla, paginación, patrón `?next=` en Editar/Eliminar |
| `bitacora_detail.html` | Detalle con stats (km, rendimiento, horas) si completado |
| `bitacora_confirm_delete.html` | Confirmación eliminación |
| `completar_viaje.html` | Form de cierre: `fecha_llegada`, `kilometraje_llegada` |
| `bitacora_dashboard.html` | Resumen estadístico del módulo |

### Lógica JS en `bitacora_form.html`

```javascript
// 1. Al cambiar modalidad → mostrar/ocultar #seccion-full

// 2. Al cambiar unidad → fetch('/bitacoras/ajax/unidad-info/?unidad_id=X')
//    → auto-rellenar campo placas (readonly) y kilometraje_salida

// 3. Al escribir cp_destino (evento blur/debounce 800ms):
//    → fetch('/bitacoras/ajax/calcular-distancia/?cp_origen=40812&cp_destino=XXXXX')
//    → mostrar debajo del campo: "≈ 425 km · 5h 30min"
//    → si no hay API key o CP inválido, mostrar mensaje discreto en gris
//    Los valores se guardan automáticamente en distancia_calculada/duracion_estimada al crear la bitácora
```

Referencia de estilos: `templates/taller/crear_orden.html` (clases `form-section`, `form-label`, `form-input`).

---

## Paso 7 — Admin (`modulos/bitacoras/admin.py`)

Actualizar `fieldsets` para incluir `salida_a_ruta` y agrupar los campos del segundo contenedor en sección colapsable `"Contenedor 2 (FULL)"`.

---

## Orden de implementación

1. `models.py` — campos nuevos + `clean()` + `MODALIDAD_CHOICES`
2. Migración
3. `forms.py` — reescribir `BitacoraViajeForm`
4. `views.py` — `unidad_info_ajax` + patrón `next` + corregir import GoogleMaps
5. `urls.py` — agregar ruta AJAX
6. `admin.py` — actualizar fieldsets
7. Templates — en orden: `bitacora_form.html` → `bitacora_list.html` → `bitacora_detail.html` → rest

---

## LOCAL — Pendiente

Solo se agrega `('LOCAL', 'Local')` a `MODALIDAD_CHOICES`. No se implementa form ni views hasta confirmar los campos requeridos.

---

## Notas

- **placas**: no es campo del modelo — se muestra vía `bitacora.unidad.placa` y se auto-rellena en el form con AJAX (readonly)
- **KM del Excel**: corresponde a `kilometraje_salida` (odómetro al salir), no a km recorridos
- **Patrón `next`**: obligatorio en `UpdateView` y `DeleteView` (pendiente según memoria del proyecto)
