# Reporte Programado de Balanza de Utilidad por Unidad — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrar el cálculo de utilidad/pérdida por unidad al sistema de reportes programados (`modulos/reportes`) para que se pueda enviar semanal o mensualmente por correo, con narrativa IA especializada y adjunto Excel.

**Architecture:** Se mueve la función de cálculo ya existente (`calcular_reporte_utilidad`, hoy en `modulos/unidades/admin.py`) a un módulo de servicio neutral (`modulos/unidades/services.py`) para que tanto el admin como el nuevo generador de reportes la reutilicen sin acoplarse entre sí. Se agrega un nuevo `tipo_reporte` (`UNIDADES_BALANZA_UTILIDAD`) con su generador en `modulos/reportes/generadores/unidades.py` y un prompt de narrativa IA dedicado en `narrativa.py`. La infraestructura de envío (email, WhatsApp, Excel, frecuencia semanal/mensual) ya existe y no se modifica.

**Tech Stack:** Django 5.2.7, Python 3.14, `django.test.TestCase` (TDD), SQLite en memoria para tests (usar `DBURL="sqlite:///:memory:"` al correr `manage.py test` para no tocar la base de datos real de producción).

## Global Constraints

- Todo el código, comentarios y verbose_names en español (proyecto en `es-mx`).
- TDD estricto: escribir el test, verlo fallar, implementar lo mínimo, verlo pasar, commitear.
- Ningún registro existente se modifica, borra ni regenera — todos los cambios son aditivos.
- Ejecutar los tests con `DBURL="sqlite:///:memory:" python manage.py test <app>` (el `.env` del proyecto apunta a un PostgreSQL remoto compartido; nunca correr `manage.py test` sin ese override).
- Commits: usar `git add <archivos específicos>` (nunca `git add -A`), un commit por paso marcado "Commit" en el plan.

---

### Task 1: Mover `calcular_reporte_utilidad` a `modulos/unidades/services.py`

Refactor puro (sin cambio de comportamiento): la función y su helper ya están cubiertos por 8 tests existentes en `modulos/unidades/tests.py`. El objetivo de este task es reubicarlos para que `modulos/reportes/generadores/unidades.py` (Task 3) pueda importarlos sin depender de `admin.py`.

**Files:**
- Create: `modulos/unidades/services.py`
- Modify: `modulos/unidades/admin.py` (eliminar las definiciones movidas, importar desde `.services`)
- Modify: `modulos/unidades/tests.py:17` (actualizar el import)

**Interfaces:**
- Produces: `modulos.unidades.services.calcular_reporte_utilidad(desde: date, hasta: date) -> dict` con la forma `{'filas': [...], 'totales': {...}, 'bitacoras_excluidas': int, 'cargas_excluidas': int}` (idéntica a la actual, ver Task 3 para el consumidor).

- [ ] **Step 1: Confirmar que los 8 tests existentes pasan antes de tocar nada (baseline)**

Run: `cd /home/tony/Developer/BitacoraKasu && source .venvKasu/bin/activate && DBURL="sqlite:///:memory:" python manage.py test modulos.unidades.tests.CalcularReporteUtilidadTests -v 2`
Expected: `OK` (8 tests, todos en verde). Si algo falla aquí, detente — no es parte de este refactor arreglarlo.

- [ ] **Step 2: Crear `modulos/unidades/services.py` con el código movido tal cual**

