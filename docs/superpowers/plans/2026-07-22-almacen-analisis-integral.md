# Análisis Integral de Almacén — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new scheduled report type, `ALMACEN_ANALISIS_INTEGRAL`, that gives IAKasu (Claude) visibility into three warehouse processes it currently can't see: asignaciones directas (`AsignacionDirectaAlmacen` + `AsignacionSalida`), entradas (`EntradaAlmacen`), and auditoría (`AuditoriaAlmacen`).

**Architecture:** Follows the existing `modulos/reportes` pattern exactly — a data generator function, a specialized narrativa (Claude) prompt, a new email template block, and Excel export — reusing the scheduling/email/WhatsApp infrastructure in `generar_reportes.py` unchanged.

**Tech Stack:** Django 5.2.7, Python 3.14, openpyxl (Excel export), Claude (via `config.services.claude_service.ClaudeService`), SQLite for local test runs.

## Global Constraints

- Spec source: `docs/superpowers/specs/2026-07-22-almacen-analisis-integral-design.md`
- All code, comments, and user-facing strings in Spanish (project convention, `es-mx`)
- Tests **must** be run with `DBURL='sqlite://' python manage.py test modulos.reportes` — the production DigitalOcean PostgreSQL instance has no `postgres` template database and cannot create a Django test database
- No new dependencies — reuse `openpyxl`, already in `requirements.txt`
- Do not call the real Claude API in automated tests — only the prompt-building helper functions are unit-tested; end-to-end narrative generation is verified manually via `--dry-run`
- Follow existing code patterns: explicit named dict keys for report-specific data (not generic wrapper abstractions), same as `top_5_salidas` / `sin_movimiento` in `ALMACEN_MOVIMIENTOS`

---

### Task 1: Generador de datos `generar_analisis_integral`

**Files:**
- Modify: `modulos/reportes/generadores/almacen.py`
- Test: `modulos/reportes/tests.py`

**Interfaces:**
- Consumes: `modulos.almacen.models.AsignacionDirectaAlmacen`, `AsignacionSalida`, `ItemAsignacionSalida`, `EntradaAlmacen`, `AuditoriaAlmacen` (all pre-existing); `AsignacionSalida.destino_display` property; `EntradaAlmacen.costo_total_entrada` / `.total_items` properties.
- Produces: `generar_analisis_integral(periodo_inicio: date, periodo_fin: date) -> dict` with keys `tipo`, `titulo`, `periodo_inicio`, `periodo_fin`, `generado_en`, `resumen` (dict), `asignaciones` (list), `entradas` (list), `auditoria` (list), `top_destinos` (list), `top_usuarios_auditoria` (list), `tablas` (dict of `{nombre_hoja: filas}`). Registered in `GENERADORES['ALMACEN_ANALISIS_INTEGRAL']`. Later tasks (3, 4, 5) consume this exact shape.

- [ ] **Step 1: Write the failing tests**

Append to `modulos/reportes/tests.py`:

```python
from modulos.almacen.models import (
    ProductoAlmacen, AsignacionDirectaAlmacen, AsignacionSalida,
    ItemAsignacionSalida, EntradaAlmacen, AuditoriaAlmacen,
)
from modulos.unidades.models import Unidad
from modulos.reportes.generadores.almacen import generar_analisis_integral
from decimal import Decimal


class GenerarAnalisisIntegralAlmacenTests(TestCase):
    def setUp(self):
        self.hoy = timezone.now().date()

        self.mecanico1 = User.objects.create_user(
            username='mecanico1', first_name='Juan', last_name='Perez', password='12345'
        )
        self.mecanico2 = User.objects.create_user(
            username='mecanico2', first_name='Ana', last_name='Lopez', password='12345'
        )

        self.unidad = Unidad.objects.create(
            numero_economico='U-100', placa='ABC123', tipo='LOCAL', año=2020,
            capacidad_combustible=Decimal('200.00'), rendimiento_esperado=Decimal('3.50'),
        )

        self.producto = ProductoAlmacen.objects.create(
            categoria='Refacciones', sku='FOC-001', descripcion='Foco delantero',
            localidad='Pasillo A1', cantidad=Decimal('50.00'), unidad_medida='Pieza',
            stock_minimo=Decimal('5.00'), costo_unitario=Decimal('80.00'), activo=True,
        )

        AsignacionDirectaAlmacen.objects.create(
            producto=self.producto, unidad=self.unidad, cantidad=Decimal('2.00'),
            motivo='Cambio de foco', entregado_por=self.mecanico1,
            fecha_asignacion=timezone.now(),
        )

        asignacion_salida = AsignacionSalida.objects.create(
            solicitante='Juan Perez', tipo_destino='UNIDAD', unidad=self.unidad,
            justificacion='Reparación urgente', entregado_por=self.mecanico1,
        )
        ItemAsignacionSalida.objects.create(
            asignacion=asignacion_salida, producto=self.producto, cantidad=Decimal('3.00'),
        )

        EntradaAlmacen.objects.create(tipo='FACTURA', recibido_por=self.mecanico2)
        EntradaAlmacen.objects.create(tipo='ENTRADA_DIRECTA', recibido_por=self.mecanico2)

        for _ in range(6):
            AuditoriaAlmacen.objects.create(
                usuario=self.mecanico1, accion='ELIMINAR', modelo='ProductoAlmacen',
                objeto_id='1', objeto_str='Producto de prueba',
            )
        AuditoriaAlmacen.objects.create(
            usuario=self.mecanico2, accion='CREAR', modelo='EntradaAlmacen',
            objeto_id='1', objeto_str='Entrada de prueba',
        )

    def test_resumen_cuenta_asignaciones_y_entradas(self):
        datos = generar_analisis_integral(self.hoy, self.hoy)
        resumen = datos['resumen']
        self.assertEqual(resumen['total_asignaciones_directas'], 1)
        self.assertEqual(resumen['total_asignaciones_salida'], 1)
        self.assertEqual(resumen['total_items_asignados'], 5.0)
        self.assertEqual(resumen['total_entradas'], 2)
        self.assertEqual(resumen['entradas_por_tipo']['Producto Nuevo desde Factura'], 1)
        self.assertEqual(resumen['entradas_por_tipo']['Entrada Directa'], 1)

    def test_top_destinos_incluye_la_unidad(self):
        datos = generar_analisis_integral(self.hoy, self.hoy)
        destinos = {d['destino'] for d in datos['top_destinos']}
        self.assertIn(str(self.unidad), destinos)

    def test_auditoria_detecta_concentracion_y_eliminaciones(self):
        datos = generar_analisis_integral(self.hoy, self.hoy)
        resumen = datos['resumen']
        self.assertEqual(resumen['total_eventos_auditoria'], 7)
        self.assertEqual(resumen['auditoria_por_accion']['Eliminar'], 6)
        self.assertEqual(len(resumen['alertas_auditoria']), 2)
        self.assertIn('Juan Perez', resumen['alertas_auditoria'][0])
        self.assertIn('eliminaciones', resumen['alertas_auditoria'][1].lower())

    def test_tablas_para_excel_incluye_las_tres_secciones(self):
        datos = generar_analisis_integral(self.hoy, self.hoy)
        self.assertEqual(set(datos['tablas'].keys()), {'Asignaciones', 'Entradas', 'Auditoria'})
        self.assertEqual(len(datos['tablas']['Asignaciones']), 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DBURL='sqlite://' python manage.py test modulos.reportes.tests.GenerarAnalisisIntegralAlmacenTests -v 2`
