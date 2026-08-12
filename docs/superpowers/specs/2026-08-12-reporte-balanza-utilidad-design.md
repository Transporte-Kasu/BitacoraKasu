# Diseño: Reporte de Balanza de Utilidad por Unidad (módulo Reportes)

**Fecha:** 2026-08-12
**Estado:** Aprobado

---

## Objetivo

Integrar el cálculo de utilidad/pérdida por unidad (ya implementado en el admin de `Unidad` como vista bajo demanda, ver `docs/superpowers/specs/2026-08-04-utilidad-por-unidad-design.md`) al sistema de reportes programados (`modulos/reportes`), para que se pueda enviar automáticamente por correo (y WhatsApp, si está habilitado) con frecuencia **semanal** y **mensual**, con narrativa ejecutiva generada por IA y adjunto Excel — reutilizando toda la infraestructura ya existente de `ConfiguracionReporte` / `generar_reportes`.

**Hallazgo que simplifica el diseño:** el sistema de reportes programados ya resuelve semanal vs. mensual de forma genérica — `_periodo(frecuencia, dia_semana, dia_mes)` en `modulos/reportes/management/commands/generar_reportes.py` calcula el rango de fechas según la `frecuencia` de cada `ConfiguracionReporte`, sin que el generador de datos necesite saber si es semanal o mensual. Esto significa que **no se requiere código distinto para semanal y mensual** — solo se crean dos `ConfiguracionReporte` (una con `frecuencia='SEMANAL'`, otra con `frecuencia='MENSUAL'`) apuntando al mismo `tipo_reporte`.

No se borra ni se regenera ningún registro existente — todos los cambios son aditivos (un tipo de reporte nuevo, un generador nuevo, un refactor de ubicación sin cambio de comportamiento).

---

## 1. Refactor: mover `calcular_reporte_utilidad` a un módulo de servicio

Hoy la función vive en `modulos/unidades/admin.py` (junto con `_suma_cantidad_por_costo`), porque ahí es donde se construyó originalmente la vista bajo demanda. Para que el generador de reportes programados la reutilice sin importar código de `admin.py` (que registra `ModelAdmin` vía decoradores), se mueve tal cual — misma firma, mismo comportamiento — a un archivo nuevo:

**`modulos/unidades/services.py`**
```python
def _suma_cantidad_por_costo(queryset): ...
def calcular_reporte_utilidad(desde, hasta) -> dict: ...
```

`modulos/unidades/admin.py` pasa a importar `from .services import calcular_reporte_utilidad` y elimina las definiciones locales. Los 8 tests existentes en `modulos/unidades/tests.py` (`CalcularReporteUtilidadTests`) actualizan su import (`from .services import calcular_reporte_utilidad`) — sin cambios de aserciones, ya que el comportamiento es idéntico.

---

## 2. Nuevo tipo de reporte

**`modulos/reportes/models.py` — `ConfiguracionReporte.TIPO_CHOICES`**, se agrega:
```python
('UNIDADES_BALANZA_UTILIDAD', 'Unidades — Balanza de utilidad/pérdida por unidad'),
```
Junto a `UNIDADES_KILOMETRAJE`, bajo el módulo `UNIDADES` (ya existe en `MODULO_CHOICES`, sin cambios ahí).

Esto genera una migración (`AlterField` sobre `tipo_reporte`, puramente de metadata de `choices`, sin `RunPython`), siguiendo el mismo patrón que las migraciones previas de este campo (`0005`, `0006`).

---

## 3. Nuevo generador — `modulos/reportes/generadores/unidades.py`

```python
def generar_balanza_utilidad(periodo_inicio: date, periodo_fin: date) -> dict:
    from modulos.unidades.services import calcular_reporte_utilidad

    resultado = calcular_reporte_utilidad(periodo_inicio, periodo_fin)

    filas = [
        {
            'unidad': f['unidad'].numero_economico,
            'ingresos': float(f['ingresos']),
            'gasto_combustible': float(f['gasto_combustible']),
            'gasto_taller': float(f['gasto_taller']),
            'gasto_consumibles': float(f['gasto_consumibles']),
            'gasto_total': float(f['gasto_total']),
            'utilidad': float(f['utilidad']),
            'utilidad_pct': round(float(f['utilidad_pct']), 2) if f['utilidad_pct'] is not None else None,
        }
        for f in resultado['filas']
    ]

    unidades_en_utilidad = sum(1 for f in resultado['filas'] if f['utilidad'] >= 0)
    unidades_en_perdida = len(resultado['filas']) - unidades_en_utilidad

    # Unidad más rentable / de mayor pérdida, para la narrativa IA (ver sección 4)
    ordenadas = sorted(resultado['filas'], key=lambda f: f['utilidad'])
    mayor_perdida = ordenadas[0] if ordenadas else None
    mas_rentable = ordenadas[-1] if ordenadas else None

    return {
        'tipo': 'UNIDADES_BALANZA_UTILIDAD',
        'titulo': f'Balanza de Utilidad por Unidad — {periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_unidades': len(filas),
            'unidades_en_utilidad': unidades_en_utilidad,
            'unidades_en_perdida': unidades_en_perdida,
            'ingresos_totales': float(resultado['totales']['ingresos']),
            'gasto_total': float(resultado['totales']['gasto_total']),
            'utilidad_total': float(resultado['totales']['utilidad']),
            'bitacoras_excluidas': resultado['bitacoras_excluidas'],
            'cargas_excluidas': resultado['cargas_excluidas'],
        },
        'filas': filas,
        # Datos auxiliares para la narrativa IA (no van al Excel, _generar_excel solo lee 'filas'/'tablas'/'resumen')
        'unidad_mas_rentable': mas_rentable,
        'unidad_mayor_perdida': mayor_perdida,
    }


GENERADORES = {
    'UNIDADES_KILOMETRAJE': generar_kilometraje_unidades,
    'UNIDADES_BALANZA_UTILIDAD': generar_balanza_utilidad,
}
```