```python
from decimal import Decimal

from django.db.models import Sum

from .models import Unidad


def _suma_cantidad_por_costo(queryset):
    """Suma cantidad * producto.costo_unitario sobre un queryset de salidas de almacén."""
    total = Decimal('0')
    for item in queryset.select_related('producto'):
        total += item.cantidad * item.producto.costo_unitario
    return total


def calcular_reporte_utilidad(desde, hasta):
    """
    Calcula ingreso, gasto y utilidad por unidad activa en el rango [desde, hasta].

    Gasto = combustible (CargaCombustible.costo_calculado) + taller (OrdenTrabajo.costo_total_real)
    + consumibles de almacén (SalidaRapidaConsumible + AsignacionDirectaAlmacen +
    ItemAsignacionSalida con tipo_destino='UNIDAD'). Las piezas de taller vía SalidaAlmacen
    ligada a OrdenTrabajo no se incluyen aquí para no duplicar el gasto ya contado en
    OrdenTrabajo.costo_total_real.
    """
    from modulos.almacen.models import (
        SalidaRapidaConsumible, AsignacionDirectaAlmacen, ItemAsignacionSalida,
    )
    from modulos.bitacoras.models import BitacoraViaje
    from modulos.combustible.models import CargaCombustible
    from modulos.taller.models import OrdenTrabajo

    filas = []
    for unidad in Unidad.objects.filter(activa=True).order_by('numero_economico'):
        ingresos = BitacoraViaje.objects.filter(
            unidad=unidad, completado=True,
            fecha_llegada__date__gte=desde, fecha_llegada__date__lte=hasta,
        ).aggregate(t=Sum('ingreso_calculado'))['t'] or Decimal('0')

        gasto_combustible = CargaCombustible.objects.filter(
            unidad=unidad, estado='COMPLETADO',
            fecha_hora_inicio__date__gte=desde, fecha_hora_inicio__date__lte=hasta,
        ).aggregate(t=Sum('costo_calculado'))['t'] or Decimal('0')

        ordenes_completadas = OrdenTrabajo.objects.filter(
            unidad=unidad, estado='COMPLETADA',
            fecha_finalizacion__date__gte=desde, fecha_finalizacion__date__lte=hasta,
        )
        gasto_taller = sum((orden.costo_total_real for orden in ordenes_completadas), Decimal('0'))

        gasto_consumibles = (
            _suma_cantidad_por_costo(SalidaRapidaConsumible.objects.filter(
                unidad=unidad, fecha_salida__date__gte=desde, fecha_salida__date__lte=hasta,
            ))
            + _suma_cantidad_por_costo(AsignacionDirectaAlmacen.objects.filter(
                unidad=unidad, fecha_asignacion__date__gte=desde, fecha_asignacion__date__lte=hasta,
            ))
            + _suma_cantidad_por_costo(ItemAsignacionSalida.objects.filter(
                asignacion__tipo_destino='UNIDAD', asignacion__unidad=unidad,
                asignacion__fecha__gte=desde, asignacion__fecha__lte=hasta,
            ))
        )

        gasto_total = gasto_combustible + gasto_taller + gasto_consumibles
        utilidad = ingresos - gasto_total
        utilidad_pct = (utilidad / ingresos * 100) if ingresos else None

        filas.append({
            'unidad': unidad,
            'ingresos': ingresos,
            'gasto_combustible': gasto_combustible,
            'gasto_taller': gasto_taller,
            'gasto_consumibles': gasto_consumibles,
            'gasto_total': gasto_total,
            'utilidad': utilidad,
            'utilidad_pct': utilidad_pct,
        })

    totales = {
        clave: sum((f[clave] for f in filas), Decimal('0'))
        for clave in ('ingresos', 'gasto_combustible', 'gasto_taller', 'gasto_consumibles', 'gasto_total', 'utilidad')
    }

    bitacoras_excluidas = BitacoraViaje.objects.filter(
        completado=True, fecha_llegada__date__gte=desde, fecha_llegada__date__lte=hasta,
        ingreso_calculado__isnull=True,
    ).count()
    cargas_excluidas = CargaCombustible.objects.filter(
        estado='COMPLETADO', fecha_hora_inicio__date__gte=desde, fecha_hora_inicio__date__lte=hasta,
        costo_calculado__isnull=True,
    ).count()

    return {
        'filas': filas,
        'totales': totales,
        'bitacoras_excluidas': bitacoras_excluidas,
        'cargas_excluidas': cargas_excluidas,
    }
```

- [ ] **Step 3: Editar `modulos/unidades/admin.py` — quitar las definiciones movidas e importar desde `.services`**

En `modulos/unidades/admin.py`, reemplazar el bloque completo desde `def _suma_cantidad_por_costo(queryset):` (línea 19) hasta el `return {...}` final de `calcular_reporte_utilidad` (línea 109, justo antes de `@admin.register(Unidad)`) por una sola línea de import. El encabezado del archivo pasa de:

```python
from datetime import date, timedelta

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.shortcuts import render
from django.contrib import messages
from django.urls import path
from django.db.models import Sum
from django.http import HttpResponse
from decimal import Decimal, InvalidOperation

import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

from .models import Unidad


def _suma_cantidad_por_costo(queryset):
    ...  # (todo el cuerpo movido)


def calcular_reporte_utilidad(desde, hasta):
    ...  # (todo el cuerpo movido)


@admin.register(Unidad)
```

a:

```python
from datetime import date, timedelta

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.shortcuts import render
from django.contrib import messages
from django.urls import path
from django.http import HttpResponse
from decimal import Decimal, InvalidOperation

import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

from .models import Unidad
from .services import calcular_reporte_utilidad


@admin.register(Unidad)
```

Nota: se quita `from django.db.models import Sum` porque ya no se usa en `admin.py` (solo lo usaba `calcular_reporte_utilidad`, ahora en `services.py`). El resto del archivo (`UnidadAdmin`, sus vistas `reporte_utilidad_view` y `exportar_excel_reporte_utilidad_view`) no cambia — siguen llamando a `calcular_reporte_utilidad(desde, hasta)` exactamente igual, solo que ahora resuelve al import.

