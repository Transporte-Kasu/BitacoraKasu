# Flujo de estados de Modulación + vista "Atención a Clientes" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la lectura de citas LCTPC deje de asignar FULL (todo SENCILLO), y que `Modulacion` gane un flujo de estados aduanal (ASIGNADO → INGRESADO → DESADUANAMIENTO_LIBRE / RECONOCIMIENTO_ADUANAL → …) con historial y un tablero "Atención a Clientes".

**Architecture:** Todo en `modulos/modulacion/`. La lógica de estados vive en `models.py` (constante `TRANSICIONES_MODULACION` + método `Modulacion.transicionar()` + modelo `SeguimientoModulacion`). Las vistas que cambian estado (nuevas y existentes) pasan por `transicionar()`. El tablero es una vista server-rendered con POST normales; un parcial de plantilla reutilizable dibuja los botones de transición válidos.

**Tech Stack:** Django 5.2.7, Python 3.12 (`.venvKasu`), SQLite en tests, Tailwind (clases utilitarias ya en `base.html`).

## Global Constraints

- Django `5.2.7`; ejecutar todo con `.venvKasu/bin/python`.
- Pruebas: `.venvKasu/bin/python manage.py test <ruta> --settings=test_settings` (SQLite en memoria). No hay pytest.
- Idioma español en nombres de modelo/campo, `verbose_name`, comentarios y textos de UI.
- `TIME_ZONE = 'America/Mexico_City'`; los `DateTimeField` se guardan aware con `django.utils.timezone`.
- Vistas con `LoginRequiredMixin` (CBV) o `@login_required` (FBV). Acceso a Atención a Clientes y a las transiciones: **solo login**, sin permiso nuevo.
- El flujo de estados aplica a **todas** las modulaciones sin importar `origen`.
- Los tests nuevos de estados van en `modulos/modulacion/tests_estados.py` (archivo nuevo). No crear paquete `tests/` (existe `tests.py`). Los cambios de la Parte A se prueban dentro de `tests_lctpc.py`.
- `MODULADO` se conserva como choice **legacy**: ningún flujo nuevo lo asigna, pero no se borra (hay filas históricas).
- El `estado` nuevo `VERIFICACION_EN_TRANSPORTE` mide 26 caracteres → `Modulacion.estado.max_length` debe ser `30`.

### Mapa de transiciones (referencia, se implementa en Task 2)

```
PENDIENTE            -> ASIGNADO                         (automática al asignar unidad+operador)
MODULADO             -> ASIGNADO                         (legacy)
ASIGNADO             -> INGRESADO
INGRESADO            -> DESADUANAMIENTO_LIBRE | RECONOCIMIENTO_ADUANAL
DESADUANAMIENTO_LIBRE-> VERIFICACION_EN_TRANSPORTE | EN_PATIO_ESPERANZA
RECONOCIMIENTO_ADUANAL-> RETENIDO | EN_PATIO_ESPERANZA
RETENIDO             -> EN_PATIO_ESPERANZA
VERIFICACION_EN_TRANSPORTE -> EN_PATIO_ESPERANZA
EN_PATIO_ESPERANZA   -> ENVIADO_BITACORA | RETIRADO_TERCERO
ENVIADO_BITACORA / RETIRADO_TERCERO -> (terminales)
```

---

## Estructura de archivos

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `modulos/modulacion/services_lctpc.py` | Modificar | quitar `clasificar()` y los imports `uuid` / `OrderedDict` que sólo usaba |
| `modulos/modulacion/services_importacion.py` | Modificar | quitar import y llamada a `clasificar()`; `_procesar_renglon` fija `SENCILLO`/`''` |
| `modulos/modulacion/models.py` | Modificar | `ESTADO_CHOICES`, `estado.max_length=30`, `TRANSICIONES_MODULACION`, `ESTADOS_EN_SEGUIMIENTO`, `TransicionInvalida`, `Modulacion.transicionar()`, `Modulacion.badge_class`, modelo `SeguimientoModulacion` |
| `modulos/modulacion/migrations/0008_estados_seguimiento.py` | Crear (auto) | `AlterField` de `estado` + `CreateModel` `SeguimientoModulacion` |
| `modulos/modulacion/views.py` | Modificar | Create/Update sin `MODULADO`; `AsignarUnidadOperadorView` auto-ASIGNADO; `enviar_a_patio_esperanza` / `retirar_de_patio` / `EnviarABitacoraView` → `transicionar()`; `AtencionClientesView`; `avanzar_estado_modulacion` |
| `modulos/modulacion/urls.py` | Modificar | rutas `atencion_clientes` y `avanzar_estado` |
| `modulos/modulacion/admin.py` | Modificar | inline read-only de `SeguimientoModulacion` en `ModulacionAdmin` + registro propio read-only |
| `templates/modulacion/_botones_transicion.html` | Crear | parcial: un `<form>` POST por cada transición válida de `modulacion` |
| `templates/modulacion/atencion_clientes.html` | Crear | tablero por estado con filtros |
| `templates/modulacion/dashboard.html` | Modificar | enlace "Atención a Clientes" en `.dash-page-actions` |
| `templates/modulacion/modulacion_list.html` | Modificar | chip de estado usa `m.badge_class` |
| `templates/modulacion/modulacion_detail.html` | Modificar | quitar botón "Enviar a Patio" de PENDIENTE/MODULADO; línea de tiempo de `seguimientos`; incluir el parcial de transiciones |
| `modulos/modulacion/tests_estados.py` | Crear | todas las pruebas de la Parte B |
| `modulos/modulacion/tests_lctpc.py` | Modificar | quitar `ClasificarTests` + helper `_renglon`; ajustar aserciones `tipo_cita`; test nuevo "no asigna FULL" |

---

## Task 1: Parte A — LCTPC deja de asignar FULL

**Files:**
- Modify: `modulos/modulacion/services_lctpc.py`
- Modify: `modulos/modulacion/services_importacion.py`
- Modify: `modulos/modulacion/tests_lctpc.py`

**Interfaces:**
- Consumes: `parsear_programacion`, `RenglonLCTPC` (sin cambio).
- Produces: `services_lctpc` ya **no** exporta `clasificar`. `services_importacion._procesar_renglon(r, terminal, fecha, agencia_defecto)` fija en la `Modulacion` `tipo_cita='SENCILLO'`, `grupo_cita=''` (ignora `r.tipo_cita`/`r.grupo_cita`).

- [ ] **Step 1: Ajustar los tests de `tests_lctpc.py` (quedan en rojo)**

En `modulos/modulacion/tests_lctpc.py`:

1. En la línea de import (actual):
```python
from .services_lctpc import (
    ErrorParseoLCTPC, RenglonLCTPC, clasificar, parsear_programacion,
)
```
déjala en:
```python
from .services_lctpc import ErrorParseoLCTPC, parsear_programacion
```
(Si `RenglonLCTPC` no se usa en el resto del archivo tras borrar `ClasificarTests`, quítalo también. Verifica con: `grep -n RenglonLCTPC modulos/modulacion/tests_lctpc.py`.)