Expected: FAIL / ERROR — `ImportError: cannot import name 'generar_analisis_integral'`

- [ ] **Step 3: Implement the generator function**

In `modulos/reportes/generadores/almacen.py`, add near the top (after `from django.utils import timezone`):

```python
from collections import defaultdict
```

Add the new function after `generar_movimientos` (right before the `# Mapa tipo_reporte → función generadora` comment):

```python
def generar_analisis_integral(periodo_inicio: date, periodo_fin: date) -> dict:
    """Reporte integral de asignaciones directas, entradas y auditoría del período."""
    from modulos.almacen.models import (
        AsignacionDirectaAlmacen, AsignacionSalida, EntradaAlmacen, AuditoriaAlmacen,
    )

    # --- Asignaciones directas (AsignacionDirectaAlmacen + AsignacionSalida) ---
    directas_qs = (
        AsignacionDirectaAlmacen.objects
        .filter(fecha_asignacion__date__gte=periodo_inicio, fecha_asignacion__date__lte=periodo_fin)
        .select_related('producto', 'unidad', 'entregado_por')
    )
    salidas_qs = (
        AsignacionSalida.objects
        .filter(creado_en__date__gte=periodo_inicio, creado_en__date__lte=periodo_fin)
        .select_related('unidad', 'equipo', 'dolly', 'caja_seca', 'entregado_por')
        .prefetch_related('items__producto')
    )

    asignaciones = []
    for a in directas_qs:
        asignaciones.append({
            'folio': a.folio,
            'tipo': 'DIRECTA',
            'destino': str(a.unidad),
            'producto_sku': a.producto.sku,
            'producto_desc': a.producto.descripcion,
            'cantidad': float(a.cantidad),
            'motivo': a.motivo,
            'entregado_por': a.entregado_por.get_full_name() or a.entregado_por.username,
            'fecha': a.fecha_asignacion.strftime('%d/%m/%Y %H:%M'),
        })
    for s in salidas_qs:
        entregado_por = (
            (s.entregado_por.get_full_name() or s.entregado_por.username) if s.entregado_por_id else ''
        )
        for item in s.items.all():
            asignaciones.append({
                'folio': s.folio,
                'tipo': 'SALIDA',
                'destino': s.destino_display,
                'producto_sku': item.producto.sku,
                'producto_desc': item.producto.descripcion,
                'cantidad': float(item.cantidad),
                'motivo': s.justificacion,
                'entregado_por': entregado_por,
                'fecha': s.creado_en.strftime('%d/%m/%Y %H:%M'),
            })

    destino_totales = defaultdict(float)
    for fila in asignaciones:
        destino_totales[fila['destino']] += fila['cantidad']
    top_destinos = [
        {'destino': destino, 'cantidad_total': total}
        for destino, total in sorted(destino_totales.items(), key=lambda kv: kv[1], reverse=True)[:5]
    ]

    # --- Entradas (EntradaAlmacen) ---
    entradas_qs = (
        EntradaAlmacen.objects
        .filter(fecha_entrada__date__gte=periodo_inicio, fecha_entrada__date__lte=periodo_fin)
        .select_related('recibido_por')
    )
    entradas = []
    entradas_por_tipo = defaultdict(int)
    valor_total_entradas = Decimal('0')
    for e in entradas_qs:
        entradas_por_tipo[e.get_tipo_display()] += 1
        valor_total_entradas += e.costo_total_entrada
        entradas.append({
            'folio': e.folio,
            'tipo': e.tipo,
            'tipo_display': e.get_tipo_display(),
            'recibido_por': e.recibido_por.get_full_name() or e.recibido_por.username,
            'costo_total_entrada': float(e.costo_total_entrada),
            'total_items': e.total_items,
            'fecha_entrada': e.fecha_entrada.strftime('%d/%m/%Y %H:%M'),
        })

    # --- Auditoría (AuditoriaAlmacen) ---
    auditoria_qs = (
        AuditoriaAlmacen.objects
        .filter(fecha__date__gte=periodo_inicio, fecha__date__lte=periodo_fin)
        .select_related('usuario')
    )
    accion_a_campo = {
        'CREAR': 'crear', 'EDITAR': 'editar', 'ELIMINAR': 'eliminar',
        'AUTORIZAR': 'autorizar', 'RECHAZAR': 'rechazar',
        'ENTREGAR': 'entregar', 'CANCELAR': 'cancelar',
    }
    por_usuario = defaultdict(lambda: {campo: 0 for campo in accion_a_campo.values()})
    auditoria_por_accion = {label: 0 for _, label in AuditoriaAlmacen.ACCION_CHOICES}
    total_eventos_auditoria = 0
    for ev in auditoria_qs:
        usuario_nombre = (
            (ev.usuario.get_full_name() or ev.usuario.username) if ev.usuario_id else 'sistema'
        )
        campo = accion_a_campo[ev.accion]
        por_usuario[usuario_nombre][campo] += 1
        auditoria_por_accion[ev.get_accion_display()] += 1
        total_eventos_auditoria += 1

    auditoria = []
    for usuario_nombre, conteos in por_usuario.items():
        total_usuario = sum(conteos.values())
        auditoria.append({'usuario': usuario_nombre, 'total_eventos': total_usuario, **conteos})
    auditoria.sort(key=lambda f: f['total_eventos'], reverse=True)
    top_usuarios_auditoria = auditoria[:5]

    alertas_auditoria = []
    if total_eventos_auditoria > 0:
        if len(auditoria) >= 2:
            top = auditoria[0]
            pct_top = top['total_eventos'] / total_eventos_auditoria
            if pct_top > 0.5:
                alertas_auditoria.append(
                    f"El usuario {top['usuario']} concentra el {round(pct_top * 100)}% de la "
                    f"actividad de auditoría del período."
                )
        eliminar_count = auditoria_por_accion.get('Eliminar', 0)
        pct_eliminar = eliminar_count / total_eventos_auditoria
        if pct_eliminar > 0.2:
            alertas_auditoria.append(
                f"Las eliminaciones representan el {round(pct_eliminar * 100)}% de los eventos de "
                f"auditoría del período, por encima del umbral esperado."
            )

    resumen = {
        'total_asignaciones_directas': directas_qs.count(),
        'total_asignaciones_salida': salidas_qs.count(),
        'total_items_asignados': sum(f['cantidad'] for f in asignaciones),
        'total_entradas': entradas_qs.count(),
        'entradas_por_tipo': dict(entradas_por_tipo),
        'valor_total_entradas': float(valor_total_entradas),
        'total_eventos_auditoria': total_eventos_auditoria,
        'auditoria_por_accion': auditoria_por_accion,
        'alertas_auditoria': alertas_auditoria,
    }

    return {
        'tipo': 'ALMACEN_ANALISIS_INTEGRAL',
        'titulo': (
            f'Análisis Integral de Almacén — {periodo_inicio.strftime("%d/%m/%Y")} '
            f'al {periodo_fin.strftime("%d/%m/%Y")}'
        ),
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': resumen,
        'asignaciones': asignaciones,
        'entradas': entradas,
        'auditoria': auditoria,
        'top_destinos': top_destinos,
        'top_usuarios_auditoria': top_usuarios_auditoria,
        'tablas': {
            'Asignaciones': asignaciones,
            'Entradas': entradas,
            'Auditoria': auditoria,
        },
    }
```

