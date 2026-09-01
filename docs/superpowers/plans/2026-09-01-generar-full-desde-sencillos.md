# Generar Full desde dos Sencillos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cuando se registran dos viajes SENCILLO con la misma unidad y el mismo operador, detectarlo al guardar y ofrecer (vía modal) fusionarlos en un único viaje FULL — directo o con reparto según coincidan cliente y CP destino — en alta manual, edición y traslado desde Modulación.

**Architecture:** Lógica de negocio pura en un módulo nuevo `modulos/bitacoras/services_full.py` (detección de capacidad de unidad, emparejamiento y fusión). Un endpoint JSON `verificar_full` alimenta un modal JS en los dos formularios. Las vistas (`BitacoraCreateView`, `BitacoraUpdateView`, `EnviarABitacoraView`) revalidan en servidor y ejecutan la fusión dentro de `transaction.atomic()`. La carga masiva no se toca.

**Tech Stack:** Django 5.2.7, Python 3.14, PostgreSQL (prod) / SQLite (dev). Tests con `django.test.TestCase`. Frontend: templates Django + JS vanilla (sin framework).

## Global Constraints

- Todo el texto visible (labels, mensajes, verbose_name, comentarios) en **español** (es-mx).
- Modalidades del modelo `BitacoraViaje.MODALIDAD_CHOICES`: `SENCILLO`, `FULL`, `LOCAL`, `LOCAL_FULL`. **No existe** `FORANEO`.
- "En curso" = `completado == False`.
- Carga de unidad: `SENCILLO`/`LOCAL` = 1 contenedor; `FULL`/`LOCAL_FULL` = 2. Máximo 2 por unidad.
- El emparejamiento para Full exige: `modalidad='SENCILLO'` + `completado=False` + misma `unidad` + mismo `operador`.
- Tipo de Full: `cliente` **y** `cp_destino` iguales → `directo` (`reparto=False`); si difiere alguno → `reparto` (`reparto=True`, se copian `cliente_2`/`cp_destino_2`).
- Una unidad **no puede** quedar con dos sencillos separados vía estos flujos: si no se acepta el Full, no se guarda.
- Nunca confiar solo en el cliente: la detección se repite en servidor.
- Fusión siempre dentro de `transaction.atomic()`.
- Campo de unidad en `Unidad` para "activa": `activa` (no `activo`). En `Operador`: `activo`.
- Ejecutar tests con: `python manage.py test <ruta> --keepdb --noinput` (la BD de test es PostgreSQL y no se puede recrear en este entorno).

---

## File Structure

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `modulos/bitacoras/services_full.py` | Crear | Lógica pura: capacidad de unidad, emparejamiento, evaluación de decisión, fusión. |
| `modulos/bitacoras/tests_full.py` | Crear | Tests de `services_full`, endpoint `verificar_full`, y rutas de fusión de `BitacoraCreateView`/`BitacoraUpdateView`. |
| `modulos/bitacoras/views.py` | Modificar | Nueva vista `verificar_full`; `_form_context(excluir_pk)`; rama de fusión en `BitacoraCreateView.form_valid` y `BitacoraUpdateView.form_valid`. |
| `modulos/bitacoras/urls.py` | Modificar | Ruta `ajax/verificar-full/`. |
| `modulos/bitacoras/forms.py` | Modificar | `BitacoraViajeForm`: filtro de `unidad`, campo oculto `confirmar_full`, `clean()` con `fusion_result`. |
| `modulos/modulacion/forms.py` | Modificar | `PromoverBitacoraForm`: filtro de `unidad`. |
| `modulos/modulacion/views.py` | Modificar | `EnviarABitacoraView.post`: rama de fusión + ligado de la Modulación al FULL. |
| `modulos/modulacion/tests.py` | Modificar | Ampliar `EnviarABitacoraViewTests`. |
| `templates/bitacoras/bitacora_form.html` | Modificar | Markup del modal + JS de interceptación en `#bitacoraForm`. |
| `templates/modulacion/enviar_a_bitacora.html` | Modificar | Markup del modal + bloque `extra_js` con el JS de interceptación. |

---

## Task 1: `services_full.py` — capacidad de unidad

**Files:**
- Create: `modulos/bitacoras/services_full.py`
- Test: `modulos/bitacoras/tests_full.py`

**Interfaces:**
- Consumes: `BitacoraViaje` de `modulos.bitacoras.models`.
- Produces:
  - `CARGA_POR_MODALIDAD: dict[str, int]`
  - `viajes_en_curso(unidad, *, excluir_pk=None) -> list[BitacoraViaje]` (con `operador` pre-cargado)
  - `contenedores_en_curso(unidad, *, excluir_pk=None) -> int`
  - `unidad_bloqueada(unidad, *, excluir_pk=None) -> bool`
  - `unidades_bloqueadas_ids(*, excluir_pk=None) -> set[int]`

- [ ] **Step 1: Write the failing test**

Crear `modulos/bitacoras/tests_full.py`:

```python
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from modulos.bitacoras.models import BitacoraViaje, Cliente
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad
from modulos.bitacoras import services_full


def _unidad(numero_economico='ECO-001', tipo='FORANEA'):
    return Unidad.objects.create(
        numero_economico=numero_economico, placa='ABC-123', tipo=tipo,
        año=2020, capacidad_combustible=Decimal('200.00'),
        rendimiento_esperado=Decimal('3.00'),
    )


def _operador(nombre='Juan Pérez', tipo='FORANEO'):
    return Operador.objects.create(nombre=nombre, tipo=tipo)


def _viaje(unidad, operador, *, modalidad='SENCILLO', completado=False,
           cliente=None, cp_destino='40810', contenedor='ABCU1234567'):
    ahora = timezone.now()
    v = BitacoraViaje(
        cliente=cliente, modalidad=modalidad, operador=operador, unidad=unidad,
        contenedor=contenedor, fecha_carga=ahora, fecha_salida=ahora,
        destino='Destino X', cp_destino=cp_destino, completado=completado,
    )
    if modalidad in ('FULL', 'LOCAL_FULL'):
        v.contenedor_2 = 'ZZZU9999999'
    v.save()
    return v


class CapacidadUnidadTests(TestCase):
    def setUp(self):
        self.unidad = _unidad()
        self.op = _operador()

    def test_contenedores_en_curso_cuenta_sencillo_como_uno(self):
        _viaje(self.unidad, self.op, modalidad='SENCILLO')
        self.assertEqual(services_full.contenedores_en_curso(self.unidad), 1)

    def test_contenedores_en_curso_cuenta_full_como_dos(self):
        _viaje(self.unidad, self.op, modalidad='FULL')
        self.assertEqual(services_full.contenedores_en_curso(self.unidad), 2)

    def test_contenedores_en_curso_ignora_completados(self):
        _viaje(self.unidad, self.op, modalidad='SENCILLO', completado=True)
        self.assertEqual(services_full.contenedores_en_curso(self.unidad), 0)

    def test_contenedores_en_curso_respeta_excluir_pk(self):
        v = _viaje(self.unidad, self.op, modalidad='FULL')
        self.assertEqual(
            services_full.contenedores_en_curso(self.unidad, excluir_pk=v.pk), 0)

    def test_unidad_bloqueada_con_full(self):
        _viaje(self.unidad, self.op, modalidad='FULL')
        self.assertTrue(services_full.unidad_bloqueada(self.unidad))

    def test_unidad_bloqueada_con_dos_sencillos(self):
        _viaje(self.unidad, self.op, contenedor='AAAU1111111')
        _viaje(self.unidad, _operador('Otro'), contenedor='BBBU2222222')
        self.assertTrue(services_full.unidad_bloqueada(self.unidad))

    def test_unidad_no_bloqueada_con_un_sencillo(self):
        _viaje(self.unidad, self.op, modalidad='SENCILLO')
        self.assertFalse(services_full.unidad_bloqueada(self.unidad))

    def test_unidades_bloqueadas_ids(self):
        libre = _unidad('ECO-LIBRE')
        _viaje(libre, self.op, modalidad='SENCILLO')
        _viaje(self.unidad, self.op, modalidad='FULL')
        ids = services_full.unidades_bloqueadas_ids()
        self.assertIn(self.unidad.pk, ids)
        self.assertNotIn(libre.pk, ids)

    def test_unidades_bloqueadas_ids_respeta_excluir_pk(self):
        v = _viaje(self.unidad, self.op, modalidad='FULL')
        self.assertEqual(services_full.unidades_bloqueadas_ids(excluir_pk=v.pk), set())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test modulos.bitacoras.tests_full.CapacidadUnidadTests --keepdb --noinput`
Expected: FAIL — `ModuleNotFoundError: No module named 'modulos.bitacoras.services_full'`

- [ ] **Step 3: Write minimal implementation**

Crear `modulos/bitacoras/services_full.py`:

```python
"""
Lógica para detectar cuándo dos viajes SENCILLO (misma unidad + mismo
operador, en curso) deben unirse en un único viaje FULL, y para ejecutar esa
fusión. Compartida por el alta manual de bitácoras, su edición y el traslado
desde Modulación.
"""
import os

from modulos.bitacoras.models import BitacoraViaje

# Contenedores que ocupa cada modalidad en la capacidad de la unidad.
CARGA_POR_MODALIDAD = {
    'SENCILLO': 1,
    'LOCAL': 1,
    'FULL': 2,
    'LOCAL_FULL': 2,
}

CAPACIDAD_UNIDAD = 2


def viajes_en_curso(unidad, *, excluir_pk=None):
    """Viajes no completados de la unidad, con el operador pre-cargado."""
    if unidad is None:
        return []
    qs = (BitacoraViaje.objects
          .filter(unidad=unidad, completado=False)
          .select_related('operador'))
    if excluir_pk:
        qs = qs.exclude(pk=excluir_pk)
    return list(qs)


def contenedores_en_curso(unidad, *, excluir_pk=None):
    """Suma la carga (1 ó 2) de los viajes en curso de la unidad."""
    return sum(
        CARGA_POR_MODALIDAD.get(v.modalidad, 1)
        for v in viajes_en_curso(unidad, excluir_pk=excluir_pk)
    )


def unidad_bloqueada(unidad, *, excluir_pk=None):
    """True si la unidad ya llegó a su capacidad (2 contenedores en curso)."""
    return contenedores_en_curso(unidad, excluir_pk=excluir_pk) >= CAPACIDAD_UNIDAD


def unidades_bloqueadas_ids(*, excluir_pk=None):
    """Ids de unidades con 2+ contenedores en curso (para filtrar selectores)."""
    from django.db.models import Case, IntegerField, Sum, Value, When

    qs = BitacoraViaje.objects.filter(completado=False)
    if excluir_pk:
        qs = qs.exclude(pk=excluir_pk)
    qs = (qs.values('unidad_id')
            .annotate(carga=Sum(Case(
                When(modalidad__in=['FULL', 'LOCAL_FULL'], then=Value(2)),
                default=Value(1),
                output_field=IntegerField(),
            )))
            .filter(carga__gte=CAPACIDAD_UNIDAD))
    return {row['unidad_id'] for row in qs}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test modulos.bitacoras.tests_full.CapacidadUnidadTests --keepdb --noinput`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add modulos/bitacoras/services_full.py modulos/bitacoras/tests_full.py
git commit -m "Full desde sencillos: capacidad de unidad en services_full"
```

---

## Task 2: `services_full.py` — emparejamiento y evaluación de decisión

**Files:**
- Modify: `modulos/bitacoras/services_full.py`
- Test: `modulos/bitacoras/tests_full.py`

**Interfaces:**
- Consumes: `viajes_en_curso`, `CARGA_POR_MODALIDAD`, `CAPACIDAD_UNIDAD` de Task 1.
- Produces:
  - `sencillo_apareable(unidad, operador, *, excluir_pk=None) -> BitacoraViaje | None`
  - `evaluar_fusion(unidad, operador, cliente, cp_destino, *, excluir_pk=None) -> dict`
    - `{'accion': 'ninguna'}`
    - `{'accion': 'bloqueo', 'mensaje': str}`
    - `{'accion': 'ofrecer_full', 'sencillo': BitacoraViaje, 'tipo_full': 'directo'|'reparto'}`
  - `cliente` es instancia de `Cliente` o `None`; `cp_destino` es `str`.

- [ ] **Step 1: Write the failing test**

Añadir a `modulos/bitacoras/tests_full.py`:

```python
class SencilloApareableTests(TestCase):
    def setUp(self):
        self.unidad = _unidad()
        self.op = _operador()

    def test_devuelve_sencillo_mismo_operador_en_curso(self):
        v = _viaje(self.unidad, self.op, modalidad='SENCILLO')
        self.assertEqual(
            services_full.sencillo_apareable(self.unidad, self.op), v)

    def test_none_si_operador_distinto(self):
        _viaje(self.unidad, self.op, modalidad='SENCILLO')
        self.assertIsNone(
            services_full.sencillo_apareable(self.unidad, _operador('Otro')))

    def test_none_si_completado(self):
        _viaje(self.unidad, self.op, modalidad='SENCILLO', completado=True)
        self.assertIsNone(services_full.sencillo_apareable(self.unidad, self.op))

    def test_none_si_es_full(self):
        _viaje(self.unidad, self.op, modalidad='FULL')
        self.assertIsNone(services_full.sencillo_apareable(self.unidad, self.op))

    def test_respeta_excluir_pk(self):
        v = _viaje(self.unidad, self.op, modalidad='SENCILLO')
        self.assertIsNone(
            services_full.sencillo_apareable(self.unidad, self.op, excluir_pk=v.pk))