2. Borra por completo el helper `_renglon(...)` (def a partir de la línea ~119) y la clase `class ClasificarTests(SimpleTestCase):` entera (incluye `test_seis_con_misma_hora_dan_tres_full`, `test_cinco_dan_dos_full_y_un_sencillo`, `test_uno_solo_es_sencillo`, `test_archivo_real_da_3_full_y_4_sencillo`).

3. En `ImportarProgramacionesTests.test_actualiza_modulacion_existente`, cambia:
```python
        self.assertEqual(m.tipo_cita, 'FULL')
        self.assertTrue(m.grupo_cita)
```
por:
```python
        self.assertEqual(m.tipo_cita, 'SENCILLO')
        self.assertEqual(m.grupo_cita, '')
```

4. En `ImportacionLCTPCViewsTests.test_detalle_renderiza_filas`, en el `detalle=[{...}]`, cambia `'tipo_cita': 'FULL'` por `'tipo_cita': 'SENCILLO'`.

5. Añade a `ImportarProgramacionesTests` (usa los helpers ya existentes de esa clase):
```python
    def test_lctpc_nunca_asigna_full(self):
        # El fixture tiene horarios repetidos (antes daba 6 FULL / 4 SENCILLO).
        self._patch_graph()
        importar_programaciones_lctpc()
        ms = Modulacion.objects.filter(origen='LCTPC')
        self.assertEqual(ms.count(), 10)
        self.assertTrue(all(m.tipo_cita == 'SENCILLO' for m in ms))
        self.assertTrue(all(m.grupo_cita == '' for m in ms))
        imp = ImportacionProgramacionLCTPC.objects.get(graph_message_id='m1')
        self.assertTrue(all(d['tipo_cita'] == 'SENCILLO' for d in imp.detalle))
```

- [ ] **Step 2: Correr — deben fallar por `ImportError` de `clasificar`**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc --settings=test_settings`
Expected: FAIL — `ImportError: cannot import name 'clasificar'` ya no aplica (lo quitaste del import), pero `services_importacion.py` todavía importa `clasificar` → `ImportError` al cargar el módulo de tests. También `test_lctpc_nunca_asigna_full` fallaría porque hoy sí asigna FULL.

- [ ] **Step 3: Quitar `clasificar()` de `services_lctpc.py`**

En `modulos/modulacion/services_lctpc.py`:

1. Borra la función `def clasificar(renglones: list[RenglonLCTPC]) -> list[RenglonLCTPC]:` completa (hasta su `return renglones`).
2. En los imports del encabezado, quita las líneas que sólo usaba `clasificar`:
```python
import uuid
from collections import OrderedDict
```
(Deja `import datetime`, `import re`, `from dataclasses import dataclass, field`, `from bs4 import BeautifulSoup`.)
3. Verifica que `uuid` / `OrderedDict` no se usen en otro lado del archivo:
`grep -nE 'uuid|OrderedDict' modulos/modulacion/services_lctpc.py` → sin resultados.

- [ ] **Step 4: Quitar `clasificar` de `services_importacion.py` y forzar SENCILLO**

En `modulos/modulacion/services_importacion.py`:

1. Import (actual):
```python
from .services_lctpc import clasificar, parsear_programacion
```
déjalo en:
```python
from .services_lctpc import parsear_programacion
```

2. En `_procesar_correo`, borra la línea:
```python
        clasificar(prog.renglones)
```

3. En `_procesar_renglon`, en la rama de actualización (`if m:`), cambia:
```python
        m.tipo_cita = r.tipo_cita
        m.grupo_cita = r.grupo_cita
```
por:
```python
        m.tipo_cita = 'SENCILLO'
        m.grupo_cita = ''
```

4. En la misma función, rama `else:` (`Modulacion.objects.create(...)`), cambia:
```python
            tipo_cita=r.tipo_cita,
            grupo_cita=r.grupo_cita,
```
por:
```python
            tipo_cita='SENCILLO',
            grupo_cita='',
```

5. En el `return {...}` de `_procesar_renglon`, cambia:
```python
        'tipo_cita': r.tipo_cita,
```
por:
```python
        'tipo_cita': 'SENCILLO',
```

- [ ] **Step 5: Correr — verde**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc --settings=test_settings`
Expected: PASS. (El total baja ~4 tests por `ClasificarTests` borrada y sube 1 por `test_lctpc_nunca_asigna_full`.)

- [ ] **Step 6: Regresión del módulo**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion --settings=test_settings`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add modulos/modulacion/services_lctpc.py modulos/modulacion/services_importacion.py modulos/modulacion/tests_lctpc.py
git commit -m "feat(modulacion): LCTPC deja de asignar FULL — todas las citas quedan SENCILLO

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0181M3c92rVYQawQxK2fgyFv"
```

---

## Task 2: Parte B — estados, mapa, `transicionar()`, `SeguimientoModulacion`, `badge_class`

**Files:**
- Modify: `modulos/modulacion/models.py`
- Create: `modulos/modulacion/migrations/0008_estados_seguimiento.py` (auto)
- Create: `modulos/modulacion/tests_estados.py`

**Interfaces:**
- Produces:
  - `modulos.modulacion.models.TRANSICIONES_MODULACION: dict[str, list[str]]`
  - `modulos.modulacion.models.ESTADOS_EN_SEGUIMIENTO: list[str]`
  - `modulos.modulacion.models.TransicionInvalida(Exception)`
  - `Modulacion.transicionar(nuevo_estado: str, *, usuario=None, nota: str = '') -> None` — valida contra el mapa (si no, `TransicionInvalida`), fija `estado`, sella `fecha_patio_esperanza` / `fecha_retiro` la primera vez, `save()`, y crea 1 `SeguimientoModulacion`. Todo en `transaction.atomic()`.
  - `Modulacion.badge_class -> str` (property) — clase Tailwind del chip por estado.
  - `SeguimientoModulacion(modulacion FK→Modulacion related_name='seguimientos', estado, usuario FK→User null, nota, creado_en)` — `Meta.ordering = ['creado_en']`.
  - `Modulacion.ESTADO_CHOICES` con las 11 claves (ver Global Constraints / mapa).

- [ ] **Step 1: Escribir `tests_estados.py` (falla)**

Crear `modulos/modulacion/tests_estados.py`:

```python
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from modulos.modulacion.models import (
    Agencia, Modulacion, SeguimientoModulacion, TerminalPortuaria,
    TransicionInvalida, TRANSICIONES_MODULACION,
)


def _modulacion(estado='PENDIENTE', **kw):
    return Modulacion.objects.create(
        agencia=Agencia.objects.get_or_create(nombre='LOGINCO')[0],
        terminal_portuaria=TerminalPortuaria.objects.get_or_create(nombre='LCTPC')[0],
        tipo_contenedor='40HC', peso_toneladas=Decimal('18.5'),
        contenedor='ABCU1234567', estado=estado, **kw,
    )


class TransicionarTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')

    def test_transicion_valida_cambia_estado_y_deja_seguimiento(self):
        m = _modulacion(estado='ASIGNADO')
        m.transicionar('INGRESADO', usuario=self.user, nota='ok')
        m.refresh_from_db()
        self.assertEqual(m.estado, 'INGRESADO')
        seg = SeguimientoModulacion.objects.get(modulacion=m)
        self.assertEqual(seg.estado, 'INGRESADO')
        self.assertEqual(seg.usuario, self.user)
        self.assertEqual(seg.nota, 'ok')

    def test_transicion_invalida_no_cambia_nada(self):
        m = _modulacion(estado='ASIGNADO')
        with self.assertRaises(TransicionInvalida):
            m.transicionar('EN_PATIO_ESPERANZA')
        m.refresh_from_db()
        self.assertEqual(m.estado, 'ASIGNADO')
        self.assertEqual(SeguimientoModulacion.objects.count(), 0)

    def test_en_patio_esperanza_sella_fecha_una_sola_vez(self):
        m = _modulacion(estado='RETENIDO')
        m.transicionar('EN_PATIO_ESPERANZA', usuario=self.user)
        m.refresh_from_db()
        primera = m.fecha_patio_esperanza
        self.assertIsNotNone(primera)
        # volver a entrar (desde otro camino) no re-sella
        m.estado = 'VERIFICACION_EN_TRANSPORTE'
        m.save(update_fields=['estado'])
        m.transicionar('EN_PATIO_ESPERANZA', usuario=self.user)
        m.refresh_from_db()
        self.assertEqual(m.fecha_patio_esperanza, primera)

    def test_retirado_tercero_sella_fecha_retiro(self):
        m = _modulacion(estado='EN_PATIO_ESPERANZA')
        m.transicionar('RETIRADO_TERCERO', usuario=self.user)
        m.refresh_from_db()
        self.assertIsNotNone(m.fecha_retiro)

    def test_mapa_cubre_todos_los_estados(self):
        claves = {c[0] for c in Modulacion.ESTADO_CHOICES}
        self.assertEqual(set(TRANSICIONES_MODULACION), claves)


class BadgeClassTests(TestCase):
    def test_badge_class_por_estado(self):
        casos = {
            'PENDIENTE': 'gray', 'ASIGNADO': 'indigo', 'INGRESADO': 'blue',
            'DESADUANAMIENTO_LIBRE': 'green', 'RECONOCIMIENTO_ADUANAL': 'red',
            'RETENIDO': 'amber', 'VERIFICACION_EN_TRANSPORTE': 'purple',
            'EN_PATIO_ESPERANZA': 'green', 'ENVIADO_BITACORA': 'blue',
            'RETIRADO_TERCERO': 'gray',
        }
        for estado, color in casos.items():
            m = Modulacion(estado=estado)
            self.assertIn(color, m.badge_class, estado)
```

- [ ] **Step 2: Correr — falla por import**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_estados --settings=test_settings`
Expected: FAIL — `ImportError: cannot import name 'SeguimientoModulacion'` (y `TransicionInvalida`, `TRANSICIONES_MODULACION`).

- [ ] **Step 3: Editar `models.py` — choices, constantes, excepción**

En `modulos/modulacion/models.py`:

1. En los imports del encabezado, añade (si no está):
```python
from django.conf import settings
```

2. Reemplaza el bloque `ESTADO_CHOICES` de `class Modulacion` por:
```python
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de modulación'),
        ('MODULADO', 'Modulado'),
        ('ASIGNADO', 'Asignado / pendiente de ingreso'),
        ('INGRESADO', 'Ingresado'),
        ('DESADUANAMIENTO_LIBRE', 'Desaduanamiento libre (verde)'),
        ('RECONOCIMIENTO_ADUANAL', 'Reconocimiento aduanal (rojo)'),
        ('RETENIDO', 'Retenido (esperando aduana)'),
        ('VERIFICACION_EN_TRANSPORTE', 'Verificación en transporte'),
        ('EN_PATIO_ESPERANZA', 'En Patio Esperanza'),
        ('ENVIADO_BITACORA', 'Enviado a Bitácora de Viajes'),
        ('RETIRADO_TERCERO', 'Retirado por transporte externo'),
    ]
```

3. Cambia la definición del campo `estado`:
```python
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE', verbose_name="Estado")
```
a `max_length=30`:
```python
    estado = models.CharField(max_length=30, choices=ESTADO_CHOICES, default='PENDIENTE', verbose_name="Estado")
```

4. Justo **antes** de `class Modulacion(models.Model):`, añade a nivel de módulo:
```python
TRANSICIONES_MODULACION = {
    'PENDIENTE': ['ASIGNADO'],
    'MODULADO': ['ASIGNADO'],
    'ASIGNADO': ['INGRESADO'],
    'INGRESADO': ['DESADUANAMIENTO_LIBRE', 'RECONOCIMIENTO_ADUANAL'],
    'DESADUANAMIENTO_LIBRE': ['VERIFICACION_EN_TRANSPORTE', 'EN_PATIO_ESPERANZA'],
    'RECONOCIMIENTO_ADUANAL': ['RETENIDO', 'EN_PATIO_ESPERANZA'],
    'RETENIDO': ['EN_PATIO_ESPERANZA'],
    'VERIFICACION_EN_TRANSPORTE': ['EN_PATIO_ESPERANZA'],
    'EN_PATIO_ESPERANZA': ['ENVIADO_BITACORA', 'RETIRADO_TERCERO'],
    'ENVIADO_BITACORA': [],
    'RETIRADO_TERCERO': [],
}

# Estados que muestra el tablero de Atención a Clientes (ni iniciales ni terminales).
ESTADOS_EN_SEGUIMIENTO = [
    'ASIGNADO', 'INGRESADO', 'DESADUANAMIENTO_LIBRE', 'RECONOCIMIENTO_ADUANAL',
    'RETENIDO', 'VERIFICACION_EN_TRANSPORTE', 'EN_PATIO_ESPERANZA',
]

_BADGE_POR_ESTADO = {
    'PENDIENTE': 'bg-gray-100 text-gray-700',
    'MODULADO': 'bg-gray-100 text-gray-700',
    'ASIGNADO': 'bg-indigo-100 text-indigo-700',
    'INGRESADO': 'bg-blue-100 text-blue-700',
    'DESADUANAMIENTO_LIBRE': 'bg-green-100 text-green-700',
    'RECONOCIMIENTO_ADUANAL': 'bg-red-100 text-red-700',
    'RETENIDO': 'bg-amber-100 text-amber-700',
    'VERIFICACION_EN_TRANSPORTE': 'bg-purple-100 text-purple-700',
    'EN_PATIO_ESPERANZA': 'bg-green-100 text-green-700',
    'ENVIADO_BITACORA': 'bg-blue-100 text-blue-700',
    'RETIRADO_TERCERO': 'bg-gray-100 text-gray-700',
}


class TransicionInvalida(Exception):
    """Se intentó un cambio de estado que TRANSICIONES_MODULACION no permite."""
