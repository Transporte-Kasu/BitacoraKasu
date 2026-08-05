# Diseño: Reporte de Utilidad/Pérdida por Unidad (Admin)

**Fecha:** 2026-08-04
**Estado:** Aprobado

---

## Objetivo

Dar visibilidad, desde una sola vista en el admin de Django, de qué unidades (vehículos) generan utilidad y cuáles generan pérdida, cruzando ingresos de viaje (bitácoras) contra gastos de combustible, taller y consumibles de almacén.

**Hallazgo que condiciona el diseño:** hoy no existe ningún dato de ingreso en el sistema (`BitacoraViaje`/`Cliente` no tienen tarifa/flete) ni de costo monetario de combustible (`CargaCombustible` solo registra litros). Este diseño agrega ambos antes de poder calcular utilidad real, siguiendo el modelo de negocio confirmado por el usuario: **tarifa única global por kilómetro**, y **precio de diesel global configurable**, ambos con historial de vigencia para no alterar cálculos de períodos pasados cuando la tarifa cambie.

No se borra ni se regenera ningún registro existente — todos los cambios son aditivos (modelos nuevos + campos nullable).

---

## 1. Nueva app `modulos/finanzas`

Aloja la configuración financiera compartida entre `bitacoras` y `combustible`, evitando mezclar conceptos de dinero dentro de apps operativas.

### `TarifaKilometro`
```python
valor = models.DecimalField(max_digits=10, decimal_places=2)  # $/km
vigente_desde = models.DateField()
activo = models.BooleanField(default=True)
```

### `PrecioDiesel`
```python
valor = models.DecimalField(max_digits=10, decimal_places=2)  # $/litro
vigente_desde = models.DateField()
activo = models.BooleanField(default=True)
```

Ambos con `Meta.ordering = ['-vigente_desde']`. Se agrega un método de clase o manager helper `vigente_en(fecha)` en cada modelo que retorna el registro con `vigente_desde <= fecha` más reciente y `activo=True` (o `None` si no hay ninguno, ej. antes de la primera tarifa capturada).

Ambos modelos se registran en `modulos/finanzas/admin.py` con CRUD estándar de Django (sin vistas custom) — cualquier usuario con permiso agrega una nueva tarifa vigente sin tocar código. `list_display` muestra `valor`, `vigente_desde`, `activo`.

---

## 2. Snapshot de ingreso/costo por registro

### `modulos/bitacoras/models.py` — `BitacoraViaje`

Nuevo campo:
```python
ingreso_calculado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
```

En el `save()` existente, donde ya se detecta `completado=True` (cuando se captura `fecha_llegada`), se agrega: si `ingreso_calculado` es `None` y hay una `TarifaKilometro.vigente_en(fecha_llegada)`, calcular `ingreso_calculado = distancia_efectiva * tarifa.valor` y guardarlo. Si no hay tarifa vigente, se deja en `None` (el viaje queda fuera del cálculo de utilidad hasta que exista tarifa aplicable).

Viajes ya completados antes de este cambio **no se recalculan**; quedan con `ingreso_calculado = None` permanentemente salvo edición manual.

### `modulos/combustible/models.py` — `CargaCombustible`

Nuevo campo:
```python
costo_calculado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
```

Misma lógica: al pasar `estado` a `COMPLETADO`, si `costo_calculado` es `None` y hay `PrecioDiesel.vigente_en(fecha)`, se calcula `costo_calculado = cantidad_litros * precio.valor`. Cargas pasadas quedan en `None`, sin backfill.

---

## 3. Cálculo de gastos por unidad (evitar doble conteo)

Gasto total por unidad, en el rango de fechas del reporte, es la suma de:

| Fuente | Campo/cálculo | Filtro |
|---|---|---|
| Taller | `OrdenTrabajo.costo_total_real` | `unidad=X`, `estado='COMPLETADA'`, `fecha_finalizacion` en rango |
| Combustible | `Sum(CargaCombustible.costo_calculado)` | `unidad=X`, `estado='COMPLETADO'`, fecha en rango |
| Consumibles almacén | `cantidad * producto.costo_unitario` sumado sobre `SalidaRapidaConsumible` + `AsignacionDirectaAlmacen` + `AsignacionSalida` (solo `tipo_destino='UNIDAD'`) | `unidad=X`, fecha en rango |

**Se excluye explícitamente** `SalidaAlmacen`/`ItemSalidaAlmacen` cuando está ligada a una `OrdenTrabajo` vía `SolicitudSalida.orden_trabajo` — esas piezas ya están contabilizadas dentro de `PiezaRequerida` → `OrdenTrabajo.costo_total_real`. Incluirlas de nuevo duplicaría el gasto.