Update the `GENERADORES` dict at the bottom of the same file:

```python
GENERADORES = {
    'ALMACEN_INVENTARIO': generar_inventario_general,
    'ALMACEN_STOCK_CRITICO': generar_stock_critico,
    'ALMACEN_CADUCIDAD': generar_proximos_caducar,
    'ALMACEN_MOVIMIENTOS': generar_movimientos,
    'ALMACEN_ANALISIS_INTEGRAL': generar_analisis_integral,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `DBURL='sqlite://' python manage.py test modulos.reportes.tests.GenerarAnalisisIntegralAlmacenTests -v 2`
Expected: `OK` — 4 tests passing

- [ ] **Step 5: Commit**

```bash
git add modulos/reportes/generadores/almacen.py modulos/reportes/tests.py
git commit -m "$(cat <<'EOF'
Agrega generador de datos para el reporte de análisis integral de almacén

Combina asignaciones directas, entradas y auditoría del período en un
solo generador para que IAKasu tenga visibilidad de estos tres procesos.
EOF
)"
```

---

### Task 2: Registrar el tipo de reporte `ALMACEN_ANALISIS_INTEGRAL`

**Files:**
- Modify: `modulos/reportes/models.py:17-31`
- Create: `modulos/reportes/migrations/0006_alter_configuracionreporte_tipo_reporte.py` (autogenerado)

**Interfaces:**
- Consumes: nothing new.
- Produces: `ConfiguracionReporte.TIPO_CHOICES` includes `('ALMACEN_ANALISIS_INTEGRAL', 'Almacén — Análisis integral (asignaciones, entradas, auditoría)')`, usable by the admin/config UI and by Task 3's narrativa dispatch.

- [ ] **Step 1: Add the choice to `TIPO_CHOICES`**

In `modulos/reportes/models.py`, modify:

```python
        ('ALMACEN_MOVIMIENTOS',  'Almacén — Movimientos del período'),
        # Combustible