```

- [ ] **Step 4: `models.py` — `transicionar()` y `badge_class` en `Modulacion`**

Dentro de `class Modulacion`, después del método `save(...)`, añade:

```python
    @property
    def badge_class(self):
        """Clase Tailwind del chip de estado (para plantillas)."""
        return _BADGE_POR_ESTADO.get(self.estado, 'bg-gray-100 text-gray-700')

    def transicionar(self, nuevo_estado, *, usuario=None, nota=''):
        """Cambia de estado validando contra TRANSICIONES_MODULACION y deja
        una fila de SeguimientoModulacion. Lanza TransicionInvalida si el
        salto no está permitido desde el estado actual."""
        if nuevo_estado not in TRANSICIONES_MODULACION.get(self.estado, []):
            raise TransicionInvalida(
                f'{self.folio}: no se puede pasar de {self.estado} a {nuevo_estado}.'
            )
        with transaction.atomic():
            self.estado = nuevo_estado
            if nuevo_estado == 'EN_PATIO_ESPERANZA' and self.fecha_patio_esperanza is None:
                self.fecha_patio_esperanza = timezone.now()
            if nuevo_estado == 'RETIRADO_TERCERO' and self.fecha_retiro is None:
                self.fecha_retiro = timezone.now()
            self.save()
            SeguimientoModulacion.objects.create(
                modulacion=self, estado=nuevo_estado, usuario=usuario, nota=nota,
            )
```

- [ ] **Step 5: `models.py` — modelo `SeguimientoModulacion`**

Al final de `modulos/modulacion/models.py` (después de `ImportacionProgramacionLCTPC`):

```python
class SeguimientoModulacion(models.Model):
    """Historial de cambios de estado de una Modulación. Una fila por
    transición hecha vía `Modulacion.transicionar()`."""
    modulacion = models.ForeignKey(
        Modulacion, on_delete=models.CASCADE, related_name='seguimientos',
        verbose_name="Modulación",
    )
    estado = models.CharField(
        max_length=30, choices=Modulacion.ESTADO_CHOICES, verbose_name="Estado",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Usuario",
    )
    nota = models.TextField(blank=True, verbose_name="Nota")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Seguimiento de modulación"
        verbose_name_plural = "Seguimientos de modulación"
        ordering = ['creado_en']

    def __str__(self):
        return f"{self.modulacion.folio} → {self.get_estado_display()}"
```

- [ ] **Step 6: Migración**

```bash
.venvKasu/bin/python manage.py makemigrations modulacion --name estados_seguimiento
.venvKasu/bin/python manage.py migrate --settings=test_settings
```
Expected: crea `0008_estados_seguimiento.py` con un `AlterField` de `estado` y un `CreateModel` de `SeguimientoModulacion`; `migrate` sin errores.

- [ ] **Step 7: Correr — verde**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_estados --settings=test_settings -v 2`
Expected: PASS (7 tests).

- [ ] **Step 8: Regresión del módulo**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion --settings=test_settings`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add modulos/modulacion/models.py modulos/modulacion/migrations/0008_estados_seguimiento.py modulos/modulacion/tests_estados.py
git commit -m "feat(modulacion): estados aduanales, transicionar() y SeguimientoModulacion

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0181M3c92rVYQawQxK2fgyFv"
```

---

## Task 3: Parte B — auto ASIGNADO + rutas existentes por `transicionar()`

**Files:**
- Modify: `modulos/modulacion/views.py`
- Modify: `templates/modulacion/modulacion_detail.html`
- Modify: `modulos/modulacion/tests_estados.py`

**Interfaces:**
- Consumes: `Modulacion.transicionar()`, `TransicionInvalida`, `TRANSICIONES_MODULACION` (Task 2).
- Produces: sin API nueva; comportamiento — `AsignarUnidadOperadorView` promueve `PENDIENTE→ASIGNADO` cuando quedan unidad+operador; `enviar_a_patio_esperanza` / `retirar_de_patio` / `EnviarABitacoraView` usan `transicionar()` y por tanto respetan el mapa y dejan historial.

- [ ] **Step 1: Tests nuevos en `tests_estados.py` (fallan)**

Añade a `modulos/modulacion/tests_estados.py`:

```python
from django.urls import reverse

from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad


class AutoAsignadoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')
        self.client.force_login(self.user)
        self.unidad = Unidad.objects.create(numero_economico='E-1', tipo='LOCAL', activa=True)
        self.operador = Operador.objects.create(nombre='Juan', tipo='LOCAL', activo=True)

    def _post_asignar(self, m):
        return self.client.post(
            reverse('modulacion:asignar', args=[m.pk]),
            {'unidad': self.unidad.pk, 'operador': self.operador.pk},
        )

    def test_asignar_unidad_y_operador_promueve_pendiente_a_asignado(self):
        m = _modulacion(estado='PENDIENTE')
        self._post_asignar(m)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'ASIGNADO')
        self.assertIsNotNone(m.fecha_asignacion)
        seg = SeguimientoModulacion.objects.get(modulacion=m)
        self.assertEqual(seg.estado, 'ASIGNADO')
        self.assertEqual(seg.usuario, self.user)

    def test_reasignar_no_cambia_estado_si_ya_avanzo(self):
        m = _modulacion(estado='INGRESADO')
        self._post_asignar(m)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'INGRESADO')
        self.assertEqual(SeguimientoModulacion.objects.filter(modulacion=m).count(), 0)


class RutasExistentesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')
        self.client.force_login(self.user)

    def test_enviar_a_patio_desde_estado_valido_deja_historial(self):
        m = _modulacion(estado='DESADUANAMIENTO_LIBRE')
        self.client.post(reverse('modulacion:enviar_a_patio_esperanza', args=[m.pk]))
        m.refresh_from_db()
        self.assertEqual(m.estado, 'EN_PATIO_ESPERANZA')
        self.assertTrue(SeguimientoModulacion.objects.filter(
            modulacion=m, estado='EN_PATIO_ESPERANZA').exists())

    def test_enviar_a_patio_desde_estado_invalido_no_hace_nada(self):
        m = _modulacion(estado='ASIGNADO')
        resp = self.client.post(
            reverse('modulacion:enviar_a_patio_esperanza', args=[m.pk]), follow=True)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'ASIGNADO')
        self.assertContains(resp, 'no se puede pasar')

    def test_retiro_externo_desde_patio_deja_historial(self):
        m = _modulacion(estado='EN_PATIO_ESPERANZA')
        self.client.post(
            reverse('modulacion:retirar_de_patio', args=[m.pk]),
            {'transportista_externo': 'Fletes SA'},
        )
        m.refresh_from_db()
        self.assertEqual(m.estado, 'RETIRADO_TERCERO')
        self.assertEqual(m.transportista_externo, 'Fletes SA')
        self.assertTrue(SeguimientoModulacion.objects.filter(
            modulacion=m, estado='RETIRADO_TERCERO').exists())
```