- [ ] **Step 4: Editar `modulos/unidades/tests.py:17` — actualizar el import**

Cambiar:
```python
from .admin import calcular_reporte_utilidad
```
por:
```python
from .services import calcular_reporte_utilidad
```

- [ ] **Step 5: Correr los tests para confirmar que el refactor no rompió nada**

Run: `DBURL="sqlite:///:memory:" python manage.py test modulos.unidades -v 2`
Expected: `OK` (8 tests, todos en verde, mismos nombres que antes).

- [ ] **Step 6: Correr `manage.py check` para confirmar que el admin sigue cargando bien**

Run: `DBURL="sqlite:///:memory:" python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 7: Commit**

```bash
git add modulos/unidades/services.py modulos/unidades/admin.py modulos/unidades/tests.py
git commit -m "$(cat <<'EOF'
Mueve calcular_reporte_utilidad a modulos/unidades/services.py

Refactor sin cambio de comportamiento: separa la lógica de cálculo de
admin.py para que el generador de reportes programados (siguiente tarea)
la reutilice sin depender del módulo de admin.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Agregar el tipo de reporte `UNIDADES_BALANZA_UTILIDAD`

**Files:**
- Modify: `modulos/reportes/models.py:29` (agregar entrada en `TIPO_CHOICES`)
- Create: `modulos/reportes/migrations/0007_alter_configuracionreporte_tipo_reporte.py` (generada por `makemigrations`, no escrita a mano)

**Interfaces:**
- Produces: el valor de choice `'UNIDADES_BALANZA_UTILIDAD'` válido en `ConfiguracionReporte.tipo_reporte`, consumido por el generador (Task 3) y por la narrativa (Task 4).

- [ ] **Step 1: Editar `modulos/reportes/models.py`**

En la lista `TIPO_CHOICES` (línea 17), justo después de la línea:
```python
        ('UNIDADES_KILOMETRAJE', 'Unidades — Kilometraje de flota'),
```
agregar:
```python
        ('UNIDADES_BALANZA_UTILIDAD', 'Unidades — Balanza de utilidad/pérdida por unidad'),
```

Así el bloque de "Unidades" queda:
```python
        # Unidades
        ('UNIDADES_KILOMETRAJE', 'Unidades — Kilometraje de flota'),
        ('UNIDADES_BALANZA_UTILIDAD', 'Unidades — Balanza de utilidad/pérdida por unidad'),
```

- [ ] **Step 2: Generar la migración**

Run: `DBURL="sqlite:///:memory:" python manage.py makemigrations reportes`
Expected:
```
Migrations for 'reportes':
  modulos/reportes/migrations/0007_alter_configuracionreporte_tipo_reporte.py
    ~ Alter field tipo_reporte on configuracionreporte
```

- [ ] **Step 3: Verificar que no falten más migraciones pendientes en la app `reportes`**

Run: `DBURL="sqlite:///:memory:" python manage.py makemigrations reportes --check --dry-run`
Expected: sin salida (exit code 0) — ya no hay cambios pendientes de detectar en esta app.

- [ ] **Step 4: Commit**