class EvaluarFusionTests(TestCase):
    def setUp(self):
        self.unidad = _unidad()
        self.op = _operador()
        self.cli_a = Cliente.objects.create(nombre='Cliente A')
        self.cli_b = Cliente.objects.create(nombre='Cliente B')

    def test_ninguna_si_unidad_libre(self):
        res = services_full.evaluar_fusion(self.unidad, self.op, self.cli_a, '40810')
        self.assertEqual(res['accion'], 'ninguna')

    def test_ninguna_si_faltan_datos(self):
        res = services_full.evaluar_fusion(None, None, None, '')
        self.assertEqual(res['accion'], 'ninguna')

    def test_ofrecer_full_directo_mismo_cliente_y_cp(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810')
        res = services_full.evaluar_fusion(self.unidad, self.op, self.cli_a, '40810')
        self.assertEqual(res['accion'], 'ofrecer_full')
        self.assertEqual(res['tipo_full'], 'directo')

    def test_ofrecer_full_reparto_si_cambia_cliente(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810')
        res = services_full.evaluar_fusion(self.unidad, self.op, self.cli_b, '40810')
        self.assertEqual(res['tipo_full'], 'reparto')

    def test_ofrecer_full_reparto_si_cambia_cp(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810')
        res = services_full.evaluar_fusion(self.unidad, self.op, self.cli_a, '62520')
        self.assertEqual(res['tipo_full'], 'reparto')

    def test_bloqueo_si_operador_distinto(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a)
        res = services_full.evaluar_fusion(
            self.unidad, _operador('Pedro'), self.cli_a, '40810')
        self.assertEqual(res['accion'], 'bloqueo')
        self.assertIn('sencillo', res['mensaje'].lower())

    def test_bloqueo_si_unidad_llena_con_full(self):
        _viaje(self.unidad, self.op, modalidad='FULL')
        res = services_full.evaluar_fusion(
            self.unidad, _operador('Pedro'), self.cli_a, '40810')
        self.assertEqual(res['accion'], 'bloqueo')
        self.assertIn('2 contenedores', res['mensaje'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test modulos.bitacoras.tests_full.SencilloApareableTests modulos.bitacoras.tests_full.EvaluarFusionTests --keepdb --noinput`
Expected: FAIL — `AttributeError: module 'modulos.bitacoras.services_full' has no attribute 'sencillo_apareable'`

- [ ] **Step 3: Write minimal implementation**

Añadir a `modulos/bitacoras/services_full.py` (después de `unidades_bloqueadas_ids`):

```python
def sencillo_apareable(unidad, operador, *, excluir_pk=None):
    """
    Viaje SENCILLO en curso de la misma unidad y el mismo operador con el que
    se puede formar un Full. El más reciente por fecha_carga si hubiera varios.
    """
    if unidad is None or operador is None:
        return None
    candidatos = [
        v for v in viajes_en_curso(unidad, excluir_pk=excluir_pk)
        if v.modalidad == 'SENCILLO' and v.operador_id == operador.pk
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda v: v.fecha_carga)


def _mismo_destino(sencillo, cliente, cp_destino):
    """True si el sencillo va al mismo cliente y CP que los datos dados."""
    cliente_pk = cliente.pk if cliente is not None else None
    mismo_cliente = sencillo.cliente_id == cliente_pk
    mismo_cp = (sencillo.cp_destino or '').strip() == (cp_destino or '').strip()
    return mismo_cliente and mismo_cp


def evaluar_fusion(unidad, operador, cliente, cp_destino, *, excluir_pk=None):
    """
    Decide qué hacer al guardar/editar un viaje SENCILLO. Devuelve un dict con
    'accion' en {'ninguna', 'bloqueo', 'ofrecer_full'}.
    """
    if unidad is None or operador is None:
        return {'accion': 'ninguna'}

    apareable = sencillo_apareable(unidad, operador, excluir_pk=excluir_pk)
    if apareable is not None:
        tipo = 'directo' if _mismo_destino(apareable, cliente, cp_destino) else 'reparto'
        return {'accion': 'ofrecer_full', 'sencillo': apareable, 'tipo_full': tipo}

    en_curso = viajes_en_curso(unidad, excluir_pk=excluir_pk)

    sencillo_otro_op = next(
        (v for v in en_curso
         if v.modalidad == 'SENCILLO' and v.operador_id != operador.pk),
        None,
    )
    if sencillo_otro_op is not None:
        return {'accion': 'bloqueo', 'mensaje': (
            f'La unidad {unidad.numero_economico} ya tiene un viaje sencillo en '
            f'curso con el operador {sencillo_otro_op.operador.nombre}. Una unidad '
            f'no puede llevar dos sencillos por separado; para un segundo '
            f'contenedor genere un Full con el mismo operador.'
        )}

    carga = sum(CARGA_POR_MODALIDAD.get(v.modalidad, 1) for v in en_curso)
    if carga >= CAPACIDAD_UNIDAD:
        return {'accion': 'bloqueo', 'mensaje': (
            f'La unidad {unidad.numero_economico} ya tiene 2 contenedores en curso.'
        )}

    return {'accion': 'ninguna'}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test modulos.bitacoras.tests_full.SencilloApareableTests modulos.bitacoras.tests_full.EvaluarFusionTests --keepdb --noinput`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add modulos/bitacoras/services_full.py modulos/bitacoras/tests_full.py
git commit -m "Full desde sencillos: emparejamiento y evaluar_fusion"
```

---

## Task 3: `services_full.py` — ejecutar la fusión

**Files:**
- Modify: `modulos/bitacoras/services_full.py`
- Test: `modulos/bitacoras/tests_full.py`

**Interfaces:**
- Consumes: nada nuevo.
- Produces:
  - `fusionar_en_full(sencillo_existente, datos_segundo, *, tipo_full) -> BitacoraViaje`
  - `datos_segundo` es dict con claves `contenedor`, `peso`, `sellos`, `cliente`, `cp_destino`.
  - Muta y guarda `sencillo_existente` (`modalidad='FULL'`). No borra el 2º registro (lo hace el caller). Recalcula Google Maps solo si queda `reparto=True` con `cp_destino_2` y hay `GOOGLE_MAPS_API_KEY`.

- [ ] **Step 1: Write the failing test**

Añadir a `modulos/bitacoras/tests_full.py`:

```python
from unittest.mock import patch


class FusionarEnFullTests(TestCase):
    def setUp(self):
        self.unidad = _unidad()
        self.op = _operador()
        self.cli_a = Cliente.objects.create(nombre='Cliente A')
        self.cli_b = Cliente.objects.create(nombre='Cliente B')

    def _datos_segundo(self, **over):
        base = {
            'contenedor': 'bbbu2222222',
            'peso': Decimal('12.00'),
            'sellos': 'S-99',
            'cliente': self.cli_b,
            'cp_destino': '62520',
        }
        base.update(over)
        return base

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_fusion_directa_no_llena_contenedor_2_cliente(self, _maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
                   contenedor='AAAU1111111')
        full = services_full.fusionar_en_full(
            s, self._datos_segundo(cliente=self.cli_a, cp_destino='40810'),
            tipo_full='directo')
        self.assertEqual(full.modalidad, 'FULL')
        self.assertEqual(full.contenedor_2, 'BBBU2222222')
        self.assertEqual(full.peso_2, Decimal('12.00'))
        self.assertEqual(full.sellos_2, 'S-99')
        self.assertFalse(full.reparto)
        self.assertIsNone(full.cliente_2)
        self.assertEqual(full.cp_destino_2, '')

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_fusion_con_reparto_llena_cliente_2_y_cp_2(self, _maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
                   contenedor='AAAU1111111')
        full = services_full.fusionar_en_full(
            s, self._datos_segundo(), tipo_full='reparto')
        self.assertTrue(full.reparto)
        self.assertEqual(full.cliente_2, self.cli_b)
        self.assertEqual(full.cp_destino_2, '62520')

    @patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY': 'x'})
    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_fusion_reparto_recalcula_distancia(self, maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, contenedor='AAAU1111111')
        services_full.fusionar_en_full(s, self._datos_segundo(), tipo_full='reparto')
        maps.assert_called_once()

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_fusion_persiste_en_bd(self, _maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, contenedor='AAAU1111111')
        services_full.fusionar_en_full(s, self._datos_segundo(), tipo_full='reparto')
        s.refresh_from_db()
        self.assertEqual(s.modalidad, 'FULL')
        self.assertEqual(s.contenedor_2, 'BBBU2222222')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test modulos.bitacoras.tests_full.FusionarEnFullTests --keepdb --noinput`
Expected: FAIL — `AttributeError: module 'modulos.bitacoras.services_full' has no attribute 'fusionar_en_full'`

- [ ] **Step 3: Write minimal implementation**

Añadir a `modulos/bitacoras/services_full.py`:

```python
def fusionar_en_full(sencillo_existente, datos_segundo, *, tipo_full):
    """
    Convierte `sencillo_existente` en un viaje FULL absorbiendo el segundo
    contenedor. Conserva todos los datos del primer contenedor (fechas,
    destino, kilometraje, diésel, tipo). Guarda con full_clean().

    `datos_segundo`: {contenedor, peso, sellos, cliente, cp_destino}.
    `tipo_full`: 'directo' (mismo destino) o 'reparto' (dos destinos).

    El borrado del segundo registro y el ligado de la Modulación son
    responsabilidad de quien llama.
    """
    s = sencillo_existente
    s.modalidad = 'FULL'
    s.contenedor_2 = (datos_segundo.get('contenedor') or '').strip().upper()
    s.peso_2 = datos_segundo.get('peso')
    s.sellos_2 = datos_segundo.get('sellos') or ''

    if tipo_full == 'reparto':
        s.reparto = True
        s.cliente_2 = datos_segundo.get('cliente')
        s.cp_destino_2 = (datos_segundo.get('cp_destino') or '').strip()
    else:
        s.reparto = False
        s.cliente_2 = None
        s.cp_destino_2 = ''

    s.full_clean()
    s.save()

    if s.reparto and s.cp_destino_2 and os.environ.get('GOOGLE_MAPS_API_KEY'):
        s.calcular_distancia_google()

    return s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test modulos.bitacoras.tests_full.FusionarEnFullTests --keepdb --noinput`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add modulos/bitacoras/services_full.py modulos/bitacoras/tests_full.py
git commit -m "Full desde sencillos: fusionar_en_full"
```

---

## Task 4: Endpoint `verificar_full`

**Files:**
- Modify: `modulos/bitacoras/views.py` (añadir vista al final, antes de la sección de clientes o junto a `unidad_info_ajax`)
- Modify: `modulos/bitacoras/urls.py`
- Test: `modulos/bitacoras/tests_full.py`

**Interfaces:**
- Consumes: `services_full.evaluar_fusion`, modelos `Unidad`, `Operador`, `Cliente`.
- Produces: `GET /bitacoras/ajax/verificar-full/` → JSON.
  - Params: `unidad` (id), `operador` (id), `cliente` (id, opcional), `cp_destino` (str, opcional), `excluir_pk` (id, opcional).
  - Respuestas:
    - `{"accion": "ninguna"}`
    - `{"accion": "bloqueo", "mensaje": "..."}`
    - `{"accion": "ofrecer_full", "tipo_full": "directo"|"reparto", "sencillo": {"id", "contenedor", "cliente", "cp_destino"}, "nuevo": {"cliente", "cp_destino"}}`

- [ ] **Step 1: Write the failing test**

Añadir a `modulos/bitacoras/tests_full.py`:

```python
from django.contrib.auth import get_user_model
from django.urls import reverse


class VerificarFullEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='t', password='p')
        self.client.login(username='t', password='p')
        self.url = reverse('bitacoras:verificar_full')
        self.unidad = _unidad()
        self.op = _operador()
        self.cli_a = Cliente.objects.create(nombre='Cliente A')
        self.cli_b = Cliente.objects.create(nombre='Cliente B')

    def test_ninguna_si_unidad_libre(self):
        r = self.client.get(self.url, {
            'unidad': self.unidad.pk, 'operador': self.op.pk,
            'cliente': self.cli_a.pk, 'cp_destino': '40810',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['accion'], 'ninguna')

    def test_ofrecer_full_reparto(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
               contenedor='AAAU1111111')
        r = self.client.get(self.url, {
            'unidad': self.unidad.pk, 'operador': self.op.pk,
            'cliente': self.cli_b.pk, 'cp_destino': '62520',
        })
        data = r.json()
        self.assertEqual(data['accion'], 'ofrecer_full')
        self.assertEqual(data['tipo_full'], 'reparto')
        self.assertEqual(data['sencillo']['contenedor'], 'AAAU1111111')
        self.assertEqual(data['sencillo']['cliente'], 'Cliente A')
        self.assertEqual(data['nuevo']['cliente'], 'Cliente B')

    def test_bloqueo_operador_distinto(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, contenedor='AAAU1111111')
        otro = _operador('Pedro')
        r = self.client.get(self.url, {
            'unidad': self.unidad.pk, 'operador': otro.pk,
            'cliente': self.cli_a.pk, 'cp_destino': '40810',
        })
        data = r.json()
        self.assertEqual(data['accion'], 'bloqueo')
        self.assertIn('Pedro', data['mensaje'])

    def test_ninguna_si_faltan_params(self):
        r = self.client.get(self.url, {'unidad': self.unidad.pk})
        self.assertEqual(r.json()['accion'], 'ninguna')

    def test_requiere_login(self):
        self.client.logout()
        r = self.client.get(self.url, {'unidad': self.unidad.pk, 'operador': self.op.pk})
        self.assertEqual(r.status_code, 302)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test modulos.bitacoras.tests_full.VerificarFullEndpointTests --keepdb --noinput`
Expected: FAIL — `django.urls.exceptions.NoReverseMatch: Reverse for 'verificar_full' not found`

- [ ] **Step 3: Write minimal implementation**

En `modulos/bitacoras/views.py`, añadir después de `unidad_info_ajax` (final del archivo):

```python
@login_required
def verificar_full(request):
    """
    Indica si al guardar un viaje SENCILLO con esta unidad+operador se debe
    ofrecer generar un Full, bloquear, o nada. Alimenta el modal del formulario.
    GET /bitacoras/ajax/verificar-full/?unidad=&operador=&cliente=&cp_destino=&excluir_pk=
    """
    from modulos.operadores.models import Operador
    from modulos.unidades.models import Unidad
    from .services_full import evaluar_fusion

    unidad = Unidad.objects.filter(pk=request.GET.get('unidad') or 0).first()
    operador = Operador.objects.filter(pk=request.GET.get('operador') or 0).first()
    cliente = Cliente.objects.filter(pk=request.GET.get('cliente') or 0).first()
    cp_destino = (request.GET.get('cp_destino') or '').strip()
    excluir_pk = request.GET.get('excluir_pk') or None

    res = evaluar_fusion(unidad, operador, cliente, cp_destino, excluir_pk=excluir_pk)

    if res['accion'] == 'ofrecer_full':
        s = res['sencillo']
        return JsonResponse({
            'accion': 'ofrecer_full',
            'tipo_full': res['tipo_full'],
            'sencillo': {
                'id': s.pk,
                'contenedor': s.contenedor,
                'cliente': s.cliente.nombre if s.cliente else '',
                'cp_destino': s.cp_destino or '',
            },
            'nuevo': {
                'cliente': cliente.nombre if cliente else '',
                'cp_destino': cp_destino,
            },
        })

    if res['accion'] == 'bloqueo':
        return JsonResponse({'accion': 'bloqueo', 'mensaje': res['mensaje']})

    return JsonResponse({'accion': 'ninguna'})
```

En `modulos/bitacoras/urls.py`, dentro de `urlpatterns`, en el bloque `# AJAX utilitarios`:

```python
    path('ajax/verificar-full/', views.verificar_full, name='verificar_full'),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test modulos.bitacoras.tests_full.VerificarFullEndpointTests --keepdb --noinput`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add modulos/bitacoras/views.py modulos/bitacoras/urls.py modulos/bitacoras/tests_full.py
git commit -m "Full desde sencillos: endpoint verificar_full"
```

---

## Task 5: `BitacoraViajeForm` — filtro de unidad, `confirmar_full`, `clean()`

**Files:**
- Modify: `modulos/bitacoras/forms.py`
- Modify: `modulos/bitacoras/views.py` (`_form_context`)
- Test: `modulos/bitacoras/tests_full.py`

**Interfaces:**
- Consumes: `services_full.unidades_bloqueadas_ids`, `services_full.evaluar_fusion`.
- Produces:
  - `BitacoraViajeForm` acepta el campo POST `confirmar_full` (BooleanField oculto, no requerido).
  - Tras `is_valid()`, `form.fusion_result` es el dict de `evaluar_fusion` (o `None` si la modalidad no es SENCILLO / faltan datos).
  - `_form_context(excluir_pk=None)` — `unidades_form` excluye unidades bloqueadas.

- [ ] **Step 1: Write the failing test**

Añadir a `modulos/bitacoras/tests_full.py`:

```python
from modulos.bitacoras.forms import BitacoraViajeForm


class BitacoraViajeFormFusionTests(TestCase):
    def setUp(self):
        self.unidad = _unidad()
        self.op = _operador()
        self.cli_a = Cliente.objects.create(nombre='Cliente A')

    def _post(self, **over):
        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        data = {
            'cliente': self.cli_a.pk, 'modalidad': 'SENCILLO',
            'operador': self.op.pk, 'unidad': self.unidad.pk,
            'fecha_carga': ahora, 'fecha_salida': ahora,
            'contenedor': 'AAAU1111111', 'tipo_contenedor': '40',
            'cp_origen': '40812', 'cp_destino': '40810', 'destino': 'X',
        }
        data.update(over)
        return data

    def test_sin_sencillo_previo_es_valido_y_fusion_result_ninguna(self):
        form = BitacoraViajeForm(data=self._post())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.fusion_result['accion'], 'ninguna')

    def test_con_sencillo_apareable_sin_confirmar_es_invalido(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
               contenedor='BBBU2222222')
        form = BitacoraViajeForm(data=self._post(contenedor='CCCU3333333'))
        self.assertFalse(form.is_valid())

    def test_con_sencillo_apareable_y_confirmar_full_es_valido(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
               contenedor='BBBU2222222')
        form = BitacoraViajeForm(
            data=self._post(contenedor='CCCU3333333', confirmar_full='1'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.fusion_result['accion'], 'ofrecer_full')

    def test_operador_distinto_es_invalido_incluso_con_confirmar(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, contenedor='BBBU2222222')
        form = BitacoraViajeForm(data=self._post(
            operador=_operador('Pedro').pk, contenedor='CCCU3333333',
            confirmar_full='1'))
        self.assertFalse(form.is_valid())

    def test_unidad_bloqueada_fuera_del_queryset(self):
        _viaje(self.unidad, self.op, modalidad='FULL', contenedor='BBBU2222222')
        form = BitacoraViajeForm()
        self.assertNotIn(self.unidad, form.fields['unidad'].queryset)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test modulos.bitacoras.tests_full.BitacoraViajeFormFusionTests --keepdb --noinput`
Expected: FAIL — `AttributeError: 'BitacoraViajeForm' object has no attribute 'fusion_result'`

- [ ] **Step 3: Write minimal implementation**

En `modulos/bitacoras/forms.py`:

1. Al principio del archivo, tras `from .models import BitacoraViaje, Cliente`, añadir:

```python
from .services_full import evaluar_fusion, unidades_bloqueadas_ids
```

2. Añadir el campo `confirmar_full` como atributo de clase de `BitacoraViajeForm` (justo debajo de `class BitacoraViajeForm(forms.ModelForm):` y su docstring, antes de `class Meta`):

```python
    confirmar_full = forms.BooleanField(required=False, widget=forms.HiddenInput)
```

3. Reemplazar el método `__init__` actual por:

```python
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fusion_result = None

        modalidad_actual = self.instance.modalidad if self.instance and self.instance.pk else None
        if modalidad_actual not in ('LOCAL', 'LOCAL_FULL'):
            self.fields['modalidad'].choices = [
                (valor, etiqueta) for valor, etiqueta in self.fields['modalidad'].choices
                if valor not in ('LOCAL', 'LOCAL_FULL')
            ]

        # Ocultar unidades que ya llegaron a su capacidad (2 contenedores en curso).
        excluir_pk = self.instance.pk if self.instance and self.instance.pk else None
        bloqueadas = unidades_bloqueadas_ids(excluir_pk=excluir_pk)
        if bloqueadas:
            self.fields['unidad'].queryset = self.fields['unidad'].queryset.exclude(
                id__in=bloqueadas
            )
```

4. Al final de `clean()` (antes del `return cleaned_data`), añadir:

```python
        # Detección de "generar Full": dos sencillos con misma unidad + operador.
        if modalidad == 'SENCILLO':
            unidad = cleaned_data.get('unidad')
            operador = cleaned_data.get('operador')
            cliente = cleaned_data.get('cliente')
            cp_destino = cleaned_data.get('cp_destino') or ''
            excluir_pk = self.instance.pk if self.instance and self.instance.pk else None
            res = evaluar_fusion(unidad, operador, cliente, cp_destino, excluir_pk=excluir_pk)
            self.fusion_result = res

            if res['accion'] == 'bloqueo':
                self.add_error('unidad', res['mensaje'])
            elif res['accion'] == 'ofrecer_full' and not cleaned_data.get('confirmar_full'):
                self.add_error(None, (
                    'Esta unidad ya tiene un viaje sencillo en curso con este operador. '
                    'Genere un Full para agregar el segundo contenedor.'
                ))
```

En `modulos/bitacoras/views.py`, reemplazar `_form_context`:

```python
def _form_context(excluir_pk=None):
    """Contexto compartido entre Create y Update: listas de unidades y operadores."""
    from modulos.operadores.models import Operador
    from modulos.unidades.models import Unidad
    from .services_full import unidades_bloqueadas_ids

    bloqueadas = unidades_bloqueadas_ids(excluir_pk=excluir_pk)
    return {
        'unidades_form': Unidad.objects.filter(activa=True).exclude(id__in=bloqueadas).order_by('numero_economico'),
        'operadores_form': Operador.objects.filter(activo=True).order_by('nombre'),
    }
```

En `BitacoraUpdateView.get_context_data`, cambiar `context.update(_form_context())` por `context.update(_form_context(self.object.pk))`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test modulos.bitacoras.tests_full.BitacoraViajeFormFusionTests --keepdb --noinput`
Expected: PASS (5 tests)

- [ ] **Step 5: Run regression on bitacoras forms/tests**

Run: `python manage.py test modulos.bitacoras --keepdb --noinput`
Expected: PASS salvo fallos preexistentes ya conocidos (ver `modulos.bitacoras` tenía 4 fallos previos no relacionados; confirmar que no aparecen fallos NUEVOS en `forms`/`views`).

- [ ] **Step 6: Commit**

```bash
git add modulos/bitacoras/forms.py modulos/bitacoras/views.py modulos/bitacoras/tests_full.py
git commit -m "Full desde sencillos: BitacoraViajeForm filtra unidad y detecta fusion"
```

---

## Task 6: `BitacoraCreateView.form_valid` — rama de fusión

**Files:**
- Modify: `modulos/bitacoras/views.py` (`BitacoraCreateView.form_valid`)
- Test: `modulos/bitacoras/tests_full.py`

**Interfaces:**
- Consumes: `form.fusion_result` (Task 5), `services_full.fusionar_en_full`.
- Produces: si `form.fusion_result['accion'] == 'ofrecer_full'` y `confirmar_full` marcado → fusiona en el sencillo existente, **no** crea `BitacoraViaje` nuevo, redirige a `bitacoras:detail` del FULL con `messages.success`.

- [ ] **Step 1: Write the failing test**

Añadir a `modulos/bitacoras/tests_full.py`:

```python
from unittest.mock import patch as _patch


class BitacoraCreateFusionViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='t', password='p')
        self.client.login(username='t', password='p')
        self.url = reverse('bitacoras:create')
        self.unidad = _unidad()
        self.op = _operador()
        self.cli_a = Cliente.objects.create(nombre='Cliente A')
        self.cli_b = Cliente.objects.create(nombre='Cliente B')

    def _post(self, **over):
        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        data = {
            'cliente': self.cli_a.pk, 'modalidad': 'SENCILLO',
            'operador': self.op.pk, 'unidad': self.unidad.pk,
            'fecha_carga': ahora, 'fecha_salida': ahora,
            'contenedor': 'CCCU3333333', 'tipo_contenedor': '40',
            'cp_origen': '40812', 'cp_destino': '62520', 'destino': 'Y',
        }
        data.update(over)
        return data

    @_patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_sin_confirmar_no_fusiona_y_responde_200(self, _maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
                   contenedor='BBBU2222222')
        r = self.client.post(self.url, data=self._post())
        self.assertEqual(r.status_code, 200)  # re-render con error
        s.refresh_from_db()
        self.assertEqual(s.modalidad, 'SENCILLO')
        self.assertEqual(BitacoraViaje.objects.count(), 1)

    @_patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_con_confirmar_full_fusiona_y_no_crea_registro(self, _maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
                   contenedor='BBBU2222222')
        r = self.client.post(self.url, data=self._post(confirmar_full='1'))
        self.assertRedirects(r, reverse('bitacoras:detail', kwargs={'pk': s.pk}))
        s.refresh_from_db()
        self.assertEqual(s.modalidad, 'FULL')
        self.assertEqual(s.contenedor_2, 'CCCU3333333')
        self.assertTrue(s.reparto)
        self.assertEqual(s.cliente_2, self.cli_a)  # cliente del 2º contenedor
        self.assertEqual(s.cp_destino_2, '62520')
        self.assertEqual(BitacoraViaje.objects.count(), 1)

    @_patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_unidad_libre_crea_sencillo_normal(self, _maps):
        r = self.client.post(self.url, data=self._post())
        self.assertEqual(BitacoraViaje.objects.count(), 1)
        self.assertEqual(BitacoraViaje.objects.first().modalidad, 'SENCILLO')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test modulos.bitacoras.tests_full.BitacoraCreateFusionViewTests --keepdb --noinput`
Expected: FAIL — `test_con_confirmar_full_fusiona_y_no_crea_registro` falla (crea un 2º registro en vez de fusionar).

- [ ] **Step 3: Write minimal implementation**

En `modulos/bitacoras/views.py`, al inicio de `BitacoraCreateView.form_valid`, antes de `bitacora = form.save(commit=False)`:

```python
    def form_valid(self, form):
        from django.db import transaction
        from .services_full import fusionar_en_full

        res = form.fusion_result
        if res and res['accion'] == 'ofrecer_full' and form.cleaned_data.get('confirmar_full'):
            cd = form.cleaned_data
            datos_segundo = {
                'contenedor': cd.get('contenedor'),
                'peso': cd.get('peso'),
                'sellos': cd.get('sellos'),
                'cliente': cd.get('cliente'),
                'cp_destino': cd.get('cp_destino'),
            }
            with transaction.atomic():
                full = fusionar_en_full(
                    res['sencillo'], datos_segundo, tipo_full=res['tipo_full'])
            messages.success(
                self.request,
                f'Full generado: el viaje #{full.pk} ahora lleva 2 contenedores.')
            return redirect(reverse('bitacoras:detail', kwargs={'pk': full.pk}))

        bitacora = form.save(commit=False)
        # ... resto del método sin cambios ...
```

(El resto del cuerpo de `form_valid` queda igual.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test modulos.bitacoras.tests_full.BitacoraCreateFusionViewTests --keepdb --noinput`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add modulos/bitacoras/views.py modulos/bitacoras/tests_full.py
git commit -m "Full desde sencillos: fusion en BitacoraCreateView"
```

---

## Task 7: `BitacoraUpdateView.form_valid` — rama de fusión al editar

**Files:**
- Modify: `modulos/bitacoras/views.py` (`BitacoraUpdateView.form_valid`)
- Test: `modulos/bitacoras/tests_full.py`

**Interfaces:**
- Consumes: `form.fusion_result` con `excluir_pk=self.object.pk` (ya lo aplica el form en Task 5), `services_full.fusionar_en_full`.
- Produces: al confirmar, fusiona los datos del viaje editado en `res['sencillo']` (el OTRO sencillo), **elimina** `self.object`, redirige al FULL.

- [ ] **Step 1: Write the failing test**

Añadir a `modulos/bitacoras/tests_full.py`:

```python
class BitacoraUpdateFusionViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='t', password='p')
        self.client.login(username='t', password='p')
        self.unidad = _unidad()
        self.op = _operador()
        self.op2 = _operador('Pedro')
        self.cli_a = Cliente.objects.create(nombre='Cliente A')

    @_patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_editar_operador_para_aparear_fusiona_y_borra_editado(self, _maps):
        existente = _viaje(self.unidad, self.op, cliente=self.cli_a,
                           cp_destino='40810', contenedor='AAAU1111111')
        editado = _viaje(self.unidad, self.op2, cliente=self.cli_a,
                         cp_destino='40810', contenedor='BBBU2222222')
        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        url = reverse('bitacoras:update', kwargs={'pk': editado.pk})
        r = self.client.post(url, data={
            'cliente': self.cli_a.pk, 'modalidad': 'SENCILLO',
            'operador': self.op.pk, 'unidad': self.unidad.pk,
            'fecha_carga': ahora, 'fecha_salida': ahora,
            'contenedor': 'BBBU2222222', 'tipo_contenedor': '40',
            'cp_origen': '40812', 'cp_destino': '40810', 'destino': 'Z',
            'confirmar_full': '1',
        })
        self.assertRedirects(r, reverse('bitacoras:detail', kwargs={'pk': existente.pk}))
        existente.refresh_from_db()
        self.assertEqual(existente.modalidad, 'FULL')
        self.assertEqual(existente.contenedor_2, 'BBBU2222222')
        self.assertFalse(BitacoraViaje.objects.filter(pk=editado.pk).exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test modulos.bitacoras.tests_full.BitacoraUpdateFusionViewTests --keepdb --noinput`
Expected: FAIL — el viaje editado sigue existiendo y `existente.modalidad` sigue siendo `SENCILLO`.

- [ ] **Step 3: Write minimal implementation**

En `modulos/bitacoras/views.py`, reemplazar `BitacoraUpdateView.form_valid`:

```python
    def form_valid(self, form):
        from django.db import transaction
        from .services_full import fusionar_en_full

        res = form.fusion_result
        if res and res['accion'] == 'ofrecer_full' and form.cleaned_data.get('confirmar_full'):
            cd = form.cleaned_data
            datos_segundo = {
                'contenedor': cd.get('contenedor'),
                'peso': cd.get('peso'),
                'sellos': cd.get('sellos'),
                'cliente': cd.get('cliente'),
                'cp_destino': cd.get('cp_destino'),
            }
            with transaction.atomic():
                full = fusionar_en_full(
                    res['sencillo'], datos_segundo, tipo_full=res['tipo_full'])
                self.object.delete()
            messages.success(
                self.request,
                f'Full generado: el viaje #{full.pk} ahora lleva 2 contenedores.')
            return redirect(reverse('bitacoras:detail', kwargs={'pk': full.pk}))

        messages.success(self.request, 'Bitácora actualizada exitosamente.')
        return super().form_valid(form)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test modulos.bitacoras.tests_full.BitacoraUpdateFusionViewTests --keepdb --noinput`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add modulos/bitacoras/views.py modulos/bitacoras/tests_full.py
git commit -m "Full desde sencillos: fusion al editar en BitacoraUpdateView"
```

---

## Task 8: Modulación — `PromoverBitacoraForm` filtra unidad y `EnviarABitacoraView` fusiona/liga

**Files:**
- Modify: `modulos/modulacion/forms.py` (`PromoverBitacoraForm.__init__`)
- Modify: `modulos/modulacion/views.py` (`EnviarABitacoraView.post`)
- Test: `modulos/modulacion/tests.py` (ampliar `EnviarABitacoraViewTests`)

**Interfaces:**
- Consumes: `services_full.evaluar_fusion`, `services_full.fusionar_en_full`, `services_full.unidades_bloqueadas_ids`.
- Produces: si hay sencillo apareable (misma unidad+operador, en curso) y llega `confirmar_full=1` en el POST → fusiona el contenedor de la Modulación como 2º contenedor del sencillo existente; `modulacion.bitacora_viaje = full`, `estado='ENVIADO_BITACORA'`, `fecha_retiro=now()`; **no** se crea `BitacoraViaje` nuevo; redirige a `bitacoras:detail` del FULL.
- Si `evaluar_fusion` devuelve `bloqueo` → `messages.warning` + re-render del form.

- [ ] **Step 1: Write the failing test**

Añadir a `modulos/modulacion/tests.py`, dentro de `EnviarABitacoraViewTests` (helper de creación de viaje sencillo reutilizando los del módulo):

```python
    def _sencillo_en_curso(self, cliente, cp_destino='62520', contenedor='AAAU1111111'):
        ahora = timezone.now()
        return BitacoraViaje.objects.create(
            cliente=cliente, modalidad='SENCILLO', operador=self.operador,
            unidad=self.unidad, contenedor=contenedor, fecha_carga=ahora,
            fecha_salida=ahora, destino='Prev', cp_destino=cp_destino,
        )

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_confirmar_full_liga_modulacion_al_full_sin_crear_segundo_viaje(self, _maps):
        previo = self._sencillo_en_curso(cliente=self.cliente, cp_destino='62520')
        url = reverse('modulacion:enviar_a_bitacora', kwargs={'pk': self.modulacion.pk})
        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        r = self.client.post(url, data={
            'operador': self.operador.pk, 'unidad': self.unidad.pk,
            'fecha_carga': ahora, 'fecha_salida': ahora,
            'destino': 'Calle 1', 'cp_destino': '62520', 'confirmar_full': '1',
        })
        self.assertRedirects(r, reverse('bitacoras:detail', kwargs={'pk': previo.pk}))
        previo.refresh_from_db()
        self.assertEqual(previo.modalidad, 'FULL')
        self.assertEqual(previo.contenedor_2, self.modulacion.contenedor)
        self.assertFalse(previo.reparto)  # mismo cliente y CP
        self.modulacion.refresh_from_db()
        self.assertEqual(self.modulacion.bitacora_viaje_id, previo.pk)
        self.assertEqual(self.modulacion.estado, 'ENVIADO_BITACORA')
        self.assertEqual(BitacoraViaje.objects.count(), 1)

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_confirmar_full_reparto_si_cliente_distinto(self, _maps):
        otro_cliente = Cliente.objects.create(nombre='Otro Cliente')
        previo = self._sencillo_en_curso(cliente=otro_cliente, cp_destino='11111')
        url = reverse('modulacion:enviar_a_bitacora', kwargs={'pk': self.modulacion.pk})
        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        self.client.post(url, data={
            'operador': self.operador.pk, 'unidad': self.unidad.pk,
            'fecha_carga': ahora, 'fecha_salida': ahora,
            'destino': 'Calle 1', 'cp_destino': '62520', 'confirmar_full': '1',
        })
        previo.refresh_from_db()
        self.assertTrue(previo.reparto)
        self.assertEqual(previo.cliente_2, self.cliente)
        self.assertEqual(previo.cp_destino_2, '62520')

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_sin_sencillo_previo_crea_sencillo_normal(self, _maps):
        url = reverse('modulacion:enviar_a_bitacora', kwargs={'pk': self.modulacion.pk})
        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        self.client.post(url, data={
            'operador': self.operador.pk, 'unidad': self.unidad.pk,
            'fecha_carga': ahora, 'fecha_salida': ahora,
            'destino': 'Calle 1', 'cp_destino': '62520',
        })
        self.modulacion.refresh_from_db()
        self.assertEqual(self.modulacion.estado, 'ENVIADO_BITACORA')
        self.assertEqual(self.modulacion.bitacora_viaje.modalidad, 'SENCILLO')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test modulos.modulacion.tests.EnviarABitacoraViewTests --keepdb --noinput`
Expected: FAIL — `test_confirmar_full_liga_modulacion_al_full_sin_crear_segundo_viaje` crea un 2º `BitacoraViaje` en vez de fusionar.

- [ ] **Step 3: Write minimal implementation**

En `modulos/modulacion/forms.py`, `PromoverBitacoraForm.__init__`, tras fijar los querysets, añadir:

```python
        from modulos.bitacoras.services_full import unidades_bloqueadas_ids
        bloqueadas = unidades_bloqueadas_ids()
        if bloqueadas:
            self.fields['unidad'].queryset = self.fields['unidad'].queryset.exclude(
                id__in=bloqueadas
            )
```

En `modulos/modulacion/views.py`, `EnviarABitacoraView.post`, tras `if not form.is_valid(): ...` y antes de `bitacora = _crear_bitacora_desde_modulacion(...)`:

```python
        from django.db import transaction
        from modulos.bitacoras.services_full import evaluar_fusion, fusionar_en_full

        cd = form.cleaned_data
        res = evaluar_fusion(
            cd['unidad'], cd['operador'], modulacion.cliente, cd.get('cp_destino') or '',
        )

        if res['accion'] == 'bloqueo':
            messages.warning(request, res['mensaje'])
            return render(request, self.template_name, {'modulacion': modulacion, 'form': form})

        if res['accion'] == 'ofrecer_full' and request.POST.get('confirmar_full') == '1':
            datos_segundo = {
                'contenedor': modulacion.contenedor,
                'peso': modulacion.peso_toneladas,
                'sellos': '',
                'cliente': modulacion.cliente,
                'cp_destino': cd.get('cp_destino') or '',
            }
            with transaction.atomic():
                full = fusionar_en_full(
                    res['sencillo'], datos_segundo, tipo_full=res['tipo_full'])
                modulacion.bitacora_viaje = full
                modulacion.estado = 'ENVIADO_BITACORA'
                modulacion.fecha_retiro = timezone.now()
                modulacion.save()
            messages.success(
                request,
                f'Modulación {modulacion.folio} unida al Full #{full.pk} (2 contenedores).')
            return redirect(reverse('bitacoras:detail', kwargs={'pk': full.pk}))

        if res['accion'] == 'ofrecer_full':
            messages.warning(
                request,
                'Esta unidad ya tiene un viaje sencillo en curso con este operador. '
                'Confirme la generación del Full para continuar.')
            return render(request, self.template_name, {'modulacion': modulacion, 'form': form})
```

(El flujo `res['accion'] == 'ninguna'` cae al código existente que crea el sencillo.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test modulos.modulacion.tests.EnviarABitacoraViewTests --keepdb --noinput`
Expected: PASS (todos, incl. los 3 nuevos y los previos).

- [ ] **Step 5: Run regression on modulacion**

Run: `python manage.py test modulos.modulacion --keepdb --noinput`
Expected: PASS salvo `test_permite_filtrar_por_mes_y_anio_explicito` (fallo preexistente sensible a la fecha, no relacionado).

- [ ] **Step 6: Commit**

```bash
git add modulos/modulacion/forms.py modulos/modulacion/views.py modulos/modulacion/tests.py
git commit -m "Full desde sencillos: modulacion filtra unidad y liga al Full"
```

---

## Task 9: Modal en `bitacora_form.html`

**Files:**
- Modify: `templates/bitacoras/bitacora_form.html`
- Test: `modulos/bitacoras/tests_full.py` (smoke)

**Interfaces:**
- Consumes: endpoint `bitacoras:verificar_full`; elementos `#id_modalidad`, `#id_unidad`, `#id_operador`, `#id_cliente` (nota: cliente se renderiza con `{{ form.cliente }}` → id por defecto `id_cliente`), `#id_cp_destino`, form `#bitacoraForm`.
- Produces: al enviar un SENCILLO, intercepta, consulta el endpoint y muestra modal "Generar Full" / "Cancelar" o alerta de bloqueo.

- [ ] **Step 1: Write the smoke test**

Añadir a `modulos/bitacoras/tests_full.py`:

```python
class BitacoraFormModalMarkupTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='t', password='p')
        self.client.login(username='t', password='p')

    def test_form_incluye_modal_y_url_endpoint(self):
        r = self.client.get(reverse('bitacoras:create'))
        self.assertContains(r, 'id="modal-generar-full"')
        self.assertContains(r, '/bitacoras/ajax/verificar-full/')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test modulos.bitacoras.tests_full.BitacoraFormModalMarkupTests --keepdb --noinput`
Expected: FAIL — `id="modal-generar-full"` no está en la respuesta.

- [ ] **Step 3: Add modal markup**

En `templates/bitacoras/bitacora_form.html`, justo **después** de `</form>` (línea ~652) y antes de `{% endblock %}`:

```html
<!-- Modal: advertencia de generación de Full -->
<div id="modal-generar-full" style="display:none; position:fixed; inset:0; z-index:60;
     background:rgba(15,23,42,.55);">
  <div style="max-width:520px; margin:10vh auto 0; background:#fff; border-radius:14px;
       box-shadow:0 20px 60px rgba(0,0,0,.25); overflow:hidden;">
    <div style="padding:20px 24px; border-bottom:1px solid #f1f5f9;">
      <h3 id="modal-full-titulo" style="margin:0; font-size:1.05rem; font-weight:700; color:#0f172a;">
        Se generará un Full
      </h3>
    </div>
    <div style="padding:20px 24px;" id="modal-full-cuerpo">
      <p style="margin:0 0 12px; font-size:.9rem; color:#475569;" id="modal-full-intro">
        Esta unidad ya tiene un viaje sencillo en curso con el mismo operador.
        Al guardar se unirán en un solo viaje Full.
      </p>
      <table style="width:100%; border-collapse:collapse; font-size:.85rem;">
        <thead>
          <tr style="text-align:left; color:#64748b;">
            <th style="padding:6px 8px;">&nbsp;</th>
            <th style="padding:6px 8px;">Cliente</th>
            <th style="padding:6px 8px;">CP destino</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style="padding:6px 8px; font-weight:600;">Contenedor 1</td>
            <td style="padding:6px 8px;" id="modal-full-c1-cliente">—</td>
            <td style="padding:6px 8px;" id="modal-full-c1-cp">—</td>
          </tr>
          <tr>
            <td style="padding:6px 8px; font-weight:600;">Contenedor 2</td>
            <td style="padding:6px 8px;" id="modal-full-c2-cliente">—</td>
            <td style="padding:6px 8px;" id="modal-full-c2-cp">—</td>
          </tr>
        </tbody>
      </table>
      <p style="margin:12px 0 0; font-size:.85rem; color:#0f172a;" id="modal-full-tipo"></p>
    </div>
    <div style="padding:16px 24px; border-top:1px solid #f1f5f9; display:flex; gap:10px; justify-content:flex-end;">
      <button type="button" id="modal-full-cancelar"
              style="padding:8px 16px; border:1px solid #cbd5e1; border-radius:8px; background:#fff;
                     font-size:.85rem; color:#475569;">Cancelar</button>
      <button type="button" id="modal-full-confirmar"
              style="padding:8px 16px; border:0; border-radius:8px; background:#059669;
                     font-size:.85rem; color:#fff; font-weight:600;">Generar Full</button>
    </div>
  </div>
</div>

<!-- Modal: unidad bloqueada -->
<div id="modal-full-bloqueo" style="display:none; position:fixed; inset:0; z-index:60;
     background:rgba(15,23,42,.55);">
  <div style="max-width:460px; margin:12vh auto 0; background:#fff; border-radius:14px;
       box-shadow:0 20px 60px rgba(0,0,0,.25); padding:24px;">
    <h3 style="margin:0 0 10px; font-size:1.05rem; font-weight:700; color:#b91c1c;">No se puede registrar</h3>
    <p style="margin:0 0 18px; font-size:.9rem; color:#475569;" id="modal-full-bloqueo-msg"></p>
    <div style="text-align:right;">
      <button type="button" id="modal-full-bloqueo-ok"
              style="padding:8px 16px; border:0; border-radius:8px; background:#0f172a; color:#fff; font-size:.85rem;">
        Entendido</button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Add interception JS**

En `templates/bitacoras/bitacora_form.html`, dentro del bloque `{% block extra_js %}`, **antes** de `</script>` final (tras el listener de submit que re-habilita `operadorSelect`):

```javascript
// ─────────────────────────────────────────────────────────────
// Detección de "generar Full" (dos sencillos misma unidad + operador)
// ─────────────────────────────────────────────────────────────
const VERIFICAR_FULL_URL = "{% url 'bitacoras:verificar_full' %}";
const formBitacora   = document.getElementById('bitacoraForm');
const clienteSelect  = document.getElementById('id_cliente');
const cpDestinoInput = document.getElementById('id_cp_destino');
const modalFull      = document.getElementById('modal-generar-full');
const modalBloqueo   = document.getElementById('modal-full-bloqueo');
const EXCLUIR_PK      = "{{ object.pk|default:'' }}";
let fullCheckPassed  = false;

function cerrarModalesFull() {
    modalFull.style.display = 'none';
    modalBloqueo.style.display = 'none';
}

document.getElementById('modal-full-cancelar').addEventListener('click', cerrarModalesFull);
document.getElementById('modal-full-bloqueo-ok').addEventListener('click', cerrarModalesFull);

document.getElementById('modal-full-confirmar').addEventListener('click', function () {
    let hidden = formBitacora.querySelector('input[name="confirmar_full"]');
    if (!hidden) {
        hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'confirmar_full';
        formBitacora.appendChild(hidden);
    }
    hidden.value = '1';
    fullCheckPassed = true;
    cerrarModalesFull();
    formBitacora.requestSubmit();
});

formBitacora.addEventListener('submit', function (e) {
    if (fullCheckPassed) return;
    if (!modalidadSelect || modalidadSelect.value !== 'SENCILLO') return;

    const unidadId = unidadSelect.value;
    const operadorId = operadorSelect.value;
    if (!unidadId || !operadorId) return;

    e.preventDefault();

    const params = new URLSearchParams({
        unidad: unidadId,
        operador: operadorId,
        cliente: clienteSelect ? (clienteSelect.value || '') : '',
        cp_destino: cpDestinoInput ? (cpDestinoInput.value || '') : '',
    });
    if (EXCLUIR_PK) params.append('excluir_pk', EXCLUIR_PK);

    fetch(VERIFICAR_FULL_URL + '?' + params.toString(), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
        .then(r => r.json())
        .then(data => {
            if (data.accion === 'ninguna') {
                fullCheckPassed = true;
                formBitacora.requestSubmit();
                return;
            }
            if (data.accion === 'bloqueo') {
                document.getElementById('modal-full-bloqueo-msg').textContent = data.mensaje;
                modalBloqueo.style.display = 'block';
                return;
            }
            // ofrecer_full
            document.getElementById('modal-full-c1-cliente').textContent = data.sencillo.cliente || '—';
            document.getElementById('modal-full-c1-cp').textContent = data.sencillo.cp_destino || '—';
            document.getElementById('modal-full-c2-cliente').textContent = data.nuevo.cliente || '—';
            document.getElementById('modal-full-c2-cp').textContent = data.nuevo.cp_destino || '—';
            document.getElementById('modal-full-tipo').textContent =
                data.tipo_full === 'reparto'
                    ? 'Se generará un Full con reparto (dos destinos distintos).'
                    : 'Se generará un Full directo (mismo cliente y destino).';
            modalFull.style.display = 'block';
        })
        .catch(() => {
            fullCheckPassed = true;
            formBitacora.requestSubmit();
        });
});
```

- [ ] **Step 5: Run the smoke test + manual check**

Run: `python manage.py test modulos.bitacoras.tests_full.BitacoraFormModalMarkupTests --keepdb --noinput`
Expected: PASS

Manual: `python manage.py runserver`, ir a `/bitacoras/crear/`, crear un sencillo con unidad U + operador O; luego crear otro sencillo con U + O → al "Guardar" aparece el modal con la comparación. "Generar Full" → redirige al detalle del viaje ahora FULL. Repetir con distinto operador → modal de bloqueo.

- [ ] **Step 6: Commit**

```bash
git add templates/bitacoras/bitacora_form.html modulos/bitacoras/tests_full.py
git commit -m "Full desde sencillos: modal en el alta/edicion manual de bitacora"
```

---

## Task 10: Modal en `enviar_a_bitacora.html` (modulación)

**Files:**
- Modify: `templates/modulacion/enviar_a_bitacora.html`
- Test: `modulos/modulacion/tests.py` (smoke, dentro de `EnviarABitacoraViewTests`)

**Interfaces:**
- Consumes: endpoint `bitacoras:verificar_full`; el form de modulación siempre es modalidad SENCILLO; campos con id por defecto `id_operador`, `id_unidad`, `id_cp_destino`; no hay campo cliente (se pasa `modulacion.cliente.pk` desde el contexto).
- Produces: mismo modal e interceptación; "Generar Full" agrega `confirmar_full=1` y reenvía.

- [ ] **Step 1: Write the smoke test**

Añadir a `EnviarABitacoraViewTests` en `modulos/modulacion/tests.py`:

```python
    def test_form_incluye_modal_generar_full(self):
        url = reverse('modulacion:enviar_a_bitacora', kwargs={'pk': self.modulacion.pk})
        r = self.client.get(url)
        self.assertContains(r, 'id="modal-generar-full"')
        self.assertContains(r, '/bitacoras/ajax/verificar-full/')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test modulos.modulacion.tests.EnviarABitacoraViewTests.test_form_incluye_modal_generar_full --keepdb --noinput`
Expected: FAIL — el marcado no está.

- [ ] **Step 3: Add modal markup + JS**

En `templates/modulacion/enviar_a_bitacora.html`, **antes** de `{% endblock %}` (cierre de `content`), añadir el **mismo marcado** de los dos modales de la Task 9 (`#modal-generar-full` y `#modal-full-bloqueo`) — copiar íntegro ese HTML.

Luego, al final del archivo, añadir un bloque nuevo:

```html
{% block extra_js %}
<script>
const VERIFICAR_FULL_URL = "{% url 'bitacoras:verificar_full' %}";
const MODULACION_CLIENTE_ID = "{{ modulacion.cliente.pk|default:'' }}";
const formEnviar     = document.querySelector('form[method="post"]');
const unidadSelect   = document.getElementById('id_unidad');
const operadorSelect = document.getElementById('id_operador');
const cpDestinoInput = document.getElementById('id_cp_destino');
const modalFull      = document.getElementById('modal-generar-full');
const modalBloqueo   = document.getElementById('modal-full-bloqueo');
let fullCheckPassed  = false;

function cerrarModalesFull() {
    modalFull.style.display = 'none';
    modalBloqueo.style.display = 'none';
}
document.getElementById('modal-full-cancelar').addEventListener('click', cerrarModalesFull);
document.getElementById('modal-full-bloqueo-ok').addEventListener('click', cerrarModalesFull);

document.getElementById('modal-full-confirmar').addEventListener('click', function () {
    let hidden = formEnviar.querySelector('input[name="confirmar_full"]');
    if (!hidden) {
        hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'confirmar_full';
        formEnviar.appendChild(hidden);
    }
    hidden.value = '1';
    fullCheckPassed = true;
    cerrarModalesFull();
    formEnviar.requestSubmit();
});

formEnviar.addEventListener('submit', function (e) {
    if (fullCheckPassed) return;
    const unidadId = unidadSelect.value;
    const operadorId = operadorSelect.value;
    if (!unidadId || !operadorId) return;

    e.preventDefault();
    const params = new URLSearchParams({
        unidad: unidadId,
        operador: operadorId,
        cliente: MODULACION_CLIENTE_ID,
        cp_destino: cpDestinoInput ? (cpDestinoInput.value || '') : '',
    });
    fetch(VERIFICAR_FULL_URL + '?' + params.toString(), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
        .then(r => r.json())
        .then(data => {
            if (data.accion === 'ninguna') { fullCheckPassed = true; formEnviar.requestSubmit(); return; }
            if (data.accion === 'bloqueo') {
                document.getElementById('modal-full-bloqueo-msg').textContent = data.mensaje;
                modalBloqueo.style.display = 'block';
                return;
            }
            document.getElementById('modal-full-c1-cliente').textContent = data.sencillo.cliente || '—';
            document.getElementById('modal-full-c1-cp').textContent = data.sencillo.cp_destino || '—';
            document.getElementById('modal-full-c2-cliente').textContent = data.nuevo.cliente || '—';
            document.getElementById('modal-full-c2-cp').textContent = data.nuevo.cp_destino || '—';
            document.getElementById('modal-full-tipo').textContent =
                data.tipo_full === 'reparto'
                    ? 'Se generará un Full con reparto (dos destinos distintos).'
                    : 'Se generará un Full directo (mismo cliente y destino).';
            modalFull.style.display = 'block';
        })
        .catch(() => { fullCheckPassed = true; formEnviar.requestSubmit(); });
});
</script>
{% endblock %}
```

Verificar que `base.html` define el bloque `extra_js` (lo usa `bitacora_form.html`, así que existe).

- [ ] **Step 4: Run the smoke test + manual check**

Run: `python manage.py test modulos.modulacion.tests.EnviarABitacoraViewTests.test_form_incluye_modal_generar_full --keepdb --noinput`
Expected: PASS

Manual: con un sencillo foráneo en curso (unidad U + operador O), enviar a bitácora una Modulación en Patio Esperanza eligiendo U + O → modal → "Generar Full" → la Modulación queda ligada al FULL y no se crea un 2º viaje.

- [ ] **Step 5: Commit**

```bash
git add templates/modulacion/enviar_a_bitacora.html modulos/modulacion/tests.py
git commit -m "Full desde sencillos: modal en Enviar a Bitacora de modulacion"
```

---

## Task 11: Regresión completa y cierre

**Files:** ninguno (verificación).

- [ ] **Step 1: Suite de bitácoras y modulación**

Run: `python manage.py test modulos.bitacoras modulos.modulacion --keepdb --noinput`
Expected: PASS salvo fallos preexistentes ya documentados:
- `modulos.modulacion.tests.ModulacionListViewFilterTests.test_permite_filtrar_por_mes_y_anio_explicito` (sensible a fecha).
- Hasta 4 fallos previos en `modulos.bitacoras` no relacionados con este cambio.
Confirmar que **no hay fallos nuevos** atribuibles a este trabajo.

- [ ] **Step 2: `check` de Django**

Run: `python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 3: Actualizar CLAUDE.md**

En `CLAUDE.md`, sección "Key Patterns" → "Model Save Overrides" o cerca de la tabla de módulos, añadir una nota:

```markdown
### Fusión de Sencillos en Full (`modulos/bitacoras/services_full.py`)
- Al guardar/editar un viaje `SENCILLO` cuya unidad ya tiene otro `SENCILLO` en curso con el **mismo operador**, se ofrece (modal JS + endpoint `bitacoras:verificar_full`) fusionarlos en un `FULL`: `directo` si coinciden cliente y `cp_destino`, `reparto` si difieren.
- Capacidad por unidad: máx. 2 contenedores en curso (SENCILLO=1, FULL=2). Unidad llena → fuera del selector.
- Aplica a alta manual, edición y `EnviarABitacoraView` de modulación (esta liga la Modulación al FULL sin crear un 2º `BitacoraViaje`). La carga masiva no pasa por aquí.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "Full desde sencillos: documentar en CLAUDE.md"
```

---

## Self-Review

**1. Spec coverage:**

| Requisito del spec | Task |
|---|---|
| "En curso" = `completado=False`; carga 1/2 por modalidad | Task 1 |
| Capacidad máx 2, `unidad_bloqueada`, ids bloqueadas para selectores | Task 1, Task 5, Task 8 |
| Emparejamiento SENCILLO + unidad + operador + en curso | Task 2 |
| Bloqueo por operador distinto (mensaje) | Task 2, Task 4, Task 8 |
| Bloqueo por unidad 2/2 (mensaje) | Task 2, Task 4 |
| Tipo de Full automático (directo/reparto por cliente + CP) | Task 2 |
| `cliente` nulo: dos nulos = iguales | Task 2 (`_mismo_destino`) |
| `fusionar_en_full` (campos copiados, conserva contenedor 1, recalcula Maps si reparto) | Task 3 |
| Endpoint `verificar_full` con contrato JSON | Task 4 |
| Selector de unidad filtra bloqueadas (form manual) | Task 5 |
| `confirmar_full` + `clean()` red de seguridad | Task 5 |
| `BitacoraCreateView`: fusiona con confirmación, no crea 2º registro | Task 6 |
| `BitacoraUpdateView`: fusiona en el otro y borra el editado; `excluir_pk` | Task 5 (form), Task 7 |
| Modulación: filtra unidad, liga al FULL, no crea 2º `BitacoraViaje` | Task 8 |
| Modulación: `reparto` según cliente/CP; `sellos_2=''` | Task 8 |
| Modal JS como la imagen (alta manual + modulación) | Task 9, Task 10 |
| Modal de bloqueo simple | Task 9, Task 10 |
| Fusión atómica (`transaction.atomic`) | Task 3 usa full_clean; envoltura en Task 6/7/8 |
| Casos borde: fetch falla → submit normal; sencillo desaparece → revalida `ninguna` | Task 9/10 (catch), Task 6 (`fusion_result` recomputado en `clean` en cada request) |
| Carga masiva intacta | No se toca (sin task) — verificado en Task 11 regresión |
| Fuera de alcance: capacidad por operador, deshacer Full, LOCAL/LOCAL_FULL | No implementado (correcto) |

Sin huecos.

**2. Placeholder scan:** Sin "TBD"/"TODO"/"handle edge cases". Todos los pasos de código llevan el código completo.

**3. Type consistency:**
- `evaluar_fusion(unidad, operador, cliente, cp_destino, *, excluir_pk=None)` — misma firma en Task 2 (def), Task 4 (endpoint), Task 5 (form), Task 8 (vista). ✓
- `fusionar_en_full(sencillo_existente, datos_segundo, *, tipo_full)` con `datos_segundo` = `{contenedor, peso, sellos, cliente, cp_destino}` — igual en Task 3 (def), Task 6, Task 7, Task 8. ✓
- Dict de retorno `{'accion': 'ninguna'|'bloqueo'|'ofrecer_full', ...}` con `sencillo` y `tipo_full` en `ofrecer_full` — consistente en todas las tasks. ✓
- `form.fusion_result` inicializado en `__init__` (Task 5) y leído en Task 6/7. ✓
- `unidades_bloqueadas_ids(*, excluir_pk=None) -> set` — Task 1 (def), Task 5, Task 8. ✓
- IDs de elementos del modal (`modal-generar-full`, `modal-full-bloqueo`, `modal-full-confirmar`, `modal-full-cancelar`, `modal-full-bloqueo-ok`, `modal-full-bloqueo-msg`, `modal-full-c1-cliente`, `modal-full-c1-cp`, `modal-full-c2-cliente`, `modal-full-c2-cp`, `modal-full-tipo`) — idénticos en Task 9 y Task 10. ✓

Sin inconsistencias.
