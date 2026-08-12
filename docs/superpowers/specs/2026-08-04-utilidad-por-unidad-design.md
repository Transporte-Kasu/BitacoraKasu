# Diseño: Reporte de Utilidad/Pérdida por Unidad (Admin)

**Fecha:** 2026-08-04
**Estado:** Aprobado

---

## Objetivo

Dar visibilidad, desde una sola vista en el admin de Django, de qué unidades (vehículos) generan utilidad y cuáles generan pérdida, cruzando ingresos de viaje (bitácoras) contra gastos de combustible, taller y consumibles de almacén.

**Hallazgo que condiciona el diseño:** hoy no existe ningún dato de ingreso en el sistema (`BitacoraViaje`/`Cliente` no tienen tarifa/flete) ni de costo monetario de combustible (`CargaCombustible` solo registra litros). Tampoco existe ningún modelo de "pipa" ni de tanque de almacenamiento — el combustible de la flotilla se abastece llenando un tanque propio mediante pipas periódicas, y el costo real por litro es el que cobra cada pipa (costo total pagado ÷ litros recibidos), no un valor fijo capturado a mano. Este diseño agrega ambos antes de poder calcular utilidad real, siguiendo el modelo de negocio confirmado por el usuario: **tarifa única global por kilómetro**, y **precio de diesel derivado de las compras reales de pipa, con historial mensual garantizado** (al menos un precio por mes, aunque no llegue pipa ese mes), para no alterar cálculos de períodos pasados cuando el costo cambie.

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

`TarifaKilometro` con `Meta.ordering = ['-vigente_desde']` y un método de clase/manager `vigente_en(fecha)` que retorna el registro con `vigente_desde <= fecha` más reciente y `activo=True` (o `None` si no hay ninguno, ej. antes de la primera tarifa capturada). Se registra en `modulos/finanzas/admin.py` con CRUD estándar — cualquier usuario con permiso agrega una nueva tarifa vigente sin tocar código. `list_display` muestra `valor`, `vigente_desde`, `activo`.

### `RecepcionPipa` (fuente real del costo de diésel)

Registra cada recepción real de pipa que rellena el tanque de almacenamiento de la empresa — es la transacción de la que se deriva el precio, no un valor capturado a mano:

```python
fecha = models.DateField()
litros = models.DecimalField(max_digits=10, decimal_places=2)          # litros recibidos
costo_total = models.DecimalField(max_digits=12, decimal_places=2)     # lo pagado a la pipa, factura completa
proveedor = models.CharField(max_length=200, blank=True)               # texto libre; sin FK a compras.Proveedor por ahora (módulos desacoplados)
factura = models.FileField(upload_to='combustible/pipas/%Y/%m/', null=True, blank=True)
notas = models.TextField(blank=True)
created_at = models.DateTimeField(auto_now_add=True)
```

Propiedad `precio_litro` (no almacenada): `costo_total / litros`. Se registra en `modulos/finanzas/admin.py` con CRUD estándar — captura manual por cada pipa que llega, con su factura adjunta (mismo patrón de storage que `combustible/{type}/%Y/%m/` ya usado en el proyecto).

### `PrecioDieselMensual` (histórico mensual, derivado)

Fila agregada por mes calendario, para no tener que recorrer todas las `RecepcionPipa` cada vez que se calcula el costo de una carga:

```python
anio = models.PositiveIntegerField()
mes = models.PositiveSmallIntegerField()  # 1-12
litros_totales = models.DecimalField(max_digits=12, decimal_places=2)
costo_total = models.DecimalField(max_digits=14, decimal_places=2)
precio_promedio_litro = models.DecimalField(max_digits=10, decimal_places=4)  # costo_total / litros_totales, ponderado
actualizado_en = models.DateTimeField(auto_now=True)

class Meta:
    unique_together = ('anio', 'mes')
    ordering = ['-anio', '-mes']
```

Se recalcula automáticamente vía signal `post_save`/`post_delete` en `RecepcionPipa`: junta todas las `RecepcionPipa.fecha` dentro de ese `(anio, mes)`, suma `litros` y `costo_total`, y hace `update_or_create` del renglón mensual con el promedio ponderado. Así el histórico mensual siempre refleja las pipas capturadas ese mes, sin backfill manual.

Método de clase `vigente_en(fecha)`: busca el renglón `(anio, mes)` de la fecha dada; si no existe (no llegó pipa ese mes), **hace carry-forward** al mes anterior más reciente que sí tenga renglón (garantiza al menos un precio disponible por mes desde que existe la primera pipa capturada, sin exigir que llegue pipa todos los meses); si no hay ningún mes anterior con datos, retorna `None`.

