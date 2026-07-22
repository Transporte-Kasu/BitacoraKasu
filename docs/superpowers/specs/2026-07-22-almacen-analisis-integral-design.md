# Diseño: Reporte "Análisis Integral de Almacén" (ALMACEN_ANALISIS_INTEGRAL)

**Fecha:** 2026-07-22
**Estado:** Aprobado

---

## Objetivo

Dar a la IA (IAKasu) visibilidad sobre tres procesos de almacén que hoy no forman parte de ningún reporte: asignaciones directas (`AsignacionDirectaAlmacen` y `AsignacionSalida`), entradas (`EntradaAlmacen`) y auditoría (`AuditoriaAlmacen`). Se agrega un nuevo tipo de reporte programado, `ALMACEN_ANALISIS_INTEGRAL`, que sigue el mismo patrón que los reportes existentes (`ALMACEN_MOVIMIENTOS`, `FLOTA_VIGENCIAS`): un generador de datos, una narrativa IA especializada, un bloque de email y export a Excel — sin infraestructura nueva.

---

## 1. Generador de datos

### Archivo: `modulos/reportes/generadores/almacen.py` — nueva función `generar_analisis_integral(periodo_inicio, periodo_fin)`

Consulta las tres fuentes dentro del período y arma tres listas con nombre explícito (mismo patrón que `top_5_salidas` / `sin_movimiento` en `ALMACEN_MOVIMIENTOS`):

#### a) Asignaciones directas (`datos['asignaciones']`)

Une `AsignacionDirectaAlmacen` (fila por registro, ya que no tiene items) y `AsignacionSalida.items` (fila por `ItemAsignacionSalida`) del período en una tabla unificada:

```
folio | tipo ('DIRECTA'|'SALIDA') | destino | producto_sku | producto_desc |
cantidad | motivo | entregado_por | fecha
```

`destino` usa `unidad` en `AsignacionDirectaAlmacen`, y `destino_display` (property ya existente) en `AsignacionSalida`.

KPIs en `resumen`:
- `total_asignaciones_directas`, `total_asignaciones_salida`
- `total_items_asignados` (suma de cantidades)
- `top_destinos` — top 5 unidades/equipos que más piezas reciben (señal de posibles fallas recurrentes)

#### b) Entradas (`datos['entradas']`)

`EntradaAlmacen` del período, desglosado por su campo `tipo` existente (`ENTRADA_DIRECTA`, `FACTURA`, `TALLER_REPARADO`, `TALLER_RECICLADO`, `AJUSTE`):

```
folio | tipo | tipo_display | recibido_por | costo_total_entrada | total_items | fecha_entrada
```

KPIs en `resumen`:
- `total_entradas`
- `entradas_por_tipo` (dict con conteo por cada tipo)
- `valor_total_entradas` (suma de `costo_total_entrada`)

#### c) Auditoría (`datos['auditoria']`)

`AuditoriaAlmacen` del período, agregada (no fila por evento crudo, para no saturar el reporte):

```
usuario | total_eventos | crear | editar | eliminar | autorizar | rechazar | entregar | cancelar
```

KPIs en `resumen`:
- `total_eventos_auditoria`
- `auditoria_por_accion` (dict conteo por `accion`)
- `top_usuarios_auditoria` (top 5 por actividad)
- `alertas_auditoria` — lista de strings con anomalías detectadas mediante reglas simples:
  - un usuario concentra más del 50% de los eventos del período (y hay ≥2 usuarios activos)
  - eliminaciones (`ELIMINAR`) superan el 20% del total de eventos
  - Estas reglas son deliberadamente simples (umbrales fijos, no estadística avanzada) — el objetivo es dar señales a la narrativa IA, no un motor de detección de fraude.

Retorna la misma envoltura estándar (`tipo`, `titulo`, `periodo_inicio/fin`, `generado_en`, `resumen`, y las tres listas nombradas). Se registra en el diccionario `GENERADORES` del archivo.

---

## 2. Narrativa IA

### Archivo: `modulos/reportes/generadores/narrativa.py`

Nueva función `_prompt_almacen_analisis_integral(resumen, datos, periodo_inicio, periodo_fin)`, análoga a `_prompt_almacen_movimientos`. Construye un prompt con:
- KPIs de las tres secciones
- Top 5 destinos de asignaciones directas
- Desglose de entradas por tipo
- Alertas de auditoría (si existen) y top usuarios

Pide a Claude que **correlacione** las tres fuentes en el análisis (ej. si una unidad concentra asignaciones directas repetidas, si el volumen de entradas es consistente con la actividad general, si las alertas de auditoría coinciden con picos de actividad). Usa `Modelo.SONNET` (igual que `ALMACEN_MOVIMIENTOS`, por la complejidad de correlacionar 3 fuentes) y `max_tokens=600`.