> Nota: si `Unidad` / `Operador` requieren más campos obligatorios, ajústalos con lo mínimo que exija el modelo (revisa `modulos/unidades/models.py` y `modulos/operadores/models.py`).

- [ ] **Step 2: Correr — fallan**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_estados --settings=test_settings -v 2`
Expected: FAIL — `AutoAsignadoTests` (hoy `AsignarUnidadOperadorView` no cambia estado) y `RutasExistentesTests` (hoy no dejan `SeguimientoModulacion` y `enviar_a_patio` acepta cualquier estado).

- [ ] **Step 3: `views.py` — quitar `MODULADO` de Create/Update**

En `modulos/modulacion/views.py`:

1. `ModulacionCreateView.form_valid` — borra la línea:
```python
        modulacion.estado = 'MODULADO'
```
(queda `modulacion.origen = 'MANUAL'` y `modulacion.save()`).

2. `ModulacionUpdateView.form_valid` — borra el bloque:
```python
        if modulacion.estado == 'PENDIENTE':
            modulacion.estado = 'MODULADO'
```

- [ ] **Step 4: `views.py` — auto ASIGNADO en `AsignarUnidadOperadorView`**

En `AsignarUnidadOperadorView.form_valid`, deja el cuerpo así:
```python
    def form_valid(self, form):
        modulacion = form.save(commit=False)
        if modulacion.fecha_asignacion is None:
            modulacion.fecha_asignacion = timezone.now()
        modulacion.save()
        if (modulacion.estado == 'PENDIENTE'
                and modulacion.unidad_id and modulacion.operador_id):
            modulacion.transicionar('ASIGNADO', usuario=self.request.user)
        messages.success(self.request, f'Unidad y operador asignados a {modulacion.folio}.')
        return redirect(reverse('modulacion:detail', kwargs={'pk': modulacion.pk}))
```

Asegura el import en `views.py` (junto a `from .models import ...`):
```python
from .models import Agencia, Modulacion, TerminalPortuaria, TransicionInvalida
```
(`ImportacionProgramacionLCTPC` ya está importado en su propia línea; añade `TransicionInvalida` donde estén los demás nombres de `.models`.)

- [ ] **Step 5: `views.py` — `enviar_a_patio_esperanza` por `transicionar()`**

Reemplaza el cuerpo de `enviar_a_patio_esperanza` por:
```python
@login_required
@require_POST
def enviar_a_patio_esperanza(request, pk):
    modulacion = get_object_or_404(Modulacion, pk=pk)
    try:
        modulacion.transicionar('EN_PATIO_ESPERANZA', usuario=request.user)
    except TransicionInvalida as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'Modulación {modulacion.folio} enviada al Patio Esperanza.')
    return redirect(reverse('modulacion:detail', kwargs={'pk': modulacion.pk}))
```
(Conserva los decoradores `@login_required` / `@require_POST` tal como estén hoy.)

- [ ] **Step 6: `views.py` — `retirar_de_patio` rama externa por `transicionar()`**

En `retirar_de_patio`, dentro de `if form.is_valid():`, cambia:
```python
        modulacion.transportista_externo = form.cleaned_data['transportista_externo']
        modulacion.estado = 'RETIRADO_TERCERO'
        modulacion.fecha_retiro = timezone.now()
        modulacion.save()
        messages.success(request, f'Modulación {modulacion.folio} marcada como retirada por transporte externo.')
```
por:
```python
        modulacion.transportista_externo = form.cleaned_data['transportista_externo']
        modulacion.save(update_fields=['transportista_externo'])
        try:
            modulacion.transicionar('RETIRADO_TERCERO', usuario=request.user)
        except TransicionInvalida as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Modulación {modulacion.folio} marcada como retirada por transporte externo.')
```

- [ ] **Step 7: `views.py` — `EnviarABitacoraView` por `transicionar()`**

En `EnviarABitacoraView`, en los dos puntos donde hoy hace `modulacion.estado = 'ENVIADO_BITACORA'` seguido de `modulacion.save()` (aprox. líneas 297 y 322), reemplaza esas dos líneas por:
```python
                modulacion.transicionar('ENVIADO_BITACORA', usuario=request.user)
```
Si en alguno de esos puntos se asignan además `modulacion.bitacora_viaje` / `operador` / `unidad` antes del cambio de estado, deja esas asignaciones y su `modulacion.save()`, y llama a `transicionar('ENVIADO_BITACORA', ...)` **después** (el `save()` de `transicionar` persiste todo). El guard existente `if modulacion.estado != 'EN_PATIO_ESPERANZA'` se queda igual (coincide con el mapa).

- [ ] **Step 8: `modulacion_detail.html` — quitar el botón de patio inválido**

En `templates/modulacion/modulacion_detail.html`, borra el bloque:
```html
            {% if modulacion.estado == 'PENDIENTE' or modulacion.estado == 'MODULADO' %}
            <form method="post" action="{% url 'modulacion:enviar_a_patio_esperanza' modulacion.pk %}">
                {% csrf_token %}
                <button type="submit"
                        class="px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 transition">Enviar a Patio Esperanza</button>
            </form>
            {% endif %}
```
(La línea de tiempo y los botones de transición del detalle se agregan en Task 5.)

- [ ] **Step 9: Correr — verde**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_estados --settings=test_settings -v 2`
Expected: PASS.