```bash
git add modulos/reportes/models.py modulos/reportes/migrations/0007_alter_configuracionreporte_tipo_reporte.py
git commit -m "$(cat <<'EOF'
Agrega tipo de reporte UNIDADES_BALANZA_UTILIDAD

Habilita el nuevo tipo en el catálogo de ConfiguracionReporte; el
generador y la narrativa se agregan en las siguientes tareas.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Generador `generar_balanza_utilidad` (TDD)

**Files:**
- Modify: `modulos/reportes/generadores/unidades.py` (agregar función + entrada en `GENERADORES`)
- Modify: `modulos/reportes/tests.py` (agregar tests, agregar import al encabezado)

**Interfaces:**
- Consumes: `modulos.unidades.services.calcular_reporte_utilidad(desde, hasta) -> dict` (Task 1).
- Produces: `modulos.reportes.generadores.unidades.generar_balanza_utilidad(periodo_inicio: date, periodo_fin: date) -> dict` con las claves `tipo`, `titulo`, `periodo_inicio`, `periodo_fin`, `generado_en`, `resumen` (dict con `total_unidades`, `unidades_en_utilidad`, `unidades_en_perdida`, `ingresos_totales`, `gasto_total`, `utilidad_total`, `bitacoras_excluidas`, `cargas_excluidas`), `filas` (lista de dicts con `unidad`, `ingresos`, `gasto_combustible`, `gasto_taller`, `gasto_consumibles`, `gasto_total`, `utilidad`, `utilidad_pct` — todos como `float`, no `Decimal`, porque el resto del sistema de reportes serializa a JSON/Excel con floats), `unidad_mas_rentable` y `unidad_mayor_perdida` (cada uno un dict de `filas` o `None` si no hay unidades). Se agrega la entrada `'UNIDADES_BALANZA_UTILIDAD': generar_balanza_utilidad` al diccionario `GENERADORES` del archivo — el comando `generar_reportes` ya lo recoge automáticamente vía `**gen_unidades.GENERADORES`.

- [ ] **Step 1: Escribir los tests que fallan en `modulos/reportes/tests.py`**

Agregar al encabezado del archivo (junto a los demás imports de generadores):
```python
from modulos.reportes.generadores.unidades import generar_balanza_utilidad
```

Agregar también, junto a los imports ya existentes de modelos, los necesarios para armar los fixtures (si no están ya importados en el archivo, revisar antes de duplicar):
```python
from modulos.bitacoras.models import BitacoraViaje
from modulos.combustible.models import Despachador, CargaCombustible
from modulos.finanzas.models import TarifaKilometro
from modulos.operadores.models import Operador
```

Agregar al final del archivo la nueva clase de tests:

```python
class GenerarBalanzaUtilidadTests(TestCase):
    def setUp(self):
        self.unidad_rentable = Unidad.objects.create(
            numero_economico='ECO-R', placa='RRR-111', tipo='LOCAL', año=2020,
            capacidad_combustible=Decimal('200.00'), rendimiento_esperado=Decimal('3.00'),
        )
        self.unidad_perdida = Unidad.objects.create(
            numero_economico='ECO-P', placa='PPP-222', tipo='LOCAL', año=2020,
            capacidad_combustible=Decimal('200.00'), rendimiento_esperado=Decimal('3.00'),
        )
        self.operador = Operador.objects.create(nombre='Juan Pérez', tipo='LOCAL')
        self.despachador = Despachador.objects.create(nombre='Pedro López')

        aware = lambda y, m, d, h=8: timezone.make_aware(timezone.datetime(y, m, d, h))

        # Unidad rentable: ingreso alto, gasto bajo
        BitacoraViaje.objects.create(
            operador=self.operador, unidad=self.unidad_rentable, modalidad='LOCAL',
            fecha_carga=aware(2026, 6, 1), fecha_salida=aware(2026, 6, 1),
            fecha_llegada=aware(2026, 6, 2), destino='Destino rentable',
            ingreso_calculado=Decimal('5000.00'),
        )
        CargaCombustible.objects.create(
            despachador=self.despachador, unidad=self.unidad_rentable, cantidad_litros=Decimal('50.00'),
            kilometraje_actual=1000, nivel_combustible_inicial='MEDIO', estado_candado_anterior='NORMAL',
            fecha_hora_inicio=aware(2026, 6, 3), tipo_flujo='LOCAL', estado='COMPLETADO',
            costo_calculado=Decimal('500.00'),
        )

        # Unidad en pérdida: sin ingreso, solo gasto
        CargaCombustible.objects.create(
            despachador=self.despachador, unidad=self.unidad_perdida, cantidad_litros=Decimal('200.00'),
            kilometraje_actual=1000, nivel_combustible_inicial='MEDIO', estado_candado_anterior='NORMAL',
            fecha_hora_inicio=aware(2026, 6, 4), tipo_flujo='LOCAL', estado='COMPLETADO',
            costo_calculado=Decimal('3000.00'),
        )

        self.periodo_inicio = date(2026, 6, 1)
        self.periodo_fin = date(2026, 6, 30)

    def test_resumen_cuenta_unidades_en_utilidad_y_perdida(self):
        datos = generar_balanza_utilidad(self.periodo_inicio, self.periodo_fin)
        self.assertEqual(datos['resumen']['total_unidades'], 2)
        self.assertEqual(datos['resumen']['unidades_en_utilidad'], 1)
        self.assertEqual(datos['resumen']['unidades_en_perdida'], 1)

    def test_resumen_incluye_totales_e_indicadores_de_cobertura(self):
        datos = generar_balanza_utilidad(self.periodo_inicio, self.periodo_fin)
        resumen = datos['resumen']
        self.assertEqual(resumen['ingresos_totales'], 5000.0)
        self.assertEqual(resumen['gasto_total'], 3500.0)
        self.assertEqual(resumen['utilidad_total'], 1500.0)
        self.assertIn('bitacoras_excluidas', resumen)
        self.assertIn('cargas_excluidas', resumen)

    def test_filas_usa_numero_economico_y_valores_float(self):
        datos = generar_balanza_utilidad(self.periodo_inicio, self.periodo_fin)
        fila_rentable = next(f for f in datos['filas'] if f['unidad'] == 'ECO-R')
        self.assertEqual(fila_rentable['ingresos'], 5000.0)
        self.assertIsInstance(fila_rentable['ingresos'], float)
        self.assertEqual(fila_rentable['utilidad'], 4500.0)

    def test_identifica_unidad_mas_rentable_y_de_mayor_perdida(self):
        datos = generar_balanza_utilidad(self.periodo_inicio, self.periodo_fin)
        self.assertEqual(datos['unidad_mas_rentable']['unidad'], 'ECO-R')
        self.assertEqual(datos['unidad_mayor_perdida']['unidad'], 'ECO-P')

    def test_tipo_y_titulo_correctos(self):
        datos = generar_balanza_utilidad(self.periodo_inicio, self.periodo_fin)
        self.assertEqual(datos['tipo'], 'UNIDADES_BALANZA_UTILIDAD')
        self.assertIn('Balanza de Utilidad', datos['titulo'])

    def test_sin_unidades_activas_no_lanza_error(self):
        Unidad.objects.all().update(activa=False)
        datos = generar_balanza_utilidad(self.periodo_inicio, self.periodo_fin)
        self.assertEqual(datos['filas'], [])
        self.assertIsNone(datos['unidad_mas_rentable'])
        self.assertIsNone(datos['unidad_mayor_perdida'])
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `DBURL="sqlite:///:memory:" python manage.py test modulos.reportes.tests.GenerarBalanzaUtilidadTests -v 2`
Expected: `ImportError: cannot import name 'generar_balanza_utilidad' from 'modulos.reportes.generadores.unidades'` (o `ERROR` en cada test por el mismo motivo). Confirma que falla por falta de la función, no por un typo.