```

to:

```python
        ('ALMACEN_MOVIMIENTOS',  'Almacén — Movimientos del período'),
        ('ALMACEN_ANALISIS_INTEGRAL', 'Almacén — Análisis integral (asignaciones, entradas, auditoría)'),
        # Combustible
```

- [ ] **Step 2: Generate the migration**

Run: `python manage.py makemigrations reportes`
Expected output:
```
Migrations for 'reportes':
  modulos/reportes/migrations/0006_alter_configuracionreporte_tipo_reporte.py
    ~ Alter field tipo_reporte on configuracionreporte
```

- [ ] **Step 3: Verify no system errors**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add modulos/reportes/models.py modulos/reportes/migrations/0006_alter_configuracionreporte_tipo_reporte.py
git commit -m "$(cat <<'EOF'
Registra el tipo de reporte ALMACEN_ANALISIS_INTEGRAL

Agrega la opción al catálogo de ConfiguracionReporte para poder
programar el nuevo reporte desde la UI existente.
EOF
)"
```

---

### Task 3: Narrativa IA especializada

**Files:**
- Modify: `modulos/reportes/generadores/narrativa.py`
- Test: `modulos/reportes/tests.py`

**Interfaces:**
- Consumes: `resumen` dict and `datos` dict shape produced by Task 1's `generar_analisis_integral` (keys `total_asignaciones_directas`, `total_asignaciones_salida`, `total_items_asignados`, `total_entradas`, `entradas_por_tipo`, `valor_total_entradas`, `total_eventos_auditoria`, `auditoria_por_accion`, `alertas_auditoria`, `top_destinos`, `top_usuarios_auditoria`).
- Produces: `_prompt_almacen_analisis_integral(resumen, datos, periodo_inicio, periodo_fin) -> tuple[str, int]`, wired into `generar_narrativa()`'s dispatch for `tipo_reporte == 'ALMACEN_ANALISIS_INTEGRAL'`.

- [ ] **Step 1: Write the failing test**

Append to `modulos/reportes/tests.py`:

```python
class PromptAnalisisIntegralAlmacenTests(TestCase):
    def test_prompt_incluye_kpis_principales(self):
        from modulos.reportes.generadores.narrativa import _prompt_almacen_analisis_integral

        resumen = {
            'total_asignaciones_directas': 3, 'total_asignaciones_salida': 2,
            'total_items_asignados': 12.0, 'total_entradas': 5,
            'entradas_por_tipo': {'Producto Nuevo desde Factura': 5},
            'valor_total_entradas': 1500.0, 'total_eventos_auditoria': 4,
            'auditoria_por_accion': {'Crear': 4},
            'alertas_auditoria': [
                'El usuario Juan Perez concentra el 90% de la actividad de auditoría del período.'
            ],
        }
        datos = {
            'top_destinos': [{'destino': 'Unidad U-100', 'cantidad_total': 8.0}],
            'top_usuarios_auditoria': [{'usuario': 'Juan Perez', 'total_eventos': 4}],
        }
        prompt, max_tokens = _prompt_almacen_analisis_integral(
            resumen, datos, '2026-07-01', '2026-07-22'
        )
        self.assertIn('Unidad U-100', prompt)
        self.assertIn('Juan Perez', prompt)
        self.assertIn('Producto Nuevo desde Factura', prompt)
        self.assertEqual(max_tokens, 600)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DBURL='sqlite://' python manage.py test modulos.reportes.tests.PromptAnalisisIntegralAlmacenTests -v 2`
Expected: FAIL / ERROR — `ImportError: cannot import name '_prompt_almacen_analisis_integral'`

- [ ] **Step 3: Implement the prompt function**

In `modulos/reportes/generadores/narrativa.py`, add the entry to `_NOMBRES_REPORTE`:

```python
_NOMBRES_REPORTE = {
    'ALMACEN_INVENTARIO':    'Inventario general de almacén',
    'ALMACEN_STOCK_CRITICO': 'Stock crítico de almacén',
    'ALMACEN_CADUCIDAD':     'Productos próximos a caducar en almacén',
    'ALMACEN_MOVIMIENTOS':   'Movimientos de almacén (entradas y salidas)',
    'ALMACEN_ANALISIS_INTEGRAL': 'Análisis integral de almacén (asignaciones, entradas, auditoría)',
    'COMBUSTIBLE_CARGAS':    'Cargas de combustible del período',
    'COMBUSTIBLE_CONSUMO':   'Consumo de combustible por unidad',
    'COMBUSTIBLE_ALERTAS':   'Alertas de candado de combustible',
    'UNIDADES_KILOMETRAJE':  'Kilometraje actual de la flota',
}
```

Add the new prompt function right after `_prompt_almacen_movimientos`:

```python
def _prompt_almacen_analisis_integral(resumen: dict, datos: dict, periodo_inicio: str, periodo_fin: str) -> tuple:
    """Prompt especializado para el reporte de análisis integral de almacén."""
    total_directas = resumen.get('total_asignaciones_directas', 0)
    total_salida = resumen.get('total_asignaciones_salida', 0)
    total_items = resumen.get('total_items_asignados', 0)
    total_entradas = resumen.get('total_entradas', 0)
    entradas_por_tipo = resumen.get('entradas_por_tipo', {})
    valor_entradas = resumen.get('valor_total_entradas', 0)
    total_eventos_auditoria = resumen.get('total_eventos_auditoria', 0)
    alertas_auditoria = resumen.get('alertas_auditoria', [])

    top_destinos = datos.get('top_destinos', [])
    top_usuarios = datos.get('top_usuarios_auditoria', [])

    destinos_texto = '\n'.join(
        f"  {i+1}. {d['destino']} — {d['cantidad_total']} piezas"
        for i, d in enumerate(top_destinos)
    ) or '  Sin asignaciones registradas en el período'

    entradas_texto = '\n'.join(
        f"  - {tipo}: {cantidad}" for tipo, cantidad in entradas_por_tipo.items()
    ) or '  Sin entradas registradas en el período'

    usuarios_texto = '\n'.join(
        f"  {i+1}. {u['usuario']} — {u['total_eventos']} eventos"
        for i, u in enumerate(top_usuarios)
    ) or '  Sin actividad de auditoría en el período'

    alertas_texto = '\n'.join(f"  ⚠ {a}" for a in alertas_auditoria) or '  Sin anomalías detectadas'

    prompt = (
        f"Reporte: Análisis Integral de Almacén\n"
        f"Período: {periodo_inicio} al {periodo_fin}\n\n"
        f"Asignaciones directas de piezas:\n"
        f"  - Asignaciones directas: {total_directas} | Asignaciones de salida: {total_salida} "
        f"| Total de piezas asignadas: {total_items}\n"
        f"  Top destinos que más piezas reciben:\n{destinos_texto}\n\n"
        f"Entradas al almacén:\n"
        f"  - Total entradas: {total_entradas} | Valor total: ${valor_entradas:,.2f} MXN\n"
        f"  Desglose por tipo:\n{entradas_texto}\n\n"
        f"Actividad de auditoría:\n"
        f"  - Total eventos: {total_eventos_auditoria}\n"
        f"  Top usuarios por actividad:\n{usuarios_texto}\n"
        f"  Anomalías detectadas:\n{alertas_texto}\n\n"
        f"Redacta el análisis ejecutivo correlacionando las tres áreas: señala si alguna unidad o "
        f"destino concentra asignaciones directas de forma recurrente (posible falla mecánica "
        f"recurrente), si el volumen de entradas es consistente con la actividad general del "
        f"almacén, y si las anomalías de auditoría ameritan atención de la gerencia:"
    )
    return prompt, 600
```

Update the dispatch inside `generar_narrativa()`:

```python
    if tipo_reporte == 'ALMACEN_MOVIMIENTOS':
        prompt, max_tokens = _prompt_almacen_movimientos(
            resumen, datos or {}, periodo_inicio, periodo_fin
        )
        modelo = Modelo.SONNET
    elif tipo_reporte == 'ALMACEN_ANALISIS_INTEGRAL':
        prompt, max_tokens = _prompt_almacen_analisis_integral(
            resumen, datos or {}, periodo_inicio, periodo_fin
        )
        modelo = Modelo.SONNET
    else:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DBURL='sqlite://' python manage.py test modulos.reportes.tests.PromptAnalisisIntegralAlmacenTests -v 2`
Expected: `OK` — 1 test passing

- [ ] **Step 5: Commit**

```bash
git add modulos/reportes/generadores/narrativa.py modulos/reportes/tests.py
git commit -m "$(cat <<'EOF'
Agrega prompt de narrativa IA para el análisis integral de almacén

Correlaciona asignaciones directas, entradas y auditoría en un solo
párrafo ejecutivo generado con Claude Sonnet.
EOF
)"
```

---

### Task 4: Soporte multi-hoja en el export a Excel

**Files:**
- Modify: `modulos/reportes/management/commands/generar_reportes.py:63-124`
- Test: `modulos/reportes/tests.py`