Ingreso total por unidad = `Sum(BitacoraViaje.ingreso_calculado)` filtrado por `unidad=X`, `completado=True`, fecha en rango.

**Utilidad = Ingreso total − Gasto total.**

---

## 4. Reporte en el Admin

### Archivo: `modulos/unidades/admin.py` — extiende `UnidadAdmin`

Sigue el patrón ya usado por `CargaCombustibleAdmin.estadisticas_view` (`get_urls()` + vista registrada con `self.admin_site.admin_view(...)`, template propio, contexto con `self.admin_site.each_context(request)`):

- Botón "Reporte de Utilidad" en cabecera del changelist de `Unidad`.
- Filtro de rango de fechas (`GET` params `desde`/`hasta`, default: primer y último día del mes actual).
- Tabla, una fila por unidad activa:
  `Unidad | Ingresos | Gasto Combustible | Gasto Taller | Gasto Consumibles | Gasto Total | Utilidad $ | Utilidad %`
  - Badge verde si utilidad ≥ 0, rojo si negativa (mismo patrón `format_html` que el resto de los admins del proyecto).
- Fila de totales generales al final de la tabla.
- Indicador auxiliar (no bloqueante): cuántas bitácoras/cargas del rango quedaron excluidas por no tener `ingreso_calculado`/`costo_calculado` (transparencia sobre cobertura de datos).
- Botón "Exportar a Excel" reutilizando el patrón `openpyxl` existente (`estilo_header`, `estilo_fila`, `titulo_hoja`) de `CargaCombustibleAdmin`/`AuditoriaAlmacenAdmin`.

### Template nuevo: `templates/admin/unidades/reporte_utilidad.html`

Sigue la estructura visual de `templates/admin/combustible/reporte_estadisticas.html` (tabla con `each_context`, filtros de fecha en un `<form>` GET).

---

## 5. Migraciones y datos existentes

| Cambio | Tipo |
|---|---|
| App `modulos/finanzas` (2 modelos nuevos) | Aditivo |
| `BitacoraViaje.ingreso_calculado` | Campo nuevo, `null=True` |
| `CargaCombustible.costo_calculado` | Campo nuevo, `null=True` |

Ningún registro existente se modifica, borra ni regenera. Las migraciones son puramente de esquema (`AddField`/`CreateModel`), sin `RunPython` de backfill.

---

## 6. Archivos a crear o modificar

| Archivo | Cambio |
|---|---|
| `modulos/finanzas/` (nueva app) | `models.py` (`TarifaKilometro`, `PrecioDiesel`), `admin.py`, `apps.py`, migración inicial |
| `config/settings.py` | Agregar `modulos.finanzas` a `INSTALLED_APPS` |
| `modulos/bitacoras/models.py` | Campo `ingreso_calculado` + lógica en `save()` |
| `modulos/bitacoras/migrations/` | Nueva migración `AddField` |
| `modulos/combustible/models.py` | Campo `costo_calculado` + lógica en `save()` |
| `modulos/combustible/migrations/` | Nueva migración `AddField` |
| `modulos/unidades/admin.py` | Nueva vista `reporte_utilidad_view` + `get_urls()` + botón en changelist |
| `templates/admin/unidades/reporte_utilidad.html` | Nuevo template |
| `modulos/finanzas/tests.py` | Tests de `vigente_en()` (historial de tarifas, casos límite de fecha) |
| `modulos/bitacoras/tests.py` | Test de cálculo de `ingreso_calculado` al completar viaje |
| `modulos/combustible/tests.py` | Test de cálculo de `costo_calculado` al completar carga |
| `modulos/unidades/tests.py` | Test de agregación del reporte (evita doble conteo, totales correctos) |

---

## 7. Lo que NO incluye este diseño

- Tarifas variables por cliente, tipo de unidad o ruta — solo tarifa única global por km (según decisión del usuario).
- Recalcular o backfillear `ingreso_calculado`/`costo_calculado` en viajes o cargas ya existentes.
- Reporte histórico de utilidad para períodos anteriores a esta implementación (esos registros no tendrán ingreso/costo calculado).
- Ajustes manuales de ingreso por viaje (descuentos, recargos) — el ingreso siempre se deriva de distancia × tarifa vigente.
- Integración con el módulo `modulos/reportes` (generador programado/email/narrativa IA) — este reporte vive únicamente como vista bajo demanda en el admin de `Unidad`, no como `ConfiguracionReporte` programado. Se puede añadir después reutilizando los mismos cálculos.