Se agrega la entrada correspondiente a `_NOMBRES_REPORTE` y al `if/elif` de selección de prompt en `generar_narrativa()`.

---

## 3. Registro del tipo de reporte

### Archivo: `modulos/reportes/models.py`

Se agrega a `ConfiguracionReporte.TIPO_CHOICES`:

```python
('ALMACEN_ANALISIS_INTEGRAL', 'Almacén — Análisis integral (asignaciones, entradas, auditoría)'),
```

Nueva migración de choices (`alter_configuracionreporte_tipo_reporte`), siguiendo el patrón de `0003`/`0005`.

### Archivo: `modulos/reportes/management/commands/generar_reportes.py`

Sin cambios estructurales — ya importa `gen_almacen.GENERADORES` completo, así que la nueva función queda disponible automáticamente en cuanto se registra en el diccionario del paso 1.

---

## 4. Email template

### Archivo: `templates/reportes/email/reporte_base.html`

Nuevo bloque `{% if datos.tipo == 'ALMACEN_ANALISIS_INTEGRAL' %}` (junto a los bloques existentes de `ALMACEN_MOVIMIENTOS` y el genérico), con:

- KPI grid: total asignaciones, total entradas, valor total entradas, total eventos de auditoría
- Tabla "Top Destinos de Asignaciones Directas" (folio, destino, producto, cantidad)
- Tabla "Entradas por Tipo" (tipo, conteo, valor)
- Tabla "Actividad de Auditoría por Usuario" (usuario, total eventos, desglose)
- Bloque de alerta (`.alert.danger` / `.alert`) si `datos.resumen.alertas_auditoria` no está vacío, listando cada anomalía detectada

Reutiliza las clases CSS existentes (`.kpi`, `.detail-table`, `.alert`, `.pill`) — no se agrega CSS nuevo.

---

## 5. Excel export

### Archivo: `modulos/reportes/management/commands/generar_reportes.py` — función `_generar_excel`

Las tres listas (`asignaciones`, `entradas`, `auditoria`) tienen columnas distintas entre sí, así que no caben en una sola hoja como hace el resto de los reportes (que usan `datos['filas']` con un único esquema de columnas).

Se extiende `_generar_excel` con soporte opcional para una clave `datos['tablas']`: un dict `{nombre_hoja: lista_de_filas}`. Si está presente, se crea una hoja por cada entrada (reutilizando la misma lógica de encabezados/anchos ya existente para la hoja de detalle) además de la hoja "Resumen" que ya se genera siempre. El comportamiento actual basado en `datos['filas']` no cambia — sigue funcionando igual para los demás tipos de reporte.

`generar_analisis_integral` retorna:
```python
'tablas': {
    'Asignaciones': asignaciones_filas,
    'Entradas': entradas_filas,
    'Auditoria': auditoria_filas,
}
```
(sin `filas` a nivel raíz, ya que no hay una tabla "principal" única para este reporte).

---

## 6. Archivos a crear o modificar

| Archivo | Cambio |
|---------|--------|
| `modulos/reportes/generadores/almacen.py` | Agregar `generar_analisis_integral()` y registrarla en `GENERADORES` |
| `modulos/reportes/generadores/narrativa.py` | Agregar `_prompt_almacen_analisis_integral()` y su entrada en `_NOMBRES_REPORTE` / selección de prompt |
| `modulos/reportes/models.py` | Agregar `ALMACEN_ANALISIS_INTEGRAL` a `TIPO_CHOICES` |
| `modulos/reportes/migrations/` | Nueva migración de choices |
| `modulos/reportes/management/commands/generar_reportes.py` | Extender `_generar_excel` con soporte para `datos['tablas']` |
| `templates/reportes/email/reporte_base.html` | Nuevo bloque condicional para `ALMACEN_ANALISIS_INTEGRAL` |
| `modulos/reportes/tests.py` | Tests del generador (conteos, reglas de anomalía) + smoke test dry-run |

---

## 7. Lo que NO incluye este diseño

- No agrega un botón de "análisis bajo demanda" en el dashboard — es únicamente un reporte programado (email/WhatsApp), igual que los demás.
- No modifica las reglas de auditoría existentes ni qué modelos se auditan.
- Las reglas de anomalía de auditoría son umbrales simples, no un motor estadístico o de detección de fraude.
- No agrega nuevas vistas ni endpoints — se configura desde la UI ya existente de `ConfiguracionReporte` (`/reportes/configuraciones/nueva/`).