**Interfaces:**
- Consumes: `datos['tablas']` (dict `{nombre_hoja: filas}`) as produced by Task 1; falls back to `datos['filas']` for every other existing report type (unchanged behavior).
- Produces: `_generar_excel(datos: dict) -> bytes` (same signature as before) and a new internal helper `_escribir_hoja_detalle(ws, filas: list) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `modulos/reportes/tests.py`:

```python
class GenerarExcelTablasTests(TestCase):
    def test_genera_una_hoja_por_tabla(self):
        import openpyxl
        from io import BytesIO
        from modulos.reportes.management.commands.generar_reportes import _generar_excel

        datos = {
            'titulo': 'Análisis Integral de Almacén',
            'resumen': {
                'total_entradas': 2,
                'entradas_por_tipo': {'Producto Nuevo desde Factura': 2},
                'alertas_auditoria': ['El usuario X concentra actividad.'],
            },
            'tablas': {
                'Asignaciones': [{'folio': 'ADI-1', 'cantidad': 2.0}],
                'Entradas': [{'folio': 'ENT-1', 'costo_total_entrada': 100.0}],
                'Auditoria': [{'usuario': 'Juan', 'total_eventos': 3}],
            },
        }
        contenido = _generar_excel(datos)
        wb = openpyxl.load_workbook(BytesIO(contenido))
        self.assertEqual(set(wb.sheetnames), {'Asignaciones', 'Entradas', 'Auditoria', 'Resumen'})
        ws = wb['Asignaciones']
        self.assertEqual(ws['A1'].value, 'Folio')
        self.assertEqual(ws['A2'].value, 'ADI-1')

    def test_resumen_con_dict_y_listas_no_lanza_error(self):
        import openpyxl
        from io import BytesIO
        from modulos.reportes.management.commands.generar_reportes import _generar_excel

        datos = {
            'titulo': 'Reporte', 'filas': [{'sku': 'A1', 'cantidad': 1}],
            'resumen': {'entradas_por_tipo': {'Factura': 2}, 'alertas_auditoria': ['x']},
        }
        contenido = _generar_excel(datos)
        wb = openpyxl.load_workbook(BytesIO(contenido))
        self.assertIn('Resumen', wb.sheetnames)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DBURL='sqlite://' python manage.py test modulos.reportes.tests.GenerarExcelTablasTests -v 2`
Expected: FAIL — `test_genera_una_hoja_por_tabla` fails (no `tablas` support, only one sheet named after `titulo`); `test_resumen_con_dict_y_listas_no_lanza_error` fails with `TypeError: Cannot convert ... to Excel` when writing a dict/list value into a cell

- [ ] **Step 3: Refactor `_generar_excel` and add `_escribir_hoja_detalle`**

Replace the body of `_generar_excel` in `modulos/reportes/management/commands/generar_reportes.py` (from `def _generar_excel(datos: dict) -> bytes:` through the end of that function, right before `def _enviar_email`) with:

```python
def _escribir_hoja_detalle(ws, filas: list) -> None:
    """Escribe encabezados y filas de detalle en una hoja, con auto-ajuste de columnas."""
    if not filas:
        return

    headers = list(filas[0].keys())
    fill_azul = PatternFill(start_color='1D4ED8', end_color='1D4ED8', fill_type='solid')
    font_blanco_bold = Font(bold=True, color='FFFFFF')

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header.replace('_', ' ').title())
        cell.font = font_blanco_bold
        cell.fill = fill_azul
        cell.alignment = Alignment(horizontal='center')

    # Detectar qué columnas son de foto (contienen URLs)
    foto_headers = {h for h in headers if h.startswith('foto_')}
    font_link = Font(color='1D4ED8', underline='single')

    for row_idx, fila in enumerate(filas, 2):
        for col_idx, header in enumerate(headers, 1):
            valor = fila.get(header) or ''
            cell = ws.cell(row=row_idx, column=col_idx)
            if header in foto_headers and valor:
                cell.value = 'Ver foto'
                cell.hyperlink = valor
                cell.font = font_link
            else:
                cell.value = valor if valor != '' else None

    # Ajustar ancho de columnas (fotos fijas en 12)
    for col in ws.columns:
        header_cell = col[0]
        letter = header_cell.column_letter
        if header_cell.value and str(header_cell.value).lower().startswith('foto'):
            ws.column_dimensions[letter].width = 12
        else:
            max_len = max((len(str(cell.value or '')) for cell in col), default=8)
            ws.column_dimensions[letter].width = min(max_len + 4, 40)


def _generar_excel(datos: dict) -> bytes:
    """Genera un archivo Excel con el detalle del período reportado."""
    wb = openpyxl.Workbook()

    tablas = datos.get('tablas')
    if tablas:
        wb.remove(wb.active)
        for nombre_hoja, filas in tablas.items():
            ws = wb.create_sheet(nombre_hoja.replace('/', '-').replace('\\', '-')[:31])
            _escribir_hoja_detalle(ws, filas)
    else:
        ws = wb.active
        titulo_hoja = datos.get('titulo', 'Reporte').replace('/', '-').replace('\\', '-')[:31]
        ws.title = titulo_hoja
        _escribir_hoja_detalle(ws, datos.get('filas', []))

    # --- Hoja de resumen ---
    ws_res = wb.create_sheet('Resumen')
    ws_res['A1'] = 'Métrica'
    ws_res['B1'] = 'Valor'
    ws_res['A1'].font = Font(bold=True)
    ws_res['B1'].font = Font(bold=True)
    for idx, (k, v) in enumerate(datos.get('resumen', {}).items(), 2):
        ws_res.cell(row=idx, column=1, value=k.replace('_', ' ').title())
        ws_res.cell(row=idx, column=2, value=str(v) if isinstance(v, (list, dict)) else v)
    ws_res.column_dimensions['A'].width = 30
    ws_res.column_dimensions['B'].width = 20

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
```

Note: the `str(v) if isinstance(v, (list, dict)) else v` guard on the Resumen sheet is required because `generar_analisis_integral`'s `resumen` now contains nested dicts/lists (`entradas_por_tipo`, `auditoria_por_accion`, `alertas_auditoria`) — openpyxl raises `TypeError` if you write those types directly into a cell.

- [ ] **Step 4: Run tests to verify they pass**

Run: `DBURL='sqlite://' python manage.py test modulos.reportes.tests.GenerarExcelTablasTests -v 2`
Expected: `OK` — 2 tests passing

- [ ] **Step 5: Run the full existing Excel-related tests to confirm no regression**

Run: `DBURL='sqlite://' python manage.py test modulos.reportes -v 2`
Expected: `OK` — all tests in the module pass (includes Task 1–3 tests plus pre-existing `EsDebidoMensualTests` / `GenerarVigenciasFlotaTests`)

- [ ] **Step 6: Commit**

```bash
git add modulos/reportes/management/commands/generar_reportes.py modulos/reportes/tests.py
git commit -m "$(cat <<'EOF'
Soporte multi-hoja en el export a Excel de reportes