- [ ] **Step 3: Implementar `generar_balanza_utilidad` en `modulos/reportes/generadores/unidades.py`**

El archivo completo queda así (se agrega la función nueva y se actualiza `GENERADORES`; `generar_kilometraje_unidades` no cambia):

```python
"""Generadores de datos para reportes del módulo Unidades."""

from datetime import date
from django.utils import timezone


def generar_kilometraje_unidades(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de kilometraje actual de todas las unidades activas.

    Es un snapshot del estado actual (no depende del período), pero acepta
    los parámetros de período para mantener la firma estándar del sistema.
    """
    from modulos.unidades.models import Unidad

    unidades = (
        Unidad.objects
        .filter(activa=True)
        .order_by('-kilometraje_actual')
        .values('numero_economico', 'placa', 'marca', 'modelo', 'kilometraje_actual', 'tipo')
    )

    filas = []
    total_km = 0
    for u in unidades:
        total_km += u['kilometraje_actual'] or 0
        filas.append({
            'numero_economico': u['numero_economico'],
            'placa': u['placa'] or '—',
            'marca': u['marca'] or '—',
            'modelo': u['modelo'] or '—',
            'kilometraje_km': u['kilometraje_actual'] or 0,
            'tipo': u['tipo'],
        })

    total = len(filas)
    km_promedio = round(total_km / total) if total else 0
    km_maximo = filas[0]['kilometraje_km'] if filas else 0
    unidad_max = filas[0]['numero_economico'] if filas else '—'

    return {
        'tipo': 'UNIDADES_KILOMETRAJE',
        'titulo': 'Kilometraje de Flota',
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_unidades': total,
            'km_promedio': km_promedio,
            'km_maximo': km_maximo,
            'unidad_mayor_km': unidad_max,
        },
        'filas': filas,
    }


def generar_balanza_utilidad(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte de utilidad/pérdida por unidad en el período (ingresos vs. gastos).

    Reutiliza el mismo cálculo que la vista bajo demanda del admin de Unidad
    (modulos.unidades.services.calcular_reporte_utilidad).
    """
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

    unidades_en_utilidad = sum(1 for f in filas if f['utilidad'] >= 0)
    unidades_en_perdida = len(filas) - unidades_en_utilidad

    ordenadas = sorted(filas, key=lambda f: f['utilidad'])
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
        'unidad_mas_rentable': mas_rentable,
        'unidad_mayor_perdida': mayor_perdida,
    }


# Mapa tipo_reporte → función generadora
GENERADORES = {
    'UNIDADES_KILOMETRAJE': generar_kilometraje_unidades,
    'UNIDADES_BALANZA_UTILIDAD': generar_balanza_utilidad,
}
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `DBURL="sqlite:///:memory:" python manage.py test modulos.reportes.tests.GenerarBalanzaUtilidadTests -v 2`
Expected: `OK` (6 tests en verde).

- [ ] **Step 5: Correr toda la suite de `reportes` para confirmar que no se rompió nada existente**

Run: `DBURL="sqlite:///:memory:" python manage.py test modulos.reportes -v 2`
Expected: mismo resultado que antes de este task (los 4 fallos preexistentes de `GenerarAnalisisIntegralAlmacenTests`, si siguen sin resolverse, no deben aumentar; ningún test nuevo debe fallar).

- [ ] **Step 6: Commit**

```bash
git add modulos/reportes/generadores/unidades.py modulos/reportes/tests.py
git commit -m "$(cat <<'EOF'
Agrega generador de reporte de balanza de utilidad por unidad