`PrecioDieselMensual` se registra en el admin **solo de lectura** (sin permiso de alta/edición manual — es 100% derivado de `RecepcionPipa`), como tabla de auditoría del histórico mensual.

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

Misma lógica: al pasar `estado` a `COMPLETADO`, si `costo_calculado` es `None` y hay `PrecioDieselMensual.vigente_en(fecha)`, se calcula `costo_calculado = cantidad_litros * precio.precio_promedio_litro` (con carry-forward al mes anterior con datos si el mes de la carga aún no tiene ninguna `RecepcionPipa`). Cargas pasadas quedan en `None`, sin backfill.

Nota: el precio es mensual, no por carga individual — todas las cargas de un mismo mes usan el mismo `precio_promedio_litro`, aunque el precio real de la pipa haya cambiado a mitad de mes. Es una aproximación deliberada (granularidad mínima mensual, según lo pedido); si se necesitara precisión diaria más adelante, `RecepcionPipa` ya tiene la fecha exacta para refinar `vigente_en()` sin cambiar el resto del diseño.

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
| App `modulos/finanzas` (3 modelos nuevos: `TarifaKilometro`, `RecepcionPipa`, `PrecioDieselMensual`) | Aditivo |
| `BitacoraViaje.ingreso_calculado` | Campo nuevo, `null=True` |
| `CargaCombustible.costo_calculado` | Campo nuevo, `null=True` |

Ningún registro existente se modifica, borra ni regenera. Las migraciones son puramente de esquema (`AddField`/`CreateModel`), sin `RunPython` de backfill.

---

## 6. Archivos a crear o modificar

| Archivo | Cambio |
|---|---|
| `modulos/finanzas/` (nueva app) | `models.py` (`TarifaKilometro`, `RecepcionPipa`, `PrecioDieselMensual`), `admin.py`, `apps.py`, `signals.py` (recalcular `PrecioDieselMensual` en `post_save`/`post_delete` de `RecepcionPipa`), migración inicial |
| `config/settings.py` | Agregar `modulos.finanzas` a `INSTALLED_APPS` |
| `modulos/bitacoras/models.py` | Campo `ingreso_calculado` + lógica en `save()` |
| `modulos/bitacoras/migrations/` | Nueva migración `AddField` |
| `modulos/combustible/models.py` | Campo `costo_calculado` + lógica en `save()`, usando `PrecioDieselMensual.vigente_en()` |
| `modulos/combustible/migrations/` | Nueva migración `AddField` |
| `modulos/unidades/admin.py` | Nueva vista `reporte_utilidad_view` + `get_urls()` + botón en changelist |
| `templates/admin/unidades/reporte_utilidad.html` | Nuevo template |
| `modulos/finanzas/tests.py` | Tests de `TarifaKilometro.vigente_en()`; tests de `PrecioDieselMensual.vigente_en()` incluyendo carry-forward a mes sin pipas y caso sin ningún mes previo con datos; test de que el signal recalcula el promedio ponderado al agregar/borrar `RecepcionPipa` |
| `modulos/bitacoras/tests.py` | Test de cálculo de `ingreso_calculado` al completar viaje |
| `modulos/combustible/tests.py` | Test de cálculo de `costo_calculado` al completar carga, usando el precio mensual vigente |
| `modulos/unidades/tests.py` | Test de agregación del reporte (evita doble conteo, totales correctos) |

---

## 7. Lo que NO incluye este diseño

- Tarifas variables por cliente, tipo de unidad o ruta — solo tarifa única global por km (según decisión del usuario).
- Recalcular o backfillear `ingreso_calculado`/`costo_calculado` en viajes o cargas ya existentes.
- Reporte histórico de utilidad para períodos anteriores a esta implementación (esos registros no tendrán ingreso/costo calculado).
- Ajustes manuales de ingreso por viaje (descuentos, recargos) — el ingreso siempre se deriva de distancia × tarifa vigente.
- Integración con el módulo `modulos/reportes` (generador programado/email/narrativa IA) — este reporte vive únicamente como vista bajo demanda en el admin de `Unidad`, no como `ConfiguracionReporte` programado. Se puede añadir después reutilizando los mismos cálculos.
- Múltiples tanques de almacenamiento o pipas asignadas a una unidad/ruta específica — se asume un solo tanque de diésel compartido por toda la flotilla, así que el precio mensual derivado de `RecepcionPipa` es único y global, no por unidad.
- Precio de diésel con granularidad diaria/por carga — la granularidad mínima garantizada es mensual (con carry-forward si un mes no tuvo pipas); todas las cargas del mismo mes usan el mismo `precio_promedio_litro`.
- Vincular `RecepcionPipa` al flujo de `compras` (`Requisicion`/`OrdenCompra`/`Proveedor`) — por ahora es captura directa e independiente en `modulos/finanzas`, con `proveedor` como texto libre.