- [ ] **Step 10: Regresión del módulo**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion --settings=test_settings`
Expected: PASS. (Si algún test viejo de `tests.py` asumía `Create/Update` → `MODULADO`, ajústalo a `PENDIENTE`.)

- [ ] **Step 11: Commit**

```bash
git add modulos/modulacion/views.py templates/modulacion/modulacion_detail.html modulos/modulacion/tests_estados.py
git commit -m "feat(modulacion): auto ASIGNADO y rutas de estado por transicionar()

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0181M3c92rVYQawQxK2fgyFv"
```

---

## Task 4: Parte B — vista "Atención a Clientes" + `avanzar_estado`

**Files:**
- Modify: `modulos/modulacion/views.py`
- Modify: `modulos/modulacion/urls.py`
- Create: `templates/modulacion/_botones_transicion.html`
- Create: `templates/modulacion/atencion_clientes.html`
- Modify: `templates/modulacion/dashboard.html`
- Modify: `modulos/modulacion/tests_estados.py`

**Interfaces:**
- Consumes: `Modulacion.transicionar()`, `TransicionInvalida`, `TRANSICIONES_MODULACION`, `ESTADOS_EN_SEGUIMIENTO` (Task 2).
- Produces:
  - URL `modulacion:atencion_clientes` (`atencion-clientes/`) → `AtencionClientesView` (GET, `LoginRequiredMixin`).
  - URL `modulacion:avanzar_estado` (`atencion-clientes/<int:pk>/avanzar/`) → `avanzar_estado_modulacion` (`@login_required @require_POST`); campos POST: `nuevo_estado`, `nota` (opcional), `next` (opcional, querystring de retorno).

- [ ] **Step 1: Tests en `tests_estados.py` (fallan)**

Añade a `modulos/modulacion/tests_estados.py`:

```python
class AtencionClientesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')
        self.client.force_login(self.user)

    def test_requiere_login(self):
        self.client.logout()
        resp = self.client.get(reverse('modulacion:atencion_clientes'))
        self.assertEqual(resp.status_code, 302)

    def test_lista_solo_estados_en_seguimiento(self):
        _modulacion(estado='PENDIENTE', contenedor='PEND1111111')
        m_seg = _modulacion(estado='INGRESADO', contenedor='INGR2222222')
        _modulacion(estado='ENVIADO_BITACORA', contenedor='ENVB3333333')
        resp = self.client.get(reverse('modulacion:atencion_clientes'))
        self.assertContains(resp, 'INGR2222222')
        self.assertNotContains(resp, 'PEND1111111')
        self.assertNotContains(resp, 'ENVB3333333')

    def test_muestra_botones_de_transiciones_validas(self):
        _modulacion(estado='INGRESADO', contenedor='INGR2222222')
        resp = self.client.get(reverse('modulacion:atencion_clientes'))
        # INGRESADO -> DESADUANAMIENTO_LIBRE | RECONOCIMIENTO_ADUANAL
        self.assertContains(resp, 'Desaduanamiento libre (verde)')
        self.assertContains(resp, 'Reconocimiento aduanal (rojo)')

    def test_avanzar_valido_mueve_y_deja_historial(self):
        m = _modulacion(estado='INGRESADO')
        resp = self.client.post(
            reverse('modulacion:avanzar_estado', args=[m.pk]),
            {'nuevo_estado': 'DESADUANAMIENTO_LIBRE', 'nota': 'verde'},
        )
        self.assertRedirects(resp, reverse('modulacion:atencion_clientes'))
        m.refresh_from_db()
        self.assertEqual(m.estado, 'DESADUANAMIENTO_LIBRE')
        seg = SeguimientoModulacion.objects.get(modulacion=m)
        self.assertEqual(seg.nota, 'verde')
        self.assertEqual(seg.usuario, self.user)

    def test_avanzar_invalido_no_cambia_nada(self):
        m = _modulacion(estado='INGRESADO')
        resp = self.client.post(
            reverse('modulacion:avanzar_estado', args=[m.pk]),
            {'nuevo_estado': 'EN_PATIO_ESPERANZA'}, follow=True,
        )
        m.refresh_from_db()
        self.assertEqual(m.estado, 'INGRESADO')
        self.assertContains(resp, 'no se puede pasar')

    def test_avanzar_solo_post(self):
        m = _modulacion(estado='INGRESADO')
        resp = self.client.get(reverse('modulacion:avanzar_estado', args=[m.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_filtro_por_estado(self):
        _modulacion(estado='INGRESADO', contenedor='INGR2222222')
        _modulacion(estado='RETENIDO', contenedor='RETE4444444')
        resp = self.client.get(reverse('modulacion:atencion_clientes'), {'estado': 'RETENIDO'})
        self.assertContains(resp, 'RETE4444444')
        self.assertNotContains(resp, 'INGR2222222')
```

- [ ] **Step 2: Correr — fallan**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_estados.AtencionClientesTests --settings=test_settings -v 2`
Expected: FAIL — `NoReverseMatch: 'atencion_clientes'`.

- [ ] **Step 3: `views.py` — imports y vistas nuevas**

En `modulos/modulacion/views.py`, deja el import de `.models` así (añade `ESTADOS_EN_SEGUIMIENTO` a lo que Task 3 ya dejó):
```python
from .models import (
    Agencia, ESTADOS_EN_SEGUIMIENTO, Modulacion, TerminalPortuaria, TransicionInvalida,
)
```
(`ImportacionProgramacionLCTPC` sigue en su propia línea de import, sin cambios.)
Añade `TemplateView` a la lista de imports de `django.views.generic` si no está.

Al final del archivo:
```python
class AtencionClientesView(LoginRequiredMixin, TemplateView):
    """Tablero de seguimiento aduanal: modulaciones desde ASIGNADO hasta
    EN_PATIO_ESPERANZA, agrupadas por estado, con botones de avance."""
    template_name = 'modulacion/atencion_clientes.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = (
            Modulacion.objects
            .filter(estado__in=ESTADOS_EN_SEGUIMIENTO)
            .select_related('cliente', 'unidad', 'operador', 'agencia', 'terminal_portuaria')
            .order_by('fecha_recepcion')
        )
        estado = self.request.GET.get('estado') or ''
        cliente = self.request.GET.get('cliente') or ''
        if estado in ESTADOS_EN_SEGUIMIENTO:
            qs = qs.filter(estado=estado)
        if cliente:
            qs = qs.filter(cliente_id=cliente)

        por_estado = []
        for clave in ESTADOS_EN_SEGUIMIENTO:
            grupo = [m for m in qs if m.estado == clave]
            if grupo:
                por_estado.append({
                    'clave': clave,
                    'label': dict(Modulacion.ESTADO_CHOICES)[clave],
                    'modulaciones': grupo,
                })
        ctx['grupos'] = por_estado
        ctx['estados_choices'] = [
            (c, dict(Modulacion.ESTADO_CHOICES)[c]) for c in ESTADOS_EN_SEGUIMIENTO
        ]
        ctx['filtro_estado'] = estado
        ctx['filtro_cliente'] = cliente
        ctx['querystring'] = self.request.GET.urlencode()
        return ctx


@login_required
@require_POST
def avanzar_estado_modulacion(request, pk):
    modulacion = get_object_or_404(Modulacion, pk=pk)
    nuevo_estado = request.POST.get('nuevo_estado', '')
    nota = request.POST.get('nota', '').strip()
    destino = request.POST.get('next') or reverse('modulacion:atencion_clientes')
    try:
        modulacion.transicionar(nuevo_estado, usuario=request.user, nota=nota)
    except TransicionInvalida as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f'{modulacion.folio}: {modulacion.get_estado_display()}.',
        )
    return redirect(destino)
```

- [ ] **Step 4: `urls.py` — 2 rutas**

En `modulos/modulacion/urls.py`, dentro de `urlpatterns`, antes del bloque `# API de recepción (HAL9MIL)`:
```python
    # Atención a Clientes (seguimiento aduanal)
    path('atencion-clientes/', views.AtencionClientesView.as_view(), name='atencion_clientes'),
    path('atencion-clientes/<int:pk>/avanzar/', views.avanzar_estado_modulacion, name='avanzar_estado'),
```

- [ ] **Step 5: Parcial `_botones_transicion.html`**

Crear `templates/modulacion/_botones_transicion.html`:
```html
{% comment %}
Espera en contexto: `modulacion` y (opcional) `next` (querystring de retorno).
Dibuja un form POST por cada transición válida desde el estado actual.
{% endcomment %}
<div class="flex flex-wrap items-center gap-2">
    {% for clave, label in modulacion.transiciones_validas %}
    <form method="post" action="{% url 'modulacion:avanzar_estado' modulacion.pk %}" class="flex items-center gap-1">
        {% csrf_token %}
        <input type="hidden" name="nuevo_estado" value="{{ clave }}">
        <input type="hidden" name="next" value="{{ next }}">
        <input type="text" name="nota" placeholder="nota (opcional)"
               class="hidden md:block text-xs border border-gray-200 rounded px-2 py-1">
        <button type="submit"
                class="px-3 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 transition min-h-[36px]">
            → {{ label }}
        </button>
    </form>
    {% empty %}
    <span class="text-xs text-gray-400">Sin transiciones</span>
    {% endfor %}
</div>
```

Para que `modulacion.transiciones_validas` exista, añade esta property a `class Modulacion` en `models.py` (junto a `badge_class`):
```python
    @property
    def transiciones_validas(self):
        """[(clave, label)] de los estados a los que se puede pasar ahora."""
        labels = dict(self.ESTADO_CHOICES)
        return [(c, labels[c]) for c in TRANSICIONES_MODULACION.get(self.estado, [])]
```

- [ ] **Step 6: `atencion_clientes.html`**

Crear `templates/modulacion/atencion_clientes.html`:
```html
{% extends "base.html" %}

{% block title %}Atención a Clientes{% endblock %}

{% block content %}
<div class="max-w-7xl mx-auto py-4 px-4 sm:py-6">
    <div class="dash-page-header">
        <div>
            <h1 class="dash-page-title">Atención a Clientes</h1>
            <p class="dash-page-subtitle">Seguimiento aduanal de modulaciones asignadas</p>
        </div>
    </div>

    <form method="get" class="mb-6 flex flex-wrap gap-3 items-end">
        <div>
            <label class="block text-xs font-semibold text-gray-500 mb-1">Estado</label>
            <select name="estado" class="border border-gray-200 rounded-lg px-3 py-2 text-sm">
                <option value="">Todos</option>
                {% for clave, label in estados_choices %}
                <option value="{{ clave }}" {% if clave == filtro_estado %}selected{% endif %}>{{ label }}</option>
                {% endfor %}
            </select>
        </div>
        <button type="submit"
                class="px-4 py-2 text-sm font-semibold rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700 min-h-[44px]">
            Filtrar
        </button>
        {% if querystring %}
        <a href="{% url 'modulacion:atencion_clientes' %}" class="text-sm text-emerald-700 py-2">Limpiar</a>
        {% endif %}
    </form>

    {% for grupo in grupos %}
    <section class="mb-8">
        <h2 class="text-sm font-bold text-gray-700 mb-3">
            {{ grupo.label }} <span class="text-gray-400 font-normal">({{ grupo.modulaciones|length }})</span>
        </h2>
        <div class="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {% for m in grupo.modulaciones %}
            <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
                <div class="flex items-center justify-between">
                    <a href="{% url 'modulacion:detail' m.pk %}" class="font-semibold text-gray-900 hover:underline">{{ m.folio }}</a>
                    <span class="inline-block px-2 py-0.5 text-xs font-semibold rounded-full {{ m.badge_class }}">{{ m.get_estado_display }}</span>
                </div>
                <p class="text-sm text-gray-600 mt-1">{{ m.contenedor }} · {{ m.cliente.nombre|default:"—" }}</p>
                <p class="text-xs text-gray-400 mt-0.5">
                    {{ m.unidad.numero_economico|default:"sin unidad" }} · {{ m.operador.nombre|default:"sin operador" }}
                </p>
                <div class="mt-3">
                    {% include "modulacion/_botones_transicion.html" with modulacion=m next=request.get_full_path %}
                </div>
            </div>
            {% endfor %}
        </div>
    </section>
    {% empty %}
    <div class="py-16 text-center text-gray-400">
        <p class="text-lg font-medium">Nada en seguimiento</p>
    </div>
    {% endfor %}
</div>
{% endblock %}
```

> `next=request.get_full_path` manda la URL completa de la página actual como campo oculto `next`; `avanzar_estado_modulacion` hace `redirect(destino)` y el usuario vuelve a donde estaba (tablero con su filtro, o el detalle). Si `next` llega vacío, cae al default `reverse('modulacion:atencion_clientes')`.

- [ ] **Step 7: `dashboard.html` — enlace**

En `templates/modulacion/dashboard.html`, dentro de `<div class="dash-page-actions">`, antes del enlace "Ver lista":
```html
            <a href="{% url 'modulacion:atencion_clientes' %}"
               class="inline-flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg font-semibold text-sm transition min-h-[44px]">
                Atención a Clientes
            </a>
```

- [ ] **Step 8: Correr — verde**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_estados --settings=test_settings -v 2`
Expected: PASS.

- [ ] **Step 9: Regresión del módulo**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion --settings=test_settings`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add modulos/modulacion/views.py modulos/modulacion/urls.py modulos/modulacion/models.py templates/modulacion/_botones_transicion.html templates/modulacion/atencion_clientes.html templates/modulacion/dashboard.html modulos/modulacion/tests_estados.py
git commit -m "feat(modulacion): tablero Atención a Clientes y avance de estados

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0181M3c92rVYQawQxK2fgyFv"
```

---

## Task 5: Parte B — badges en lista, línea de tiempo en detalle, admin

**Files:**
- Modify: `templates/modulacion/modulacion_list.html`
- Modify: `templates/modulacion/modulacion_detail.html`
- Modify: `modulos/modulacion/admin.py`
- Modify: `modulos/modulacion/tests_estados.py`

**Interfaces:**
- Consumes: `Modulacion.badge_class`, `Modulacion.transiciones_validas`, `SeguimientoModulacion` (Tasks 2 y 4).
- Produces: sin API nueva.

- [ ] **Step 1: Tests en `tests_estados.py` (fallan)**

Añade a `modulos/modulacion/tests_estados.py`:
```python
class ListaYDetalleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')
        self.client.force_login(self.user)

    def test_lista_usa_badge_class_para_estados_nuevos(self):
        _modulacion(estado='RECONOCIMIENTO_ADUANAL', contenedor='RECO5555555')
        resp = self.client.get(reverse('modulacion:list'))
        self.assertContains(resp, 'RECO5555555')
        self.assertContains(resp, 'bg-red-100')          # badge_class de RECONOCIMIENTO_ADUANAL
        self.assertContains(resp, 'Reconocimiento aduanal (rojo)')

    def test_detalle_muestra_linea_de_tiempo(self):
        m = _modulacion(estado='ASIGNADO')
        m.transicionar('INGRESADO', usuario=self.user, nota='ingresó a las 8')
        resp = self.client.get(reverse('modulacion:detail', args=[m.pk]))
        self.assertContains(resp, 'Ingresado')
        self.assertContains(resp, 'ingresó a las 8')

    def test_detalle_muestra_botones_de_transicion(self):
        m = _modulacion(estado='INGRESADO')
        resp = self.client.get(reverse('modulacion:detail', args=[m.pk]))
        self.assertContains(resp, 'Desaduanamiento libre (verde)')
        self.assertContains(resp, 'Reconocimiento aduanal (rojo)')
```

- [ ] **Step 2: Correr — fallan**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_estados.ListaYDetalleTests --settings=test_settings -v 2`
Expected: FAIL — la lista aún no rinde `bg-red-100` para ese estado; el detalle no rinde línea de tiempo ni botones.

- [ ] **Step 3: `modulacion_list.html` — chip por `badge_class`**

En `templates/modulacion/modulacion_list.html`, reemplaza el bloque del `<td>` de estado:
```html
                <td class="px-4 py-3">
                    {% if m.get_estado_display == "Pendiente de modulación" %}
                        <span class="inline-block px-2 py-0.5 bg-gray-100 text-gray-700 text-xs font-semibold rounded-full">{{ m.get_estado_display }}</span>
                    {% elif m.get_estado_display == "Enviado a Bitácora de Viajes" %}
                        <span class="inline-block px-2 py-0.5 bg-blue-100 text-blue-700 text-xs font-semibold rounded-full">{{ m.get_estado_display }}</span>
                    {% elif m.get_estado_display == "En Patio Esperanza" %}
                        <span class="inline-block px-2 py-0.5 bg-green-100 text-green-700 text-xs font-semibold rounded-full">{{ m.get_estado_display }}</span>
                    {% endif %}
                </td>
```
por:
```html
                <td class="px-4 py-3">
                    <span class="inline-block px-2 py-0.5 {{ m.badge_class }} text-xs font-semibold rounded-full">{{ m.get_estado_display }}</span>
                </td>
```

- [ ] **Step 4: `modulacion_detail.html` — chip, botones de transición y línea de tiempo**

1. En el encabezado del detalle, cambia:
```html
            <span class="inline-block px-3 py-1 bg-gray-100 text-gray-700 text-xs font-semibold rounded-full">{{ modulacion.get_estado_display }}</span>
```
por:
```html
            <span class="inline-block px-3 py-1 {{ modulacion.badge_class }} text-xs font-semibold rounded-full">{{ modulacion.get_estado_display }}</span>
```

2. En el `<div class="px-6 py-4 border-t border-gray-100 flex flex-wrap gap-3">` (botonera), después del botón "Eliminar", añade:
```html
            {% include "modulacion/_botones_transicion.html" with modulacion=modulacion next=request.get_full_path %}
```

3. Antes del `</div>` que cierra `<div class="max-w-3xl mx-auto space-y-6">` (al final del `block content`, después del bloque `{% if modulacion.estado == 'EN_PATIO_ESPERANZA' %}`), añade la línea de tiempo:
```html
    {% if modulacion.seguimientos.all %}
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-100">
            <h2 class="text-sm font-semibold text-gray-700">Historial de estados</h2>
        </div>
        <ol class="px-6 py-4 space-y-3">
            {% for s in modulacion.seguimientos.all %}
            <li class="flex items-start gap-3 text-sm">
                <span class="inline-block mt-0.5 px-2 py-0.5 text-xs font-semibold rounded-full {{ s.badge_class }}">{{ s.get_estado_display }}</span>
                <div>
                    <div class="text-gray-500">{{ s.creado_en|date:"d/m/Y H:i" }}{% if s.usuario %} · {{ s.usuario.get_username }}{% endif %}</div>
                    {% if s.nota %}<div class="text-gray-700">{{ s.nota }}</div>{% endif %}
                </div>
            </li>
            {% endfor %}
        </ol>
    </div>
    {% endif %}
```
Para que `{{ s.badge_class }}` funcione, añade a `class SeguimientoModulacion` en `models.py`:
```python
    @property
    def badge_class(self):
        return _BADGE_POR_ESTADO.get(self.estado, 'bg-gray-100 text-gray-700')
```

- [ ] **Step 5: `admin.py` — inline y registro read-only**

En `modulos/modulacion/admin.py`:

1. Import:
```python
from .models import (
    Agencia, ImportacionProgramacionLCTPC, Modulacion, SeguimientoModulacion,
    TerminalPortuaria,
)
```

2. Antes de `@admin.register(Modulacion)`:
```python
class SeguimientoModulacionInline(admin.TabularInline):
    model = SeguimientoModulacion
    extra = 0
    can_delete = False
    readonly_fields = ['estado', 'usuario', 'nota', 'creado_en']

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
```

3. En `class ModulacionAdmin`, añade:
```python
    inlines = [SeguimientoModulacionInline]
```

4. Al final del archivo:
```python
@admin.register(SeguimientoModulacion)
class SeguimientoModulacionAdmin(admin.ModelAdmin):
    list_display = ['creado_en', 'modulacion', 'estado', 'usuario']
    list_filter = ['estado']
    search_fields = ['modulacion__folio', 'modulacion__contenedor']
    date_hierarchy = 'creado_en'
    ordering = ['-creado_en']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
```

- [ ] **Step 6: Correr — verde**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_estados --settings=test_settings -v 2`
Expected: PASS.

- [ ] **Step 7: Regresión completa del módulo + checks**

```bash
.venvKasu/bin/python manage.py test modulos.modulacion --settings=test_settings
.venvKasu/bin/python manage.py check
.venvKasu/bin/python manage.py makemigrations --check --dry-run
```
Expected: suite en verde; `check` sin errores; sin migraciones pendientes de `modulacion` (puede aparecer el drift preexistente y ajeno de `taller`, que este trabajo no toca).

- [ ] **Step 8: Commit**

```bash
git add templates/modulacion/modulacion_list.html templates/modulacion/modulacion_detail.html modulos/modulacion/models.py modulos/modulacion/admin.py modulos/modulacion/tests_estados.py
git commit -m "feat(modulacion): badges centralizados, línea de tiempo en detalle y admin de seguimiento

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0181M3c92rVYQawQxK2fgyFv"
```

---

## Verificación final

- [ ] `.venvKasu/bin/python manage.py test modulos.modulacion --settings=test_settings` → toda la suite en verde (incluye `tests.py`, `tests_lctpc.py`, `tests_estados.py`).
- [ ] `.venvKasu/bin/python manage.py check` → sin errores.
- [ ] `.venvKasu/bin/python manage.py makemigrations --check --dry-run` → sin cambios en `modulacion`.
- [ ] `git log --oneline` → 5 commits, uno por tarea.
- [ ] Smoke manual: en `/modulacion/` aparece "Atención a Clientes"; asignar unidad+operador a una modulación `PENDIENTE` la deja `ASIGNADO` con una fila de historial; el tablero muestra los botones correctos por estado y el avance inválido da mensaje de error.

## Notas / fuera de alcance

- Sin permiso dedicado (solo login).
- Sin backfill de `SeguimientoModulacion` para modulaciones previas.
- Sin retroceso automático de estado al quitar unidad/operador.
- No se toca `services_full.py` ni la fusión de sencillos de `bitacoras`.
- `completar_datos_terminal` no cambia; su guard de "acceso cerrado" ahora se dispara al llegar a `ASIGNADO` (antes, a `MODULADO`).