No requiere cambios en `generar_reportes.py`: el diccionario `GENERADORES` de `unidades.py` ya se combina automáticamente vía `**gen_unidades.GENERADORES` en el comando.

---

## 4. Narrativa IA especializada — `modulos/reportes/generadores/narrativa.py`

Se agrega `_prompt_unidades_balanza_utilidad(resumen, datos, periodo_inicio, periodo_fin)`, siguiendo el patrón de `_prompt_almacen_analisis_integral`:

- Menciona primero la unidad con mayor pérdida y la más rentable (con sus montos).
- Reporta cuántas unidades están en pérdida vs. en utilidad, y la utilidad total de la flotilla.
- Si `bitacoras_excluidas` o `cargas_excluidas` > 0, lo señala como advertencia de cobertura de datos incompleta (igual que ya se muestra en el admin bajo demanda).
- Se añade la entrada `'UNIDADES_BALANZA_UTILIDAD': _prompt_unidades_balanza_utilidad` al `if/elif` de `generar_narrativa()`, usando `Modelo.SONNET` (por la cantidad de contexto financiero, igual que el análisis integral de almacén) y `max_tokens=500`.
- También se agrega la entrada correspondiente a `_NOMBRES_REPORTE` (usada como fallback si la narrativa especializada llegara a fallar y cayera al prompt genérico — no debería ocurrir, pero mantiene consistencia con el resto del archivo).

---

## 5. Excel y envío

Sin cambios: `_generar_excel()` en `generar_reportes.py` ya construye una hoja a partir de `datos['filas']` (lista de dicts homogénea) más una hoja "Resumen" a partir de `datos['resumen']` — funciona tal cual con la forma de datos de este nuevo generador. El envío por correo/WhatsApp (`_enviar_email`, `_enviar_whatsapp_reporte`) es genérico y no requiere cambios.

---

## 6. Activación (fuera de este cambio de código)

El usuario crea, desde el admin de `Configuración de Reporte`, dos registros:
- **Semanal**: `modulo=UNIDADES`, `tipo_reporte=UNIDADES_BALANZA_UTILIDAD`, `frecuencia=SEMANAL`, `dia_semana` a elección, `destinatarios` propios.
- **Mensual**: igual pero `frecuencia=MENSUAL`, `dia_mes` a elección.

No es parte del código de esta implementación — es configuración de datos que el usuario controla desde el admin cuando esté listo para activar el envío.

---

## 7. Migraciones y archivos a crear/modificar

| Archivo | Cambio |
|---|---|
| `modulos/unidades/services.py` | Nuevo. `calcular_reporte_utilidad` + `_suma_cantidad_por_costo` (movidos desde `admin.py`, sin cambios de comportamiento) |
| `modulos/unidades/admin.py` | Elimina las definiciones locales, importa desde `.services` |
| `modulos/unidades/tests.py` | Actualiza el import de `CalcularReporteUtilidadTests` a `from .services import calcular_reporte_utilidad` |
| `modulos/reportes/models.py` | Nueva opción en `TIPO_CHOICES` |
| `modulos/reportes/migrations/` | Nueva migración `AlterField` (metadata de choices) |
| `modulos/reportes/generadores/unidades.py` | Nueva función `generar_balanza_utilidad` + entrada en `GENERADORES` |
| `modulos/reportes/generadores/narrativa.py` | Nuevo prompt especializado + entrada en el dispatch + `_NOMBRES_REPORTE` |
| `modulos/reportes/tests.py` | Tests del nuevo generador (mapeo de filas/resumen, conteo verde/rojo, unidad más rentable/mayor pérdida) y de que el prompt especializado incluye los datos clave |

Ningún registro existente se modifica, borra ni regenera.

---

## 8. Lo que NO incluye este diseño

- Crear las `ConfiguracionReporte` (semanal/mensual) con destinatarios reales — el usuario las crea desde el admin cuando quiera activar el envío.
- Cambios a `_periodo()`, al comando `generar_reportes`, a las plantillas de email/WhatsApp, ni al export a Excel — todos ya son genéricos y funcionan sin modificación.
- Reporte con más de una hoja de Excel (`tablas`, como `ALMACEN_ANALISIS_INTEGRAL`) — una sola hoja de filas por unidad es suficiente para esta balanza.
- Frecuencia DIARIO para este reporte — no tiene sentido operativo para un indicador de utilidad; el usuario puede configurarla igual si lo desea, pero no se documenta como caso de uso previsto.
- Bloque HTML dedicado en `templates/reportes/email/reporte_base.html` para `UNIDADES_BALANZA_UTILIDAD` — el correo usará el bloque genérico (`{% else %}` del `if/elif` por `datos.tipo`), que ya lista el resumen de forma tabular. El detalle por unidad llega vía el adjunto Excel y el análisis vía la narrativa IA.