generar_balanza_utilidad() reutiliza calcular_reporte_utilidad() y arma
el formato estándar de datos para el sistema de reportes programados
(resumen, filas, unidad más rentable / de mayor pérdida).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Narrativa IA especializada (TDD)

**Files:**
- Modify: `modulos/reportes/generadores/narrativa.py`
- Modify: `modulos/reportes/tests.py`

**Interfaces:**
- Consumes: el `resumen` y `datos` producidos por `generar_balanza_utilidad` (Task 3) — en particular `datos['unidad_mas_rentable']` y `datos['unidad_mayor_perdida']`.
- Produces: `modulos.reportes.generadores.narrativa._prompt_unidades_balanza_utilidad(resumen: dict, datos: dict, periodo_inicio: str, periodo_fin: str) -> tuple[str, int]` (prompt, max_tokens), enganchado en `generar_narrativa()` bajo `tipo_reporte == 'UNIDADES_BALANZA_UTILIDAD'`.

- [ ] **Step 1: Escribir el test que falla en `modulos/reportes/tests.py`**

Agregar al final del archivo:

```python
class PromptBalanzaUtilidadTests(TestCase):
    def test_prompt_incluye_unidades_extremas_y_totales(self):
        from modulos.reportes.generadores.narrativa import _prompt_unidades_balanza_utilidad

        resumen = {
            'total_unidades': 2, 'unidades_en_utilidad': 1, 'unidades_en_perdida': 1,
            'ingresos_totales': 5000.0, 'gasto_total': 3500.0, 'utilidad_total': 1500.0,
            'bitacoras_excluidas': 3, 'cargas_excluidas': 1,
        }
        datos = {
            'unidad_mas_rentable': {'unidad': 'ECO-R', 'utilidad': 4500.0},
            'unidad_mayor_perdida': {'unidad': 'ECO-P', 'utilidad': -3000.0},
        }
        prompt, max_tokens = _prompt_unidades_balanza_utilidad(
            resumen, datos, '2026-06-01', '2026-06-30'
        )
        self.assertIn('ECO-R', prompt)
        self.assertIn('ECO-P', prompt)
        self.assertIn('1500.0', prompt)
        self.assertIn('3', prompt)  # bitácoras excluidas mencionadas
        self.assertEqual(max_tokens, 500)

    def test_generar_narrativa_despacha_al_prompt_especializado(self):
        from unittest.mock import patch
        from modulos.reportes.generadores.narrativa import generar_narrativa

        resumen = {'total_unidades': 0, 'unidades_en_utilidad': 0, 'unidades_en_perdida': 0}
        datos = {'unidad_mas_rentable': None, 'unidad_mayor_perdida': None}

        with patch('modulos.reportes.generadores.narrativa.settings.IA_HABILITADA', True), \
             patch('config.services.claude_service.ClaudeService') as MockClaude:
            instancia = MockClaude.return_value
            instancia.completar.return_value = 'Narrativa de prueba'

            resultado = generar_narrativa(
                tipo_reporte='UNIDADES_BALANZA_UTILIDAD', resumen=resumen,
                periodo_inicio='2026-06-01', periodo_fin='2026-06-30', datos=datos,
            )

        self.assertEqual(resultado, 'Narrativa de prueba')
        args, kwargs = instancia.completar.call_args
        self.assertIn('Balanza', kwargs['prompt'] if 'prompt' in kwargs else args[0])
```

Nota sobre el segundo test: revisa la firma real de `claude.completar()` en `config/services/claude_service.py` antes de escribir la aserción final — `generar_narrativa()` la llama como `claude.completar(prompt=prompt, sistema=SISTEMA_NARRATIVA, modelo=modelo, max_tokens=max_tokens)`, así que `kwargs['prompt']` es la forma correcta (ya reflejada arriba).

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `DBURL="sqlite:///:memory:" python manage.py test modulos.reportes.tests.PromptBalanzaUtilidadTests -v 2`
Expected: el primer test falla con `ImportError: cannot import name '_prompt_unidades_balanza_utilidad'`; el segundo falla porque `generar_narrativa` cae al prompt genérico (el mock de `completar` se llama, pero el prompt no contendrá "Balanza" en el formato específico — o falla porque el dispatch no existe todavía). Confirma que el mensaje de fallo corresponde a "falta implementar", no a un error de sintaxis en el test.