Permite que un reporte entregue varias tablas con columnas distintas
(datos['tablas']) generando una hoja de Excel por cada una, y evita
errores al serializar valores dict/list en la hoja de Resumen.
EOF
)"
```

---

### Task 5: Bloque de email para `ALMACEN_ANALISIS_INTEGRAL`

**Files:**
- Modify: `templates/reportes/email/reporte_base.html:169`
- Test: `modulos/reportes/tests.py`

**Interfaces:**
- Consumes: `datos.tipo`, `datos.resumen` (incl. `total_asignaciones_directas`, `total_asignaciones_salida`, `total_entradas`, `valor_total_entradas`, `total_eventos_auditoria`, `entradas_por_tipo`, `alertas_auditoria`), `datos.top_destinos`, `datos.top_usuarios_auditoria` — all produced by Task 1.
- Produces: rendered HTML fragment reused by `_enviar_email()` in `generar_reportes.py` (no signature change there).

- [ ] **Step 1: Write the failing test**

Append to `modulos/reportes/tests.py`:

```python
class EmailTemplateAnalisisIntegralTests(TestCase):
    def test_render_incluye_secciones_principales(self):
        from django.template.loader import render_to_string

        datos = {
            'tipo': 'ALMACEN_ANALISIS_INTEGRAL',
            'titulo': 'Análisis Integral de Almacén',
            'periodo_inicio': '2026-07-01', 'periodo_fin': '2026-07-22',
            'generado_en': '2026-07-22T09:00:00',
            'resumen': {
                'total_asignaciones_directas': 3, 'total_asignaciones_salida': 2,
                'total_entradas': 5, 'valor_total_entradas': 1500.0,
                'total_eventos_auditoria': 7,
                'entradas_por_tipo': {'Producto Nuevo desde Factura': 5},
                'alertas_auditoria': [
                    'El usuario Juan Perez concentra el 86% de la actividad de auditoría del período.'
                ],
            },
            'top_destinos': [{'destino': 'Unidad U-100', 'cantidad_total': 8.0}],
            'top_usuarios_auditoria': [{'usuario': 'Juan Perez', 'total_eventos': 6}],
        }
        html = render_to_string(
            'reportes/email/reporte_base.html', {'datos': datos, 'config': None, 'narrativa': ''}
        )
        self.assertIn('Unidad U-100', html)
        self.assertIn('Producto Nuevo desde Factura', html)
        self.assertIn('Juan Perez', html)
        self.assertIn('concentra el 86%', html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DBURL='sqlite://' python manage.py test modulos.reportes.tests.EmailTemplateAnalisisIntegralTests -v 2`
Expected: FAIL — the assertions for `'Unidad U-100'`, `'Producto Nuevo desde Factura'`, and the alert text are not found (falls through to the generic KPI block, which doesn't render these fields)

- [ ] **Step 3: Add the template block**

In `templates/reportes/email/reporte_base.html`, find this line (currently right after the `ALMACEN_MOVIMIENTOS` block, around line 169):

```html
    {% else %}

    <!-- KPI genérico para otros tipos de reporte -->
```

Replace it with:

```html
    {% elif datos.tipo == 'ALMACEN_ANALISIS_INTEGRAL' %}

    <!-- KPIs generales -->
    <div class="resumen">
      <div class="kpi">
        <div class="label">Asignaciones Directas</div>
        <div class="value">{{ datos.resumen.total_asignaciones_directas }}</div>
      </div>
      <div class="kpi">
        <div class="label">Asignaciones de Salida</div>
        <div class="value">{{ datos.resumen.total_asignaciones_salida }}</div>
      </div>
      <div class="kpi blue">
        <div class="label">Total Entradas</div>
        <div class="value">{{ datos.resumen.total_entradas }}</div>
      </div>
      <div class="kpi green">
        <div class="label">Valor Entradas</div>
        <div class="value">${{ datos.resumen.valor_total_entradas|floatformat:"0" }}</div>
      </div>
      <div class="kpi {% if datos.resumen.alertas_auditoria %}amber{% else %}green{% endif %}">
        <div class="label">Eventos de Auditoría</div>
        <div class="value">{{ datos.resumen.total_eventos_auditoria }}</div>
      </div>
    </div>

    {% if datos.resumen.alertas_auditoria %}
    {% for alerta in datos.resumen.alertas_auditoria %}
    <div class="alert danger">⚠️ {{ alerta }}</div>
    {% endfor %}
    {% endif %}

    <hr class="divider">

    {% if datos.top_destinos %}
    <p class="section-title">🔧 Top Destinos de Asignaciones Directas</p>
    <table class="detail-table">
      <thead>
        <tr style="background: #1e40af;">
          <th style="width:36px;">#</th>
          <th>Destino</th>
          <th class="td-right">Piezas Asignadas</th>
        </tr>
      </thead>
      <tbody>
        {% for item in datos.top_destinos %}
        <tr style="background: {% if forloop.counter|divisibleby:2 %}#f8fafc{% else %}#ffffff{% endif %};">
          <td><span class="rank-badge {% if forloop.first %}gold{% endif %}">{{ forloop.counter }}</span></td>
          <td style="color: #111827; font-weight: 500;">{{ item.destino }}</td>
          <td class="td-right"><span class="pill pill-blue">{{ item.cantidad_total }}</span></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="alert info">Sin asignaciones directas registradas en el período.</div>
    {% endif %}

    <hr class="divider">

    {% if datos.resumen.entradas_por_tipo %}
    <p class="section-title">📦 Entradas por Tipo</p>
    <table class="detail-table">
      <thead>
        <tr style="background: #1e40af;">
          <th>Tipo</th>
          <th class="td-right">Cantidad</th>
        </tr>
      </thead>
      <tbody>
        {% for tipo, cantidad in datos.resumen.entradas_por_tipo.items %}
        <tr style="background: {% if forloop.counter|divisibleby:2 %}#f8fafc{% else %}#ffffff{% endif %};">
          <td style="color: #374151;">{{ tipo }}</td>
          <td class="td-right"><span class="pill pill-blue">{{ cantidad }}</span></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="alert info">Sin entradas registradas en el período.</div>
    {% endif %}

    <hr class="divider">

    {% if datos.top_usuarios_auditoria %}
    <p class="section-title">🕵️ Actividad de Auditoría por Usuario</p>
    <table class="detail-table">
      <thead>
        <tr style="background: #1e40af;">
          <th>Usuario</th>
          <th class="td-right">Total Eventos</th>
        </tr>
      </thead>
      <tbody>
        {% for item in datos.top_usuarios_auditoria %}
        <tr style="background: {% if forloop.counter|divisibleby:2 %}#f8fafc{% else %}#ffffff{% endif %};">
          <td style="color: #111827; font-weight: 500;">{{ item.usuario }}</td>
          <td class="td-right"><span class="pill pill-blue">{{ item.total_eventos }}</span></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="alert info">Sin actividad de auditoría en el período.</div>
    {% endif %}

    {% else %}

    <!-- KPI genérico para otros tipos de reporte -->
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DBURL='sqlite://' python manage.py test modulos.reportes.tests.EmailTemplateAnalisisIntegralTests -v 2`
Expected: `OK` — 1 test passing

- [ ] **Step 5: Commit**

```bash
git add templates/reportes/email/reporte_base.html modulos/reportes/tests.py
git commit -m "$(cat <<'EOF'
Agrega bloque de email para el reporte de análisis integral de almacén

Muestra KPIs, top destinos de asignaciones directas, entradas por
tipo y actividad de auditoría por usuario, con alertas de anomalía.
EOF
)"
```

---

### Task 6: Verificación final end-to-end

**Files:** none (verification only)

**Interfaces:** N/A — this task only exercises the integration of Tasks 1–5 through the existing `generar_reportes` management command.

- [ ] **Step 1: Run the full reportes test suite**

Run: `DBURL='sqlite://' python manage.py test modulos.reportes -v 2`
Expected: `OK` — every test passes, including all tests added in Tasks 1, 3, 4, 5 plus the pre-existing `EsDebidoMensualTests` and `GenerarVigenciasFlotaTests`

- [ ] **Step 2: Run the full project test suite to confirm no regressions elsewhere**

Run: `DBURL='sqlite://' python manage.py test`
Expected: `OK`

- [ ] **Step 3: Manual dry-run smoke test of the real pipeline (including live Claude narrative)**

In the Django shell or via a one-off script, create a `ConfiguracionReporte` and force-run it without sending real emails:

```bash
python manage.py shell -c "
from modulos.reportes.models import ConfiguracionReporte
c = ConfiguracionReporte.objects.create(
    nombre='Análisis Integral de Almacén (prueba)',
    modulo='ALMACEN', tipo_reporte='ALMACEN_ANALISIS_INTEGRAL',
    frecuencia='MENSUAL', dia_mes=1,
    destinatarios='test@example.com', adjuntar_excel=True,
)
print(c.id)
"
```

Then run (replace `<ID>` with the printed id):

```bash
python manage.py generar_reportes --dry-run --forzar-id <ID>
```

Expected output: `RUN   Análisis Integral de Almacén (prueba) (...)`, followed by `IA    Narrativa generada para Análisis Integral de Almacén (prueba)` (if `IA_HABILITADA=True` and there's data in the current period) or no IA line (if the period is empty — `generar_narrativa` returns `''` when `resumen` is falsy... note `resumen` here is never empty since it always has keys, so the narrativa call will always attempt to run; confirm it completes without raising), and `OK    Análisis Integral de Almacén (prueba)`, with `Ejecutados: 1  Errores: 0` at the end.

Delete the test configuration afterward:

```bash
python manage.py shell -c "
from modulos.reportes.models import ConfiguracionReporte
ConfiguracionReporte.objects.filter(nombre='Análisis Integral de Almacén (prueba)').delete()
"
```

- [ ] **Step 4: Confirm with the user**

Report back: all 6 tasks complete, full test suite green, manual dry-run confirmed the new report type generates data, an IA narrative, and a valid multi-sheet Excel file end-to-end. No further commit needed for this task (verification only).