- [ ] **Step 3: Implementar en `modulos/reportes/generadores/narrativa.py`**

Agregar a `_NOMBRES_REPORTE` (después de la línea `'UNIDADES_KILOMETRAJE': ...`):
```python
    'UNIDADES_BALANZA_UTILIDAD': 'Balanza de utilidad/pérdida por unidad',
```

Agregar la función nueva, después de `_prompt_almacen_analisis_integral` y antes de `def generar_narrativa(...)`:

```python
def _prompt_unidades_balanza_utilidad(resumen: dict, datos: dict, periodo_inicio: str, periodo_fin: str) -> tuple:
    """Prompt especializado para el reporte de balanza de utilidad por unidad."""
    total = resumen.get('total_unidades', 0)
    en_utilidad = resumen.get('unidades_en_utilidad', 0)
    en_perdida = resumen.get('unidades_en_perdida', 0)
    ingresos_totales = resumen.get('ingresos_totales', 0)
    gasto_total = resumen.get('gasto_total', 0)
    utilidad_total = resumen.get('utilidad_total', 0)
    bitacoras_excluidas = resumen.get('bitacoras_excluidas', 0)
    cargas_excluidas = resumen.get('cargas_excluidas', 0)

    mas_rentable = datos.get('unidad_mas_rentable')
    mayor_perdida = datos.get('unidad_mayor_perdida')

    rentable_texto = (
        f"  {mas_rentable['unidad']} — utilidad de ${mas_rentable['utilidad']:,.2f} MXN"
        if mas_rentable else '  Sin datos'
    )
    perdida_texto = (
        f"  {mayor_perdida['unidad']} — utilidad de ${mayor_perdida['utilidad']:,.2f} MXN"
        if mayor_perdida else '  Sin datos'
    )

    cobertura_texto = ''
    if bitacoras_excluidas or cargas_excluidas:
        cobertura_texto = (
            f"\nAdvertencia de cobertura de datos: {bitacoras_excluidas} bitácora(s) sin tarifa vigente "
            f"y {cargas_excluidas} carga(s) de combustible sin precio de diésel vigente quedaron fuera "
            f"de este cálculo (no se contabilizó su ingreso/costo).\n"
        )

    prompt = (
        f"Reporte: Balanza de Utilidad por Unidad\n"
        f"Período: {periodo_inicio} al {periodo_fin}\n\n"
        f"Resumen de flotilla:\n"
        f"  - Total de unidades: {total} | En utilidad: {en_utilidad} | En pérdida: {en_perdida}\n"
        f"  - Ingresos totales: ${ingresos_totales:,.2f} MXN\n"
        f"  - Gasto total: ${gasto_total:,.2f} MXN\n"
        f"  - Utilidad total de la flotilla: ${utilidad_total:,.2f} MXN\n\n"
        f"Unidad más rentable del período:\n{rentable_texto}\n\n"
        f"Unidad con mayor pérdida del período:\n{perdida_texto}\n"
        f"{cobertura_texto}\n"
        f"Redacta el análisis ejecutivo. Menciona primero la unidad con mayor pérdida y la más "
        f"rentable con sus montos, señala si la advertencia de cobertura de datos (si existe) "
        f"limita la confiabilidad del resultado, y concluye con una valoración general de la "
        f"salud financiera de la flotilla en el período:"
    )
    return prompt, 500
```

Editar el `if/elif` de `generar_narrativa()` para agregar la nueva rama, justo después del bloque `elif tipo_reporte == 'ALMACEN_ANALISIS_INTEGRAL':`:

```python
    elif tipo_reporte == 'ALMACEN_ANALISIS_INTEGRAL':
        prompt, max_tokens = _prompt_almacen_analisis_integral(
            resumen, datos or {}, periodo_inicio, periodo_fin
        )
        modelo = Modelo.SONNET
    elif tipo_reporte == 'UNIDADES_BALANZA_UTILIDAD':
        prompt, max_tokens = _prompt_unidades_balanza_utilidad(
            resumen, datos or {}, periodo_inicio, periodo_fin
        )
        modelo = Modelo.SONNET
    else:
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `DBURL="sqlite:///:memory:" python manage.py test modulos.reportes.tests.PromptBalanzaUtilidadTests -v 2`
Expected: `OK` (2 tests en verde). Si el segundo test falla por un mock mal formado (nombre de módulo distinto en `patch()`), revisa el import real de `ClaudeService` dentro de `generar_narrativa()` (`from config.services.claude_service import ClaudeService, Modelo`) y ajusta la ruta del `patch()` para que coincida exactamente con esa ruta de import.

- [ ] **Step 5: Correr toda la suite de `reportes` una vez más**

Run: `DBURL="sqlite:///:memory:" python manage.py test modulos.reportes -v 2`
Expected: todos los tests de este plan en verde; los 4 fallos preexistentes de `GenerarAnalisisIntegralAlmacenTests` (si no se han resuelto aparte) siguen igual, sin tests nuevos rotos.

- [ ] **Step 6: Commit**

```bash
git add modulos/reportes/generadores/narrativa.py modulos/reportes/tests.py
git commit -m "$(cat <<'EOF'
Agrega narrativa IA especializada para la balanza de utilidad por unidad

Prompt dedicado que prioriza la unidad con mayor pérdida y la más
rentable, y advierte sobre bitácoras/cargas excluidas por falta de
tarifa o precio de diésel vigente.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Verificación end-to-end con `generar_reportes --dry-run`

Confirma que todo el pipeline (generador → narrativa → Excel → email) funciona junto, sin enviar correos reales ni tocar la base de datos de producción.

**Files:** ninguno (solo verificación manual, no se escribe código).

- [ ] **Step 1: Correr la suite completa del proyecto una vez más**

Run: `DBURL="sqlite:///:memory:" python manage.py test`
Expected: mismo conteo de éxitos/fallos que al cierre del plan anterior (utilidad por unidad) más los tests nuevos de este plan, todos en verde. Los 4 fallos preexistentes de `modulos.reportes.tests.GenerarAnalisisIntegralAlmacenTests` (no relacionados con este trabajo) pueden seguir apareciendo — no son parte de este plan.

- [ ] **Step 2: Crear una `ConfiguracionReporte` de prueba y correr el comando en `--dry-run` contra la base de datos real**

Esto NO envía correo (flag `--dry-run`) y NO escribe en `ReporteGenerado`, pero sí lee de la base de datos real para confirmar que el generador funciona con datos reales de producción.

Run:
```bash
python manage.py shell -c "
from modulos.reportes.models import ConfiguracionReporte
config, created = ConfiguracionReporte.objects.get_or_create(
    nombre='TEST — Balanza Utilidad (borrar después)',
    defaults={
        'modulo': 'UNIDADES',
        'tipo_reporte': 'UNIDADES_BALANZA_UTILIDAD',
        'frecuencia': 'MENSUAL',
        'destinatarios': 'test@example.com',
        'activo': True,
    },
)
print('Config id:', config.id, 'creado:', created)
"
```
Expected: imprime un `id` numérico.

Run: `python manage.py generar_reportes --forzar-id <ID impreso arriba> --dry-run`
Expected: salida `RUN   TEST — Balanza Utilidad...`, luego `IA    Narrativa generada para TEST — Balanza Utilidad...` (o sin esa línea si `IA_HABILITADA=False`/no hay API key configurada, lo cual es aceptable), y finalmente `OK    TEST — Balanza Utilidad...` con `Ejecutados: 1  Errores: 0`. Si aparece `FAIL`, lee el traceback — casi siempre significa un `KeyError` en el prompt de narrativa o en `_generar_excel` por una clave de `datos` faltante; revisa contra las claves exactas definidas en el Task 3.

- [ ] **Step 3: Borrar la configuración de prueba (no dejar basura en la base de datos real)**

Run:
```bash
python manage.py shell -c "
from modulos.reportes.models import ConfiguracionReporte
ConfiguracionReporte.objects.filter(nombre='TEST — Balanza Utilidad (borrar después)').delete()
print('Borrado.')
"
```
Expected: `Borrado.`

- [ ] **Step 4: No hay commit en este task** (fue solo verificación manual, ningún archivo cambió).

---

## Resumen de archivos tocados

| Archivo | Task |
|---|---|
| `modulos/unidades/services.py` (nuevo) | 1 |
| `modulos/unidades/admin.py` | 1 |
| `modulos/unidades/tests.py` | 1 |
| `modulos/reportes/models.py` | 2 |
| `modulos/reportes/migrations/0007_alter_configuracionreporte_tipo_reporte.py` (nuevo, generado) | 2 |
| `modulos/reportes/generadores/unidades.py` | 3 |
| `modulos/reportes/generadores/narrativa.py` | 4 |
| `modulos/reportes/tests.py` | 3, 4 |

Después de este plan, la activación (crear las `ConfiguracionReporte` reales de SEMANAL y MENSUAL con destinatarios) queda pendiente para cuando el usuario decida activarlas desde el admin — no es parte de este plan (ver spec, sección 6).
