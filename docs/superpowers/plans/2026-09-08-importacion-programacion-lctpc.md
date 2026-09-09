# Importación de programación de citas LCTPC — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que BitacoraKasu lea por Microsoft Graph los correos de `atencionspf@lctpc.com.mx`, parsee el adjunto `.xls` (tabla HTML) con la programación de citas de la terminal LCTPC y actualice o cree las Modulaciones correspondientes, disparado por un poll cada 15 min y por un botón manual.

**Architecture:** Cuatro módulos nuevos en `modulos/modulacion/`: `services_graph.py` (solo red — token app-only + listar correos + bajar adjunto), `services_lctpc.py` (puro — parsear tabla HTML + fecha ES/EN + clasificar FULL/SENCILLO), `services_importacion.py` (orquesta: correos no procesados → parsear → match/crear Modulaciones → fila de auditoría) y un management command envoltura. Idempotencia por el modelo nuevo `ImportacionProgramacionLCTPC` (`graph_message_id` único). El scheduler existente (`config/scheduler.py`) gana un segundo job `interval`.

**Tech Stack:** Django 5.2.7, Python 3.12 (`.venvKasu`), `requests` (ya presente), `beautifulsoup4` (nueva), APScheduler + `django_apscheduler` (ya presente).

## Global Constraints

- Django `5.2.7`; ejecutar todo con el intérprete `.venvKasu/bin/python`.
- Pruebas: `.venvKasu/bin/python manage.py test <ruta> --settings=test_settings` (SQLite en memoria). No hay pytest.
- `requirements.txt` fija versiones exactas (`paquete==X.Y.Z`). Al agregar `beautifulsoup4`, instalar, correr `.venvKasu/bin/pip show beautifulsoup4` y fijar esa versión exacta.
- Idioma español en nombres de modelo/campo, `verbose_name`, comentarios y textos de UI.
- `TIME_ZONE = 'America/Mexico_City'`; los `DateTimeField` se guardan aware con `django.utils.timezone`.
- Vistas con `LoginRequiredMixin` (CBV) o `@login_required` (FBV), igual que el resto de `modulos/modulacion/views.py`.
- El scheduler ejecuta trabajo vía `call_command`, nunca lógica inline (patrón de `config/scheduler.py`).
- Permiso de Graph asumido: `Mail.Read` (solo lectura). No marcar correos como leídos ni moverlos.
- Remitente, buzón, nombre de terminal y minutos de poll salen de `settings` (con default), no hardcodeados en la lógica.
- Los tests nuevos van en `modulos/modulacion/tests_lctpc.py` (no tocar `tests.py`, que ya existe y no permite crear un paquete `tests/`). Fixtures en `modulos/modulacion/tests_fixtures/lctpc/`.

---

## Estructura de archivos

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `requirements.txt` | Modificar | Agregar `beautifulsoup4==<versión instalada>` |
| `modulos/modulacion/models.py` | Modificar | `+ tipo_cita`, `+ grupo_cita`, choice `LCTPC` en `ORIGEN_CHOICES`, modelo `ImportacionProgramacionLCTPC` |
| `modulos/modulacion/migrations/0007_*.py` | Crear (auto) | Migración de lo anterior |
| `modulos/modulacion/services_lctpc.py` | Crear | Parser HTML + fecha ES/EN + `clasificar()` |
| `modulos/modulacion/services_graph.py` | Crear | Graph API app-only: token, listar correos, bajar adjunto |
| `modulos/modulacion/services_importacion.py` | Crear | Orquestador `importar_programaciones_lctpc()` |
| `modulos/modulacion/management/__init__.py` | Crear | (paquete) |
| `modulos/modulacion/management/commands/__init__.py` | Crear | (paquete) |
| `modulos/modulacion/management/commands/importar_programacion_lctpc.py` | Crear | Command envoltura |
| `config/settings.py` | Modificar | Bloque `GRAPH_*` + `MODULACION_LCTPC_*` |
| `config/scheduler.py` | Modificar | `_ejecutar_importacion_lctpc()` + segundo `add_job` |
| `modulos/reportes/apps.py` | Modificar | `'importar_programacion_lctpc'` en `_SKIP_COMMANDS` |
| `modulos/modulacion/views.py` | Modificar | `importar_programacion_lctpc` (FBV POST), `ImportacionProgramacionLCTPCListView`, `ImportacionProgramacionLCTPCDetailView`, panel en `modulacion_dashboard` |
| `modulos/modulacion/urls.py` | Modificar | 3 rutas nuevas |
| `modulos/modulacion/admin.py` | Modificar | Registrar `ImportacionProgramacionLCTPC` read-only; `tipo_cita` en `ModulacionAdmin` |
| `templates/modulacion/dashboard.html` | Modificar | Panel "Programaciones LCTPC" + botón "Importar ahora" |
| `templates/modulacion/importacion_lctpc_list.html` | Crear | Lista de importaciones |
| `templates/modulacion/importacion_lctpc_detail.html` | Crear | Detalle renglón por renglón |
| `modulos/modulacion/tests_lctpc.py` | Crear | Todas las pruebas de esta feature |
| `modulos/modulacion/tests_fixtures/lctpc/*.xls` | Crear | Los 3 `.xls` reales |
| `CLAUDE.md` | Modificar | Env vars + nota del import LCTPC |

---

## Task 1: Dependencia, campos de modelo y modelo de auditoría

**Files:**
- Modify: `requirements.txt`
- Modify: `modulos/modulacion/models.py`
- Create: `modulos/modulacion/migrations/0007_importacion_lctpc.py` (auto)
- Create: `modulos/modulacion/tests_lctpc.py`

**Interfaces:**
- Produces:
  - `Modulacion.tipo_cita: str` (choices `'FULL'`/`'SENCILLO'`, `blank=True`)
  - `Modulacion.grupo_cita: str` (`max_length=32`, `blank=True`, `db_index=True`)
  - `Modulacion.ORIGEN_CHOICES` incluye `('LCTPC', 'Programación LCTPC')`
  - `ImportacionProgramacionLCTPC` con campos: `graph_message_id: str` (unique), `asunto: str`, `fecha_recibido: datetime`, `fecha_modulacion_aduana: date|None`, `estado: str` (`'OK'`/`'OK_CON_AVISOS'`/`'ERROR'`), `total_renglones/creadas/actualizadas/ambiguas: int`, `detalle: list`, `mensaje_error: str`, `creado_en: datetime`

- [ ] **Step 1: Instalar beautifulsoup4 y fijar versión**

```bash
.venvKasu/bin/pip install beautifulsoup4
.venvKasu/bin/pip show beautifulsoup4 | grep -i '^Version:'
```

Agregar a `requirements.txt` (orden alfabético, junto a `botocore`/`certifi`), sustituyendo `X.Y.Z` por la versión que imprimió el comando:

```
beautifulsoup4==X.Y.Z
```

- [ ] **Step 2: Escribir el test de modelo (falla)**

Crear `modulos/modulacion/tests_lctpc.py`:

```python
from datetime import date

from django.db import IntegrityError
from django.test import TestCase

from .models import ImportacionProgramacionLCTPC, Modulacion


class ImportacionProgramacionLCTPCModelTests(TestCase):
    def test_graph_message_id_es_unico(self):
        ImportacionProgramacionLCTPC.objects.create(
            graph_message_id='AAA-1', asunto='Programacion ... 07 September 2026',
            fecha_recibido='2026-09-05T14:02:00Z', estado='OK',
        )
        with self.assertRaises(IntegrityError):
            ImportacionProgramacionLCTPC.objects.create(
                graph_message_id='AAA-1', asunto='dup',
                fecha_recibido='2026-09-05T14:02:00Z', estado='OK',
            )

    def test_defaults_de_contadores_y_detalle(self):
        imp = ImportacionProgramacionLCTPC.objects.create(
            graph_message_id='AAA-2', asunto='x',
            fecha_recibido='2026-09-05T14:02:00Z', estado='ERROR',
            mensaje_error='sin adjunto',
        )
        self.assertEqual(imp.total_renglones, 0)
        self.assertEqual(imp.creadas, 0)
        self.assertEqual(imp.detalle, [])

    def test_modulacion_acepta_tipo_y_grupo_cita(self):
        m = Modulacion(contenedor='TEST1234567', tipo_cita='FULL', grupo_cita='abc123')
        # Solo comprobamos que los campos existen y aceptan el valor en memoria.
        self.assertEqual(m.tipo_cita, 'FULL')
        self.assertEqual(m.grupo_cita, 'abc123')
```

- [ ] **Step 3: Correr el test — debe fallar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc --settings=test_settings -v 2`
Expected: FAIL — `ImportError: cannot import name 'ImportacionProgramacionLCTPC'`.

- [ ] **Step 4: Agregar los campos a `Modulacion`**

En `modulos/modulacion/models.py`, dentro de `class Modulacion`, en `ORIGEN_CHOICES` agregar la tercera opción:

```python
    ORIGEN_CHOICES = [
        ('HAL9MIL', 'HAL9MIL / LOGINCO'),
        ('MANUAL', 'Captura manual'),
        ('LCTPC', 'Programación LCTPC'),
    ]
```

Y junto a los campos `carril` / `hora_registro` (busca la línea `carril = models.CharField(max_length=10, blank=True, verbose_name="Carril")`), añadir:

```python
    tipo_cita = models.CharField(
        max_length=10,
        blank=True,
        choices=[('FULL', 'Full'), ('SENCILLO', 'Sencillo')],
        verbose_name="Tipo de cita",
        help_text="Clasificación FULL/SENCILLO derivada de la programación de la terminal.",
    )
    grupo_cita = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        verbose_name="Grupo de cita FULL",
        help_text="Comparten valor los 2 contenedores de un mismo FULL.",
    )
```

- [ ] **Step 5: Agregar el modelo `ImportacionProgramacionLCTPC`**

Al final de `modulos/modulacion/models.py`:

```python
class ImportacionProgramacionLCTPC(models.Model):
    """
    Auditoría e idempotencia de cada correo de programación de citas de LCTPC
    (`atencionspf@lctpc.com.mx`) procesado por el import automático.
    Un registro = un correo. `graph_message_id` único evita reprocesar.
    """
    ESTADO_CHOICES = [
        ('OK', 'Procesado sin avisos'),
        ('OK_CON_AVISOS', 'Procesado con avisos'),
        ('ERROR', 'Error al procesar'),
    ]

    graph_message_id = models.CharField(max_length=255, unique=True, verbose_name="ID de mensaje (Graph)")
    asunto = models.CharField(max_length=300, verbose_name="Asunto")
    fecha_recibido = models.DateTimeField(verbose_name="Fecha de recepción del correo")
    fecha_modulacion_aduana = models.DateField(
        null=True, blank=True, verbose_name="Fecha de modulación ante aduana",
    )
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, verbose_name="Estado")
    total_renglones = models.PositiveIntegerField(default=0, verbose_name="Renglones en el Excel")
    creadas = models.PositiveIntegerField(default=0, verbose_name="Modulaciones creadas")
    actualizadas = models.PositiveIntegerField(default=0, verbose_name="Modulaciones actualizadas")
    ambiguas = models.PositiveIntegerField(default=0, verbose_name="Coincidencias ambiguas")
    detalle = models.JSONField(
        default=list, blank=True,
        verbose_name="Detalle por contenedor",
        help_text="[{contenedor, folio_lctpc, resultado, modulacion_id, tipo_cita}]",
    )
    mensaje_error = models.TextField(blank=True, verbose_name="Error / avisos")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Importación de programación LCTPC"
        verbose_name_plural = "Importaciones de programación LCTPC"
        ordering = ['-fecha_recibido']

    def __str__(self):
        return f"{self.asunto} ({self.estado})"
```

- [ ] **Step 6: Generar y aplicar la migración**

```bash
.venvKasu/bin/python manage.py makemigrations modulacion --name importacion_lctpc
.venvKasu/bin/python manage.py migrate --settings=test_settings
```

Expected: crea `0007_importacion_lctpc.py`; `migrate` sin errores.

- [ ] **Step 7: Correr el test — debe pasar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc --settings=test_settings -v 2`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add requirements.txt modulos/modulacion/models.py modulos/modulacion/migrations/0007_importacion_lctpc.py modulos/modulacion/tests_lctpc.py
git commit -m "feat(modulacion): modelo ImportacionProgramacionLCTPC y campos tipo_cita/grupo_cita

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01L9VJK8wNw2vCheFNyGLcgV"
```

---

## Task 2: Parser del adjunto — tabla y fecha (`services_lctpc.py`)

**Files:**
- Create: `modulos/modulacion/services_lctpc.py`
- Create: `modulos/modulacion/tests_fixtures/lctpc/3ZYM_202609031849.xls`, `3ZYM_202609041650.xls`, `3ZYM_202609051401.xls`
- Modify: `modulos/modulacion/tests_lctpc.py`

**Interfaces:**
- Produces:
  - `class ErrorParseoLCTPC(Exception)`
  - `@dataclass class RenglonLCTPC` con atributos **mutables**: `contenedor: str`, `transportista: str`, `folio_lctpc: str`, `registro_inicio: datetime.time`, `registro_fin: datetime.time`, `cita_inicio: datetime.time`, `cita_fin: datetime.time`, `tipo_cita: str = ''`, `grupo_cita: str = ''`
  - `@dataclass class ProgramacionParseada`: `fecha: datetime.date`, `fecha_titulo_excel: datetime.date | None`, `fecha_asunto: datetime.date | None`, `renglones: list[RenglonLCTPC]`, `avisos: list[str]`
  - `parsear_programacion(contenido: bytes, asunto: str) -> ProgramacionParseada`

- [ ] **Step 1: Copiar los fixtures**

```bash
mkdir -p modulos/modulacion/tests_fixtures/lctpc
cp 3ZYM_202609031849.xls 3ZYM_202609041650.xls 3ZYM_202609051401.xls modulos/modulacion/tests_fixtures/lctpc/
```

- [ ] **Step 2: Escribir los tests del parser (fallan)**

Añadir a `modulos/modulacion/tests_lctpc.py`:

```python
from datetime import time
from pathlib import Path

from django.test import SimpleTestCase

from .services_lctpc import ErrorParseoLCTPC, parsear_programacion

FIXTURES = Path(__file__).resolve().parent / 'tests_fixtures' / 'lctpc'
ASUNTO_07 = ('Programacion de contenedores a SPF, por horario preferente, '
             'para el 07 September 2026')


def _leer(nombre):
    return (FIXTURES / nombre).read_bytes()


class ParsearProgramacionTests(SimpleTestCase):
    def test_extrae_las_10_filas_con_columnas_correctas(self):
        prog = parsear_programacion(_leer('3ZYM_202609051401.xls'), ASUNTO_07)
        self.assertEqual(len(prog.renglones), 10)
        r0 = prog.renglones[0]
        self.assertEqual(r0.contenedor, 'GXYU5129072')
        self.assertEqual(r0.transportista, '3ZYM')
        self.assertEqual(r0.folio_lctpc, '617210')
        self.assertEqual(r0.registro_inicio, time(1, 30))
        self.assertEqual(r0.registro_fin, time(3, 0))
        self.assertEqual(r0.cita_inicio, time(3, 0))
        self.assertEqual(r0.cita_fin, time(3, 59))

    def test_fecha_mes_en_ingles(self):
        prog = parsear_programacion(_leer('3ZYM_202609051401.xls'), ASUNTO_07)
        self.assertEqual(prog.fecha, date(2026, 9, 7))

    def test_fecha_mes_en_espanol(self):
        # 3ZYM_202609031849.xls: título "... para el 04 Septiembre 2026"
        asunto = 'Programacion de contenedores a SPF, para el 04 Septiembre 2026'
        prog = parsear_programacion(_leer('3ZYM_202609031849.xls'), asunto)
        self.assertEqual(prog.fecha, date(2026, 9, 4))
        self.assertEqual(prog.avisos, [])

    def test_decodifica_iso_8859_1_en_titulo(self):
        # No debe reventar por el carácter 'ó' de "Programación".
        prog = parsear_programacion(_leer('3ZYM_202609041650.xls'),
                                    'Programacion ... para el 05 September 2026')
        self.assertIsNotNone(prog.fecha)

    def test_fecha_asunto_distinta_a_titulo_usa_asunto_y_avisa(self):
        prog = parsear_programacion(
            _leer('3ZYM_202609051401.xls'),
            'Programacion de contenedores a SPF, para el 08 September 2026',
        )
        self.assertEqual(prog.fecha, date(2026, 9, 8))
        self.assertEqual(prog.fecha_titulo_excel, date(2026, 9, 7))
        self.assertTrue(prog.avisos)

    def test_sin_fecha_en_asunto_ni_titulo_levanta_error(self):
        contenido = b'<html><table><tr><th>OTRA</th></tr></table></html>'
        with self.assertRaises(ErrorParseoLCTPC):
            parsear_programacion(contenido, 'asunto sin fecha')

    def test_rango_horario_invalido_levanta_error(self):
        contenido = (
            '<table><thead><tr><th>CONTENEDOR</th><th>TRANSPORTISTA</th>'
            '<th>FOLIO</th><th>VENTANA DE REGISTRO</th><th>HORARIO DE CITA</th>'
            '</tr></thead><tr><td>ABCU1234567</td><td>3ZYM</td><td>1</td>'
            '<td>nope</td><td>03:00-03:59</td></tr></table>'
        ).encode('iso-8859-1')
        with self.assertRaises(ErrorParseoLCTPC):
            parsear_programacion(contenido, 'para el 07 September 2026')
```

- [ ] **Step 3: Correr — deben fallar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ParsearProgramacionTests --settings=test_settings -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'modulos.modulacion.services_lctpc'`.

- [ ] **Step 4: Implementar `services_lctpc.py` (parser)**

Crear `modulos/modulacion/services_lctpc.py`:

```python
"""
Parser del adjunto de programación de citas de LCTPC.

El adjunto llega como `.xls` pero es una **tabla HTML** (ISO-8859-1), con:
  - una celda título `class="oscuro"` con "... para el <día> <mes> <año>"
    (mes en inglés o español), y
  - una tabla con columnas
    CONTENEDOR | TRANSPORTISTA | FOLIO | VENTANA DE REGISTRO | HORARIO DE CITA.

Este módulo es puro: no toca la BD ni la red.
"""
import datetime
import re
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from bs4 import BeautifulSoup


class ErrorParseoLCTPC(Exception):
    """El adjunto o el asunto no tienen el formato esperado."""


@dataclass
class RenglonLCTPC:
    contenedor: str
    transportista: str
    folio_lctpc: str
    registro_inicio: datetime.time
    registro_fin: datetime.time
    cita_inicio: datetime.time
    cita_fin: datetime.time
    tipo_cita: str = ''
    grupo_cita: str = ''


@dataclass
class ProgramacionParseada:
    fecha: datetime.date
    fecha_titulo_excel: datetime.date | None
    fecha_asunto: datetime.date | None
    renglones: list
    avisos: list = field(default_factory=list)


_MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11,
    'diciembre': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11,
    'december': 12,
}
_FECHA_RE = re.compile(
    r'para el\s+(\d{1,2})\s+([A-Za-zÀ-ſ]+)\s+(\d{4})', re.IGNORECASE
)
_RANGO_RE = re.compile(r'^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$')


def _parsear_fecha_texto(texto):
    if not texto:
        return None
    m = _FECHA_RE.search(texto)
    if not m:
        return None
    mes = _MESES.get(m.group(2).lower())
    if not mes:
        return None
    try:
        return datetime.date(int(m.group(3)), mes, int(m.group(1)))
    except ValueError:
        return None


def _parsear_rango(texto):
    m = _RANGO_RE.match(texto or '')
    if not m:
        raise ErrorParseoLCTPC(f'Rango horario inválido: {texto!r}')
    h1, m1, h2, m2 = (int(x) for x in m.groups())
    try:
        return datetime.time(h1, m1), datetime.time(h2, m2)
    except ValueError as exc:
        raise ErrorParseoLCTPC(f'Rango horario inválido: {texto!r}') from exc


def _encontrar_tabla_datos(soup):
    for tabla in soup.find_all('table'):
        encabezados = [c.get_text(strip=True).upper() for c in tabla.find_all('th')]
        if 'CONTENEDOR' in encabezados:
            return tabla
    return None


def parsear_programacion(contenido: bytes, asunto: str) -> ProgramacionParseada:
    soup = BeautifulSoup(contenido.decode('iso-8859-1'), 'html.parser')

    titulo_cell = soup.find('th', class_='oscuro')
    fecha_titulo = _parsear_fecha_texto(
        titulo_cell.get_text(strip=True) if titulo_cell else ''
    )
    fecha_asunto = _parsear_fecha_texto(asunto or '')

    avisos = []
    if fecha_asunto and fecha_titulo and fecha_asunto != fecha_titulo:
        avisos.append(
            f'La fecha del asunto ({fecha_asunto}) no coincide con la del Excel '
            f'({fecha_titulo}); se usa la del asunto.'
        )
    fecha = fecha_asunto or fecha_titulo
    if fecha is None:
        raise ErrorParseoLCTPC(
            'No se pudo determinar la fecha de modulación (ni en el asunto ni en el Excel).'
        )

    tabla = _encontrar_tabla_datos(soup)
    if tabla is None:
        raise ErrorParseoLCTPC('No se encontró la tabla de contenedores en el adjunto.')

    renglones = []
    for tr in tabla.find_all('tr'):
        celdas = tr.find_all('td')
        if len(celdas) < 5:
            continue
        vals = [c.get_text(strip=True) for c in celdas]
        contenedor, transportista, folio, ventana, cita = vals[:5]
        reg_ini, reg_fin = _parsear_rango(ventana)
        cita_ini, cita_fin = _parsear_rango(cita)
        renglones.append(RenglonLCTPC(
            contenedor=contenedor.strip().upper(),
            transportista=transportista.strip(),
            folio_lctpc=folio.strip(),
            registro_inicio=reg_ini,
            registro_fin=reg_fin,
            cita_inicio=cita_ini,
            cita_fin=cita_fin,
        ))

    if not renglones:
        raise ErrorParseoLCTPC('La tabla del adjunto no tiene renglones de datos.')

    return ProgramacionParseada(
        fecha=fecha,
        fecha_titulo_excel=fecha_titulo,
        fecha_asunto=fecha_asunto,
        renglones=renglones,
        avisos=avisos,
    )
```

- [ ] **Step 5: Correr — deben pasar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ParsearProgramacionTests --settings=test_settings -v 2`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add modulos/modulacion/services_lctpc.py modulos/modulacion/tests_lctpc.py modulos/modulacion/tests_fixtures/
git commit -m "feat(modulacion): parser del adjunto HTML de programación LCTPC

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01L9VJK8wNw2vCheFNyGLcgV"
```

---

## Task 3: Clasificación FULL / SENCILLO (`services_lctpc.clasificar`)

**Files:**
- Modify: `modulos/modulacion/services_lctpc.py`
- Modify: `modulos/modulacion/tests_lctpc.py`

**Interfaces:**
- Consumes: `RenglonLCTPC`, `parsear_programacion` (Task 2)
- Produces: `clasificar(renglones: list[RenglonLCTPC]) -> list[RenglonLCTPC]` — muta cada `RenglonLCTPC` en el sitio (`tipo_cita`, `grupo_cita`) y devuelve la misma lista. Agrupa por `registro_inicio` preservando el orden de aparición; empareja de 2 en 2 dentro del grupo (`FULL`, `grupo_cita` = `uuid4().hex` compartido); el sobrante impar y los grupos de 1 quedan `SENCILLO` con `grupo_cita = ''`.

- [ ] **Step 1: Escribir los tests (fallan)**

Añadir a `modulos/modulacion/tests_lctpc.py`:

```python
from .services_lctpc import RenglonLCTPC, clasificar


def _renglon(contenedor, reg_ini):
    return RenglonLCTPC(
        contenedor=contenedor, transportista='3ZYM', folio_lctpc='0',
        registro_inicio=reg_ini, registro_fin=time(9, 0),
        cita_inicio=time(9, 0), cita_fin=time(9, 59),
    )


class ClasificarTests(SimpleTestCase):
    def test_seis_con_misma_hora_dan_tres_full(self):
        rs = [_renglon(f'C{i}', time(1, 30)) for i in range(6)]
        clasificar(rs)
        self.assertTrue(all(r.tipo_cita == 'FULL' for r in rs))
        self.assertEqual(rs[0].grupo_cita, rs[1].grupo_cita)
        self.assertEqual(rs[2].grupo_cita, rs[3].grupo_cita)
        self.assertEqual(rs[4].grupo_cita, rs[5].grupo_cita)
        self.assertEqual(len({rs[0].grupo_cita, rs[2].grupo_cita, rs[4].grupo_cita}), 3)

    def test_cinco_dan_dos_full_y_un_sencillo(self):
        rs = [_renglon(f'C{i}', time(1, 30)) for i in range(5)]
        clasificar(rs)
        self.assertEqual([r.tipo_cita for r in rs],
                         ['FULL', 'FULL', 'FULL', 'FULL', 'SENCILLO'])
        self.assertEqual(rs[4].grupo_cita, '')

    def test_uno_solo_es_sencillo(self):
        rs = [_renglon('C0', time(2, 30))]
        clasificar(rs)
        self.assertEqual(rs[0].tipo_cita, 'SENCILLO')
        self.assertEqual(rs[0].grupo_cita, '')

    def test_archivo_real_da_3_full_y_4_sencillo(self):
        prog = parsear_programacion(_leer('3ZYM_202609051401.xls'), ASUNTO_07)
        clasificar(prog.renglones)
        tipos = [r.tipo_cita for r in prog.renglones]
        self.assertEqual(tipos.count('FULL'), 6)
        self.assertEqual(tipos.count('SENCILLO'), 4)
        # 6 FULL == 3 pares con grupo distinto
        grupos_full = {r.grupo_cita for r in prog.renglones if r.tipo_cita == 'FULL'}
        self.assertEqual(len(grupos_full), 3)
```

- [ ] **Step 2: Correr — deben fallar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ClasificarTests --settings=test_settings -v 2`
Expected: FAIL — `ImportError: cannot import name 'clasificar'`.

- [ ] **Step 3: Implementar `clasificar`**

Añadir al final de `modulos/modulacion/services_lctpc.py`:

```python
def clasificar(renglones):
    """Marca cada RenglonLCTPC con tipo_cita ('FULL'/'SENCILLO') y grupo_cita.

    Regla del usuario: los renglones que comparten la hora de inicio de la
    ventana de registro se emparejan de 2 en 2 (en el orden del Excel) → FULL.
    El sobrante de un grupo impar, y los grupos de 1, quedan SENCILLO.
    """
    grupos = OrderedDict()
    for r in renglones:
        grupos.setdefault(r.registro_inicio, []).append(r)

    for grupo in grupos.values():
        i = 0
        while i + 1 < len(grupo):
            gid = uuid.uuid4().hex
            grupo[i].tipo_cita = grupo[i + 1].tipo_cita = 'FULL'
            grupo[i].grupo_cita = grupo[i + 1].grupo_cita = gid
            i += 2
        if i < len(grupo):
            grupo[i].tipo_cita = 'SENCILLO'
            grupo[i].grupo_cita = ''

    return renglones
```

- [ ] **Step 4: Correr — deben pasar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ClasificarTests --settings=test_settings -v 2`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add modulos/modulacion/services_lctpc.py modulos/modulacion/tests_lctpc.py
git commit -m "feat(modulacion): clasificación FULL/SENCILLO por ventana de registro

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01L9VJK8wNw2vCheFNyGLcgV"
```

---

## Task 4: Conector Microsoft Graph (`services_graph.py`) + settings

**Files:**
- Create: `modulos/modulacion/services_graph.py`
- Modify: `config/settings.py`
- Modify: `modulos/modulacion/tests_lctpc.py`

**Interfaces:**
- Produces:
  - `class GraphError(Exception)`
  - `@dataclass class CorreoLCTPC`: `id: str`, `asunto: str`, `recibido: datetime.datetime | None`
  - `obtener_token() -> str` — client credentials; cachea en memoria del proceso; `GraphError` si falta config o falla la red/HTTP
  - `listar_correos(remitente: str | None = None) -> list[CorreoLCTPC]` — `remitente` default `settings.MODULACION_LCTPC_REMITENTE`; 25 más recientes
  - `descargar_adjunto_xls(message_id: str) -> bytes` — primer `fileAttachment` cuyo nombre termina en `.xls`; `GraphError` si no hay
- Settings nuevos: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `MODULACION_LCTPC_MAILBOX`, `MODULACION_LCTPC_REMITENTE`, `MODULACION_TERMINAL_LCTPC`, `MODULACION_LCTPC_POLL_MINUTOS`

- [ ] **Step 1: Agregar settings**

En `config/settings.py`, justo después de la línea `PUBLIC_BASE_URL = env.str('PUBLIC_BASE_URL', default='')`:

```python

# ---------------------------------------------------------------------------
# Microsoft Graph — lectura del buzón de calidad (programación de citas LCTPC)
# ---------------------------------------------------------------------------
GRAPH_TENANT_ID = env.str('GRAPH_TENANT_ID', default='')
GRAPH_CLIENT_ID = env.str('GRAPH_CLIENT_ID', default='')
GRAPH_CLIENT_SECRET = env.str('GRAPH_CLIENT_SECRET', default='')

MODULACION_LCTPC_MAILBOX = env.str(
    'MODULACION_LCTPC_MAILBOX', default='calidad@transporteskasu.com.mx'
)
MODULACION_LCTPC_REMITENTE = env.str(
    'MODULACION_LCTPC_REMITENTE', default='atencionspf@lctpc.com.mx'
)
MODULACION_TERMINAL_LCTPC = env.str(
    'MODULACION_TERMINAL_LCTPC',
    default='L.C. Terminal Portuaria de Contenedores, S.A. de C.V.',
)
MODULACION_LCTPC_POLL_MINUTOS = env.int('MODULACION_LCTPC_POLL_MINUTOS', default=15)
```

- [ ] **Step 2: Escribir los tests (fallan)**

Añadir a `modulos/modulacion/tests_lctpc.py`:

```python
import base64
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from .services_graph import CorreoLCTPC, GraphError, descargar_adjunto_xls, listar_correos, obtener_token

GRAPH_CONF = dict(
    GRAPH_TENANT_ID='t', GRAPH_CLIENT_ID='c', GRAPH_CLIENT_SECRET='s',
    MODULACION_LCTPC_MAILBOX='calidad@transporteskasu.com.mx',
    MODULACION_LCTPC_REMITENTE='atencionspf@lctpc.com.mx',
)


def _resp(status=200, json_data=None, text=''):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data or {}
    r.text = text
    return r


@override_settings(**GRAPH_CONF)
class ServicesGraphTests(SimpleTestCase):
    def setUp(self):
        # limpiar el cache de token entre pruebas
        import modulos.modulacion.services_graph as g
        g._token_cache.update(valor=None, expira=0.0)

    @patch('modulos.modulacion.services_graph.requests.post')
    def test_obtener_token_devuelve_access_token(self, mock_post):
        mock_post.return_value = _resp(json_data={'access_token': 'ABC', 'expires_in': 3600})
        self.assertEqual(obtener_token(), 'ABC')

    @patch('modulos.modulacion.services_graph.requests.post')
    def test_obtener_token_http_error_levanta_grapherror(self, mock_post):
        mock_post.return_value = _resp(status=401, text='bad secret')
        with self.assertRaises(GraphError):
            obtener_token()

    @override_settings(GRAPH_TENANT_ID='', GRAPH_CLIENT_ID='', GRAPH_CLIENT_SECRET='')
    def test_sin_config_levanta_grapherror(self):
        with self.assertRaises(GraphError):
            obtener_token()

    @patch('modulos.modulacion.services_graph.obtener_token', return_value='TOK')
    @patch('modulos.modulacion.services_graph.requests.get')
    def test_listar_correos_parsea_value(self, mock_get, _tok):
        mock_get.return_value = _resp(json_data={'value': [
            {'id': 'm1', 'subject': 'Programacion ... 07 September 2026',
             'receivedDateTime': '2026-09-05T14:02:00Z'},
        ]})
        correos = listar_correos()
        self.assertEqual(len(correos), 1)
        self.assertIsInstance(correos[0], CorreoLCTPC)
        self.assertEqual(correos[0].id, 'm1')
        self.assertEqual(correos[0].recibido.year, 2026)

    @patch('modulos.modulacion.services_graph.obtener_token', return_value='TOK')
    @patch('modulos.modulacion.services_graph.requests.get')
    def test_descargar_adjunto_xls_decodifica_base64(self, mock_get, _tok):
        contenido = b'<table>hola</table>'
        mock_get.return_value = _resp(json_data={'value': [
            {'@odata.type': '#microsoft.graph.fileAttachment',
             'name': '3ZYM_202609051401.xls',
             'contentBytes': base64.b64encode(contenido).decode()},
        ]})
        self.assertEqual(descargar_adjunto_xls('m1'), contenido)

    @patch('modulos.modulacion.services_graph.obtener_token', return_value='TOK')
    @patch('modulos.modulacion.services_graph.requests.get')
    def test_descargar_sin_xls_levanta_grapherror(self, mock_get, _tok):
        mock_get.return_value = _resp(json_data={'value': [
            {'@odata.type': '#microsoft.graph.fileAttachment', 'name': 'firma.png',
             'contentBytes': 'AAAA'},
        ]})
        with self.assertRaises(GraphError):
            descargar_adjunto_xls('m1')
```

- [ ] **Step 3: Correr — deben fallar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ServicesGraphTests --settings=test_settings -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'modulos.modulacion.services_graph'`.

- [ ] **Step 4: Implementar `services_graph.py`**

Crear `modulos/modulacion/services_graph.py`:

```python
"""
Cliente mínimo de Microsoft Graph (app-only) para leer el buzón de calidad.

Solo lectura: token client-credentials, listar los correos de un remitente y
bajar el primer adjunto `.xls`. Sin lógica de negocio. Toda falla de red,
de token o de HTTP se traduce a `GraphError`.
"""
import base64
import datetime
import time
from dataclasses import dataclass

import requests
from django.conf import settings

_GRAPH = 'https://graph.microsoft.com/v1.0'
_token_cache = {'valor': None, 'expira': 0.0}


class GraphError(Exception):
    """Cualquier problema hablando con Microsoft Graph."""


@dataclass
class CorreoLCTPC:
    id: str
    asunto: str
    recibido: datetime.datetime | None


def _config_ok():
    return all([
        settings.GRAPH_TENANT_ID,
        settings.GRAPH_CLIENT_ID,
        settings.GRAPH_CLIENT_SECRET,
    ])


def obtener_token() -> str:
    if not _config_ok():
        raise GraphError(
            'Graph API no configurada (faltan GRAPH_TENANT_ID / GRAPH_CLIENT_ID / '
            'GRAPH_CLIENT_SECRET).'
        )
    ahora = time.time()
    if _token_cache['valor'] and _token_cache['expira'] - 60 > ahora:
        return _token_cache['valor']

    url = f'https://login.microsoftonline.com/{settings.GRAPH_TENANT_ID}/oauth2/v2.0/token'
    datos = {
        'client_id': settings.GRAPH_CLIENT_ID,
        'client_secret': settings.GRAPH_CLIENT_SECRET,
        'scope': 'https://graph.microsoft.com/.default',
        'grant_type': 'client_credentials',
    }
    try:
        resp = requests.post(url, data=datos, timeout=15)
    except requests.RequestException as exc:
        raise GraphError(f'Error de red al pedir el token: {exc}') from exc
    if resp.status_code != 200:
        raise GraphError(f'Token rechazado ({resp.status_code}): {resp.text[:300]}')

    payload = resp.json()
    _token_cache['valor'] = payload['access_token']
    _token_cache['expira'] = ahora + int(payload.get('expires_in', 3600))
    return _token_cache['valor']


def _get(path, params=None):
    token = obtener_token()
    try:
        resp = requests.get(
            f'{_GRAPH}{path}', params=params,
            headers={'Authorization': f'Bearer {token}'}, timeout=30,
        )
    except requests.RequestException as exc:
        raise GraphError(f'Error de red en {path}: {exc}') from exc
    if resp.status_code != 200:
        raise GraphError(f'Graph {path} -> {resp.status_code}: {resp.text[:300]}')
    return resp.json()


def _parsear_dt(valor):
    if not valor:
        return None
    try:
        return datetime.datetime.fromisoformat(valor.replace('Z', '+00:00'))
    except ValueError:
        return None


def listar_correos(remitente: str | None = None) -> list:
    remitente = remitente or settings.MODULACION_LCTPC_REMITENTE
    mailbox = settings.MODULACION_LCTPC_MAILBOX
    params = {
        '$filter': f"from/emailAddress/address eq '{remitente}'",
        '$select': 'id,subject,receivedDateTime',
        '$orderby': 'receivedDateTime desc',
        '$top': '25',
    }
    data = _get(f'/users/{mailbox}/messages', params=params)
    return [
        CorreoLCTPC(
            id=item['id'],
            asunto=item.get('subject', '') or '',
            recibido=_parsear_dt(item.get('receivedDateTime')),
        )
        for item in data.get('value', [])
    ]


def descargar_adjunto_xls(message_id: str) -> bytes:
    mailbox = settings.MODULACION_LCTPC_MAILBOX
    data = _get(f'/users/{mailbox}/messages/{message_id}/attachments')
    for att in data.get('value', []):
        nombre = (att.get('name') or '').lower()
        if (att.get('@odata.type') == '#microsoft.graph.fileAttachment'
                and nombre.endswith('.xls')):
            return base64.b64decode(att['contentBytes'])
    raise GraphError(f'El correo {message_id} no tiene un adjunto .xls.')
```

- [ ] **Step 5: Correr — deben pasar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ServicesGraphTests --settings=test_settings -v 2`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add modulos/modulacion/services_graph.py config/settings.py modulos/modulacion/tests_lctpc.py
git commit -m "feat(modulacion): cliente Microsoft Graph app-only para el buzón de calidad

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01L9VJK8wNw2vCheFNyGLcgV"
```

---

## Task 5: Orquestador (`services_importacion.py`)

**Files:**
- Create: `modulos/modulacion/services_importacion.py`
- Modify: `modulos/modulacion/tests_lctpc.py`

**Interfaces:**
- Consumes: `services_graph.listar_correos`, `services_graph.descargar_adjunto_xls`, `services_graph.GraphError`, `CorreoLCTPC` (Task 4); `parsear_programacion`, `clasificar`, `ErrorParseoLCTPC` (Tasks 2–3); `Modulacion`, `Agencia`, `TerminalPortuaria`, `ImportacionProgramacionLCTPC` (Task 1)
- Produces:
  - `@dataclass class ResumenImportacion`: `correos_procesados: int = 0`, `correos_saltados: int = 0`, `correos_con_error: int = 0`, `creadas: int = 0`, `actualizadas: int = 0`, `ambiguas: int = 0`
  - `importar_programaciones_lctpc() -> ResumenImportacion` — recorre `listar_correos()`, salta los que ya están en `ImportacionProgramacionLCTPC`, procesa cada uno en su propia transacción, escribe una fila de auditoría por correo. Un `GraphError` al **listar** se traga (se registra en el logger `modulos.modulacion`) y devuelve el `ResumenImportacion` acumulado hasta ahí.
  - Valores de `detalle[].resultado`: `'CREADA'`, `'ACTUALIZADA'`, `'ACTUALIZADA_AMBIGUA'`

- [ ] **Step 1: Escribir los tests (fallan)**

Añadir a `modulos/modulacion/tests_lctpc.py`:

```python
from decimal import Decimal

from modulos.modulacion.models import Agencia, ImportacionProgramacionLCTPC, Modulacion, TerminalPortuaria
from modulos.modulacion.services_graph import CorreoLCTPC, GraphError
from modulos.modulacion.services_importacion import importar_programaciones_lctpc

TERMINAL_LCTPC = 'L.C. Terminal Portuaria de Contenedores, S.A. de C.V.'


def _terminal():
    return TerminalPortuaria.objects.get_or_create(nombre=TERMINAL_LCTPC)[0]


def _modulacion(contenedor, estado='PENDIENTE', terminal=None):
    return Modulacion.objects.create(
        agencia=Agencia.objects.get_or_create(nombre='LOGINCO')[0],
        terminal_portuaria=terminal or _terminal(),
        tipo_contenedor='40HC', peso_toneladas=Decimal('18.5'),
        contenedor=contenedor, estado=estado,
    )


@override_settings(MODULACION_TERMINAL_LCTPC=TERMINAL_LCTPC)
class ImportarProgramacionesTests(TestCase):
    def setUp(self):
        self.xls = _leer('3ZYM_202609051401.xls')
        self.correo = CorreoLCTPC(id='m1', asunto=ASUNTO_07,
                                  recibido=timezone.now())

    def _patch_graph(self, correos=None, xls=None, list_error=None, dl_error=None):
        correos = [self.correo] if correos is None else correos
        p_list = patch('modulos.modulacion.services_importacion.listar_correos')
        p_dl = patch('modulos.modulacion.services_importacion.descargar_adjunto_xls')
        m_list = p_list.start()
        m_dl = p_dl.start()
        self.addCleanup(p_list.stop)
        self.addCleanup(p_dl.stop)
        m_list.side_effect = list_error
        if not list_error:
            m_list.return_value = correos
        if dl_error:
            m_dl.side_effect = dl_error
        else:
            m_dl.return_value = self.xls if xls is None else xls
        return m_list, m_dl

    def test_crea_stub_cuando_no_hay_modulacion(self):
        self._patch_graph()
        resumen = importar_programaciones_lctpc()
        self.assertEqual(resumen.creadas, 10)
        stub = Modulacion.objects.get(contenedor='GXYU5129072')
        self.assertEqual(stub.origen, 'LCTPC')
        self.assertEqual(stub.peso_toneladas, Decimal('0'))
        self.assertEqual(stub.tipo_contenedor, '')
        self.assertEqual(stub.agencia.nombre, 'POR DEFINIR')
        self.assertEqual(stub.fecha_modulacion_aduana, date(2026, 9, 7))
        self.assertIsNotNone(stub.hora_registro)
        self.assertIn('faltan agencia/cliente/tipo/peso', stub.observaciones)
        self.assertIn('Cita LCTPC 617210', stub.observaciones)

    def test_actualiza_modulacion_existente(self):
        m = _modulacion('GXYU5129072')
        self._patch_graph()
        resumen = importar_programaciones_lctpc()
        m.refresh_from_db()
        self.assertEqual(resumen.actualizadas, 1)
        self.assertEqual(resumen.creadas, 9)
        self.assertEqual(m.fecha_modulacion_aduana, date(2026, 9, 7))
        # hora_* se guardan aware en America/Mexico_City (make_aware) y Django
        # las almacena en UTC; se comparan en hora local.
        self.assertEqual(timezone.localtime(m.hora_registro).hour, 1)
        self.assertEqual(timezone.localtime(m.hora_registro).minute, 30)
        self.assertEqual(timezone.localtime(m.hora_ingreso).hour, 3)
        self.assertEqual(m.tipo_cita, 'FULL')
        self.assertTrue(m.grupo_cita)

    def test_hora_registro_es_aware_y_en_la_fecha_de_modulacion(self):
        _modulacion('GXYU5129072')
        self._patch_graph()
        importar_programaciones_lctpc()
        m = Modulacion.objects.get(contenedor='GXYU5129072')
        self.assertIsNotNone(timezone.is_aware(m.hora_registro))
        self.assertEqual(timezone.localtime(m.hora_registro).date(), date(2026, 9, 7))

    def test_correo_ya_procesado_se_salta(self):
        ImportacionProgramacionLCTPC.objects.create(
            graph_message_id='m1', asunto=ASUNTO_07,
            fecha_recibido=timezone.now(), estado='OK',
        )
        self._patch_graph()
        resumen = importar_programaciones_lctpc()
        self.assertEqual(resumen.correos_saltados, 1)
        self.assertEqual(resumen.creadas, 0)

    def test_no_duplica_linea_de_observacion_en_segundo_correo(self):
        m = _modulacion('GXYU5129072')
        self._patch_graph()
        importar_programaciones_lctpc()
        # segundo correo distinto (otro id) con el mismo contenido
        self.correo = CorreoLCTPC(id='m2', asunto=ASUNTO_07, recibido=timezone.now())
        self._patch_graph()
        importar_programaciones_lctpc()
        m.refresh_from_db()
        self.assertEqual(m.observaciones.count('Cita LCTPC 617210'), 1)

    def test_ignora_modulaciones_en_estado_cerrado(self):
        _modulacion('GXYU5129072', estado='ENVIADO_BITACORA')
        self._patch_graph()
        resumen = importar_programaciones_lctpc()
        # como la única candidata está cerrada, se crea stub
        self.assertEqual(resumen.creadas, 10)
        self.assertEqual(
            Modulacion.objects.filter(contenedor='GXYU5129072').count(), 2
        )

    def test_dos_candidatas_activas_marca_ambigua(self):
        _modulacion('GXYU5129072')
        _modulacion('GXYU5129072')
        self._patch_graph()
        resumen = importar_programaciones_lctpc()
        self.assertEqual(resumen.ambiguas, 1)
        imp = ImportacionProgramacionLCTPC.objects.get(graph_message_id='m1')
        self.assertEqual(imp.estado, 'OK_CON_AVISOS')
        resultados = {d['contenedor']: d['resultado'] for d in imp.detalle}
        self.assertEqual(resultados['GXYU5129072'], 'ACTUALIZADA_AMBIGUA')

    def test_correo_sin_adjunto_xls_registra_error_y_sigue(self):
        self._patch_graph(dl_error=GraphError('sin adjunto'))
        resumen = importar_programaciones_lctpc()
        self.assertEqual(resumen.correos_con_error, 1)
        imp = ImportacionProgramacionLCTPC.objects.get(graph_message_id='m1')
        self.assertEqual(imp.estado, 'ERROR')
        self.assertIn('sin adjunto', imp.mensaje_error)

    def test_grapherror_al_listar_no_revienta(self):
        self._patch_graph(list_error=GraphError('token muerto'))
        resumen = importar_programaciones_lctpc()
        self.assertEqual(resumen.correos_procesados, 0)
        self.assertEqual(ImportacionProgramacionLCTPC.objects.count(), 0)

    def test_estado_ok_con_avisos_por_fecha_discrepante(self):
        self.correo = CorreoLCTPC(
            id='m1',
            asunto='Programacion de contenedores a SPF, para el 08 September 2026',
            recibido=timezone.now(),
        )
        self._patch_graph()
        importar_programaciones_lctpc()
        imp = ImportacionProgramacionLCTPC.objects.get(graph_message_id='m1')
        self.assertEqual(imp.estado, 'OK_CON_AVISOS')
        self.assertEqual(imp.fecha_modulacion_aduana, date(2026, 9, 8))
```

- [ ] **Step 2: Correr — deben fallar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ImportarProgramacionesTests --settings=test_settings -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'modulos.modulacion.services_importacion'`.

- [ ] **Step 3: Implementar `services_importacion.py`**

Crear `modulos/modulacion/services_importacion.py`:

```python
"""
Orquestador del import de programación de citas de LCTPC.

Recorre los correos del remitente configurado, salta los ya procesados
(`ImportacionProgramacionLCTPC.graph_message_id`), y por cada correo nuevo:
parsea el adjunto, clasifica FULL/SENCILLO y, por cada contenedor, actualiza
la Modulación activa de la terminal LCTPC o crea un stub incompleto.
Cada correo se procesa en su propia transacción y deja una fila de auditoría.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Agencia, ImportacionProgramacionLCTPC, Modulacion, TerminalPortuaria
from .services_graph import GraphError, descargar_adjunto_xls, listar_correos
from .services_lctpc import ErrorParseoLCTPC, clasificar, parsear_programacion

logger = logging.getLogger('modulos.modulacion')

_ESTADOS_CERRADOS = ('ENVIADO_BITACORA', 'RETIRADO_TERCERO')


@dataclass
class ResumenImportacion:
    correos_procesados: int = 0
    correos_saltados: int = 0
    correos_con_error: int = 0
    creadas: int = 0
    actualizadas: int = 0
    ambiguas: int = 0


def _aware(fecha, hora):
    return timezone.make_aware(datetime.combine(fecha, hora))


def _linea_observacion(r):
    return (
        f'Cita LCTPC {r.folio_lctpc} — reg {r.registro_inicio:%H:%M} / '
        f'cita {r.cita_inicio:%H:%M} ({r.tipo_cita})'
    )


def _anexar_observacion(modulacion, r):
    linea = _linea_observacion(r)
    if linea in (modulacion.observaciones or '').splitlines():
        return
    modulacion.observaciones = (
        f'{modulacion.observaciones}\n{linea}'.strip()
        if modulacion.observaciones else linea
    )


def _procesar_renglon(r, terminal, fecha):
    hora_reg = _aware(fecha, r.registro_inicio)
    hora_ing = _aware(fecha, r.cita_inicio)

    qs = (
        Modulacion.objects
        .filter(terminal_portuaria=terminal, contenedor=r.contenedor)
        .exclude(estado__in=_ESTADOS_CERRADOS)
        .order_by('-fecha_recepcion')
    )
    m = qs.first()
    if m:
        m.fecha_modulacion_aduana = fecha
        m.hora_registro = hora_reg
        m.hora_ingreso = hora_ing
        m.tipo_cita = r.tipo_cita
        m.grupo_cita = r.grupo_cita
        _anexar_observacion(m, r)
        m.save()
        resultado = 'ACTUALIZADA_AMBIGUA' if qs.count() > 1 else 'ACTUALIZADA'
    else:
        agencia = Agencia.objects.get_or_create(nombre='POR DEFINIR')[0]
        m = Modulacion.objects.create(
            agencia=agencia,
            terminal_portuaria=terminal,
            tipo_contenedor='',
            peso_toneladas=Decimal('0'),
            contenedor=r.contenedor,
            cliente=None,
            origen='LCTPC',
            estado='PENDIENTE',
            fecha_modulacion_aduana=fecha,
            hora_registro=hora_reg,
            hora_ingreso=hora_ing,
            tipo_cita=r.tipo_cita,
            grupo_cita=r.grupo_cita,
            observaciones=(
                'Creada desde programación LCTPC — faltan agencia/cliente/tipo/peso.\n'
                + _linea_observacion(r)
            ),
        )
        resultado = 'CREADA'

    return {
        'contenedor': r.contenedor,
        'folio_lctpc': r.folio_lctpc,
        'resultado': resultado,
        'modulacion_id': m.id,
        'tipo_cita': r.tipo_cita,
    }


def _procesar_correo(correo, resumen):
    try:
        xls = descargar_adjunto_xls(correo.id)
        prog = parsear_programacion(xls, correo.asunto)
        clasificar(prog.renglones)
    except (GraphError, ErrorParseoLCTPC) as exc:
        ImportacionProgramacionLCTPC.objects.create(
            graph_message_id=correo.id,
            asunto=correo.asunto,
            fecha_recibido=correo.recibido or timezone.now(),
            estado='ERROR',
            mensaje_error=str(exc)[:2000],
        )
        resumen.correos_con_error += 1
        logger.warning('Correo LCTPC %s con error: %s', correo.id, exc)
        return

    with transaction.atomic():
        terminal = TerminalPortuaria.objects.get_or_create(
            nombre=settings.MODULACION_TERMINAL_LCTPC
        )[0]
        detalle = []
        for r in prog.renglones:
            fila = _procesar_renglon(r, terminal, prog.fecha)
            detalle.append(fila)
            if fila['resultado'] == 'CREADA':
                resumen.creadas += 1
            elif fila['resultado'] == 'ACTUALIZADA_AMBIGUA':
                resumen.actualizadas += 1
                resumen.ambiguas += 1
            else:
                resumen.actualizadas += 1

        hay_ambiguas = any(f['resultado'] == 'ACTUALIZADA_AMBIGUA' for f in detalle)
        estado = 'OK_CON_AVISOS' if (prog.avisos or hay_ambiguas) else 'OK'
        ImportacionProgramacionLCTPC.objects.create(
            graph_message_id=correo.id,
            asunto=correo.asunto,
            fecha_recibido=correo.recibido or timezone.now(),
            fecha_modulacion_aduana=prog.fecha,
            estado=estado,
            total_renglones=len(prog.renglones),
            creadas=sum(1 for f in detalle if f['resultado'] == 'CREADA'),
            actualizadas=sum(1 for f in detalle if f['resultado'].startswith('ACTUALIZADA')),
            ambiguas=sum(1 for f in detalle if f['resultado'] == 'ACTUALIZADA_AMBIGUA'),
            detalle=detalle,
            mensaje_error='\n'.join(prog.avisos),
        )
    resumen.correos_procesados += 1


def importar_programaciones_lctpc() -> ResumenImportacion:
    resumen = ResumenImportacion()
    try:
        correos = listar_correos()
    except GraphError as exc:
        logger.error('No se pudieron listar los correos de LCTPC: %s', exc)
        return resumen

    ya_vistos = set(
        ImportacionProgramacionLCTPC.objects
        .filter(graph_message_id__in=[c.id for c in correos])
        .values_list('graph_message_id', flat=True)
    )
    for correo in correos:
        if correo.id in ya_vistos:
            resumen.correos_saltados += 1
            continue
        _procesar_correo(correo, resumen)

    return resumen
```

- [ ] **Step 4: Correr — deben pasar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ImportarProgramacionesTests --settings=test_settings -v 2`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add modulos/modulacion/services_importacion.py modulos/modulacion/tests_lctpc.py
git commit -m "feat(modulacion): orquestador de importación de programación LCTPC

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01L9VJK8wNw2vCheFNyGLcgV"
```

---

## Task 6: Management command + exclusión del scheduler

**Files:**
- Create: `modulos/modulacion/management/__init__.py`
- Create: `modulos/modulacion/management/commands/__init__.py`
- Create: `modulos/modulacion/management/commands/importar_programacion_lctpc.py`
- Modify: `modulos/reportes/apps.py`
- Modify: `modulos/modulacion/tests_lctpc.py`

**Interfaces:**
- Consumes: `importar_programaciones_lctpc` (Task 5)
- Produces: command `importar_programacion_lctpc` (sin argumentos) que llama al orquestador e imprime el resumen; `'importar_programacion_lctpc'` añadido a `_SKIP_COMMANDS` de `modulos/reportes/apps.py`

- [ ] **Step 1: Escribir el test (falla)**

Añadir a `modulos/modulacion/tests_lctpc.py`:

```python
from io import StringIO

from django.core.management import call_command

from modulos.modulacion.services_importacion import ResumenImportacion


class ImportarCommandTests(TestCase):
    @patch('modulos.modulacion.management.commands.importar_programacion_lctpc.importar_programaciones_lctpc')
    def test_command_llama_orquestador_e_imprime_resumen(self, mock_orq):
        mock_orq.return_value = ResumenImportacion(
            correos_procesados=1, creadas=3, actualizadas=7,
        )
        out = StringIO()
        call_command('importar_programacion_lctpc', stdout=out)
        mock_orq.assert_called_once()
        salida = out.getvalue()
        self.assertIn('3', salida)
        self.assertIn('7', salida)

    def test_command_esta_en_skip_commands_del_scheduler(self):
        from modulos.reportes.apps import _SKIP_COMMANDS
        self.assertIn('importar_programacion_lctpc', _SKIP_COMMANDS)
```

- [ ] **Step 2: Correr — debe fallar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ImportarCommandTests --settings=test_settings -v 2`
Expected: FAIL — `CommandError: Unknown command: 'importar_programacion_lctpc'`.

- [ ] **Step 3: Crear los paquetes y el command**

```bash
mkdir -p modulos/modulacion/management/commands
touch modulos/modulacion/management/__init__.py modulos/modulacion/management/commands/__init__.py
```

Crear `modulos/modulacion/management/commands/importar_programacion_lctpc.py`:

```python
"""
Management command: importar_programacion_lctpc

Lee el buzón de calidad por Microsoft Graph, procesa los correos de
programación de citas de LCTPC no vistos y actualiza/crea Modulaciones.

    python manage.py importar_programacion_lctpc

Pensado para correr desde el scheduler (cada 15 min) y a mano.
"""
from django.core.management.base import BaseCommand

from modulos.modulacion.services_importacion import importar_programaciones_lctpc


class Command(BaseCommand):
    help = 'Importa la programación de citas de LCTPC desde el buzón de calidad.'

    def handle(self, *args, **options):
        r = importar_programaciones_lctpc()
        self.stdout.write(
            'Programación LCTPC: '
            f'{r.correos_procesados} correo(s) procesado(s), '
            f'{r.correos_saltados} saltado(s), '
            f'{r.correos_con_error} con error. '
            f'Modulaciones: {r.creadas} creada(s), {r.actualizadas} actualizada(s) '
            f'({r.ambiguas} ambigua(s)).'
        )
```

- [ ] **Step 4: Añadir el command a `_SKIP_COMMANDS`**

En `modulos/reportes/apps.py`, dentro del `set` `_SKIP_COMMANDS`, agregar `'importar_programacion_lctpc'` (p. ej. al final, antes de la llave de cierre):

```python
_SKIP_COMMANDS = {
    'migrate', 'makemigrations', 'createsuperuser', 'collectstatic',
    'test', 'shell', 'dbshell', 'check', 'loaddata', 'dumpdata',
    'generar_reportes', 'inspectdb', 'showmigrations', 'sqlmigrate',
    'flush', 'help', 'importar_programacion_lctpc',
}
```

- [ ] **Step 5: Correr — deben pasar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ImportarCommandTests --settings=test_settings -v 2`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add modulos/modulacion/management modulos/reportes/apps.py modulos/modulacion/tests_lctpc.py
git commit -m "feat(modulacion): command importar_programacion_lctpc

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01L9VJK8wNw2vCheFNyGLcgV"
```

---

## Task 7: Job del scheduler (poll cada 15 min)

**Files:**
- Modify: `config/scheduler.py`
- Modify: `modulos/modulacion/tests_lctpc.py`

**Interfaces:**
- Consumes: `settings.MODULACION_LCTPC_POLL_MINUTOS` (Task 4); command `importar_programacion_lctpc` (Task 6)
- Produces: dentro de `iniciar_scheduler()`, un segundo `scheduler.add_job(..., trigger='interval', minutes=..., id='importar_programacion_lctpc', replace_existing=True, jobstore='default', misfire_grace_time=600)` cuya función es `_ejecutar_importacion_lctpc`

- [ ] **Step 1: Escribir el test (falla)**

Añadir a `modulos/modulacion/tests_lctpc.py`:

```python
from django.test import SimpleTestCase


class SchedulerJobLCTPCTests(SimpleTestCase):
    @patch('config.scheduler.BackgroundScheduler')
    def test_iniciar_scheduler_registra_job_lctpc(self, MockSched):
        from config.scheduler import iniciar_scheduler
        iniciar_scheduler()
        inst = MockSched.return_value
        ids = [c.kwargs.get('id') for c in inst.add_job.call_args_list]
        self.assertIn('importar_programacion_lctpc', ids)
        self.assertIn('generar_reportes_diario', ids)  # el job existente sigue
```

- [ ] **Step 2: Correr — debe fallar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.SchedulerJobLCTPCTests --settings=test_settings -v 2`
Expected: FAIL — `AssertionError: 'importar_programacion_lctpc' not found in [...]`.

- [ ] **Step 3: Añadir la función y el job**

En `config/scheduler.py`, después de `_ejecutar_reportes()`:

```python
def _ejecutar_importacion_lctpc():
    """Llama al command importar_programacion_lctpc desde el scheduler."""
    try:
        from django.core.management import call_command
        call_command('importar_programacion_lctpc')
    except Exception:
        logger.exception('Error ejecutando importar_programacion_lctpc desde el scheduler')
```

Dentro de `iniciar_scheduler()`, justo antes de `scheduler.start()`:

```python
    scheduler.add_job(
        func=_ejecutar_importacion_lctpc,
        trigger='interval',
        minutes=getattr(settings, 'MODULACION_LCTPC_POLL_MINUTOS', 15),
        id='importar_programacion_lctpc',
        replace_existing=True,
        jobstore='default',
        misfire_grace_time=600,
    )
```

- [ ] **Step 4: Correr — debe pasar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.SchedulerJobLCTPCTests --settings=test_settings -v 2`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add config/scheduler.py modulos/modulacion/tests_lctpc.py
git commit -m "feat(modulacion): job de scheduler para importar programación LCTPC cada 15 min

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01L9VJK8wNw2vCheFNyGLcgV"
```

---

## Task 8: UI — botón "Importar ahora", lista, detalle, admin

**Files:**
- Modify: `modulos/modulacion/views.py`
- Modify: `modulos/modulacion/urls.py`
- Modify: `modulos/modulacion/admin.py`
- Modify: `templates/modulacion/dashboard.html`
- Create: `templates/modulacion/importacion_lctpc_list.html`
- Create: `templates/modulacion/importacion_lctpc_detail.html`
- Modify: `modulos/modulacion/tests_lctpc.py`

**Interfaces:**
- Consumes: `importar_programaciones_lctpc` (Task 5), `ImportacionProgramacionLCTPC` (Task 1)
- Produces:
  - URL `modulacion:lctpc_importar` (`lctpc/importar/`, solo POST) → llama al orquestador, `messages`, redirige a `modulacion:dashboard`
  - URL `modulacion:lctpc_list` (`lctpc/`) → `ImportacionProgramacionLCTPCListView`
  - URL `modulacion:lctpc_detail` (`lctpc/<int:pk>/`) → `ImportacionProgramacionLCTPCDetailView`
  - `modulacion_dashboard` pasa `importaciones_lctpc` (últimas 10) al contexto

- [ ] **Step 1: Escribir los tests (fallan)**

Añadir a `modulos/modulacion/tests_lctpc.py`:

```python
from django.contrib.auth import get_user_model
from django.urls import reverse


class ImportacionLCTPCViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')
        self.client.force_login(self.user)

    def test_lista_requiere_login(self):
        self.client.logout()
        resp = self.client.get(reverse('modulacion:lctpc_list'))
        self.assertEqual(resp.status_code, 302)

    def test_boton_importar_llama_orquestador_y_redirige(self):
        with patch('modulos.modulacion.views.importar_programaciones_lctpc') as mock_orq:
            mock_orq.return_value = ResumenImportacion(correos_procesados=1, creadas=2)
            resp = self.client.post(reverse('modulacion:lctpc_importar'))
        mock_orq.assert_called_once()
        self.assertRedirects(resp, reverse('modulacion:dashboard'))

    def test_importar_solo_acepta_post(self):
        resp = self.client.get(reverse('modulacion:lctpc_importar'))
        self.assertEqual(resp.status_code, 405)

    def test_detalle_renderiza_filas(self):
        imp = ImportacionProgramacionLCTPC.objects.create(
            graph_message_id='m1', asunto=ASUNTO_07,
            fecha_recibido=timezone.now(), estado='OK', total_renglones=1,
            detalle=[{'contenedor': 'GXYU5129072', 'folio_lctpc': '617210',
                      'resultado': 'CREADA', 'modulacion_id': 1, 'tipo_cita': 'FULL'}],
        )
        resp = self.client.get(reverse('modulacion:lctpc_detail', args=[imp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'GXYU5129072')
        self.assertContains(resp, '617210')
```

- [ ] **Step 2: Correr — deben fallar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ImportacionLCTPCViewsTests --settings=test_settings -v 2`
Expected: FAIL — `NoReverseMatch: 'lctpc_list' is not a valid view function or pattern name`.

- [ ] **Step 3: Vistas**

En `modulos/modulacion/views.py`:

Añadir a los imports (junto a `from .models import ...`):

```python
from .models import Agencia, ImportacionProgramacionLCTPC, Modulacion, TerminalPortuaria
from .services_importacion import importar_programaciones_lctpc
```

En `modulacion_dashboard`, añadir al `context`:

```python
        'importaciones_lctpc': ImportacionProgramacionLCTPC.objects.all()[:10],
```

Al final del archivo:

```python
@login_required
@require_POST
def importar_programacion_lctpc(request):
    """Dispara el import de programación de citas de LCTPC bajo demanda."""
    r = importar_programaciones_lctpc()
    texto = (
        f'{r.correos_procesados} correo(s) procesado(s), {r.correos_saltados} sin cambios, '
        f'{r.correos_con_error} con error · {r.creadas} modulación(es) creada(s), '
        f'{r.actualizadas} actualizada(s).'
    )
    if r.correos_con_error or r.ambiguas:
        messages.warning(request, f'Importación LCTPC con avisos: {texto}')
    else:
        messages.success(request, f'Importación LCTPC: {texto}')
    return redirect('modulacion:dashboard')


class ImportacionProgramacionLCTPCListView(LoginRequiredMixin, ListView):
    model = ImportacionProgramacionLCTPC
    template_name = 'modulacion/importacion_lctpc_list.html'
    context_object_name = 'importaciones'
    paginate_by = 30


class ImportacionProgramacionLCTPCDetailView(LoginRequiredMixin, DetailView):
    model = ImportacionProgramacionLCTPC
    template_name = 'modulacion/importacion_lctpc_detail.html'
    context_object_name = 'importacion'
```

- [ ] **Step 4: URLs**

En `modulos/modulacion/urls.py`, añadir dentro de `urlpatterns` (antes del bloque `# API de recepción (HAL9MIL)`):

```python
    # Programación de citas de LCTPC (Graph API)
    path('lctpc/', views.ImportacionProgramacionLCTPCListView.as_view(), name='lctpc_list'),
    path('lctpc/importar/', views.importar_programacion_lctpc, name='lctpc_importar'),
    path('lctpc/<int:pk>/', views.ImportacionProgramacionLCTPCDetailView.as_view(), name='lctpc_detail'),
```

- [ ] **Step 5: Templates**

Crear `templates/modulacion/importacion_lctpc_list.html`:

```html
{% extends "base.html" %}

{% block title %}Programaciones LCTPC{% endblock %}

{% block content %}
<div class="max-w-7xl mx-auto py-4 px-4 sm:py-6">
    <div class="dash-page-header">
        <div>
            <h1 class="dash-page-title">Programaciones LCTPC</h1>
            <p class="dash-page-subtitle">Correos de citas de la terminal procesados automáticamente</p>
        </div>
        <div class="dash-page-actions">
            <form method="post" action="{% url 'modulacion:lctpc_importar' %}">
                {% csrf_token %}
                <button type="submit"
                        class="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-lg font-semibold text-sm transition min-h-[44px]">
                    Importar ahora
                </button>
            </form>
        </div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {% if importaciones %}
        <table class="w-full text-sm">
            <thead>
                <tr class="bg-gray-50 border-b border-gray-100 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    <th class="px-4 py-3">Recibido</th>
                    <th class="px-4 py-3">Asunto</th>
                    <th class="px-4 py-3">Estado</th>
                    <th class="px-4 py-3">Renglones</th>
                    <th class="px-4 py-3">Creadas</th>
                    <th class="px-4 py-3">Actualizadas</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
                {% for imp in importaciones %}
                <tr class="hover:bg-gray-50 transition cursor-pointer"
                    onclick="window.location='{% url 'modulacion:lctpc_detail' imp.pk %}'">
                    <td class="px-4 py-3">{{ imp.fecha_recibido|date:"d/m/Y H:i" }}</td>
                    <td class="px-4 py-3">{{ imp.asunto }}</td>
                    <td class="px-4 py-3">
                        {% if imp.estado == 'OK' %}
                        <span class="inline-block px-2 py-0.5 bg-green-100 text-green-700 text-xs font-semibold rounded-full">OK</span>
                        {% elif imp.estado == 'OK_CON_AVISOS' %}
                        <span class="inline-block px-2 py-0.5 bg-amber-100 text-amber-700 text-xs font-semibold rounded-full">Con avisos</span>
                        {% else %}
                        <span class="inline-block px-2 py-0.5 bg-red-100 text-red-700 text-xs font-semibold rounded-full">Error</span>
                        {% endif %}
                    </td>
                    <td class="px-4 py-3">{{ imp.total_renglones }}</td>
                    <td class="px-4 py-3">{{ imp.creadas }}</td>
                    <td class="px-4 py-3">{{ imp.actualizadas }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="py-16 text-center text-gray-400">
            <p class="text-lg font-medium">Sin programaciones procesadas</p>
        </div>
        {% endif %}
    </div>

    {% if is_paginated %}
    <div class="mt-4 flex gap-2 text-sm">
        {% if page_obj.has_previous %}<a class="text-emerald-700" href="?page={{ page_obj.previous_page_number }}">&larr; Anteriores</a>{% endif %}
        <span class="text-gray-500">Página {{ page_obj.number }} de {{ page_obj.paginator.num_pages }}</span>
        {% if page_obj.has_next %}<a class="text-emerald-700" href="?page={{ page_obj.next_page_number }}">Siguientes &rarr;</a>{% endif %}
    </div>
    {% endif %}
</div>
{% endblock %}
```

Crear `templates/modulacion/importacion_lctpc_detail.html`:

```html
{% extends "base.html" %}

{% block title %}Programación LCTPC — {{ importacion.fecha_recibido|date:"d/m/Y H:i" }}{% endblock %}

{% block content %}
<div class="max-w-7xl mx-auto py-4 px-4 sm:py-6">
    <div class="dash-page-header">
        <div>
            <h1 class="dash-page-title">{{ importacion.asunto }}</h1>
            <p class="dash-page-subtitle">
                Recibido {{ importacion.fecha_recibido|date:"d/m/Y H:i" }} ·
                Fecha de modulación: {{ importacion.fecha_modulacion_aduana|default:"—" }} ·
                Estado: {{ importacion.get_estado_display }}
            </p>
        </div>
        <div class="dash-page-actions">
            <a href="{% url 'modulacion:lctpc_list' %}"
               class="inline-flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg font-semibold text-sm transition min-h-[44px]">
                &larr; Volver
            </a>
        </div>
    </div>

    {% if importacion.mensaje_error %}
    <div class="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 whitespace-pre-line">{{ importacion.mensaje_error }}</div>
    {% endif %}

    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <table class="w-full text-sm">
            <thead>
                <tr class="bg-gray-50 border-b border-gray-100 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    <th class="px-4 py-3">Contenedor</th>
                    <th class="px-4 py-3">Folio LCTPC</th>
                    <th class="px-4 py-3">Tipo de cita</th>
                    <th class="px-4 py-3">Resultado</th>
                    <th class="px-4 py-3">Modulación</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
                {% for fila in importacion.detalle %}
                <tr>
                    <td class="px-4 py-3 font-medium text-gray-900">{{ fila.contenedor }}</td>
                    <td class="px-4 py-3">{{ fila.folio_lctpc }}</td>
                    <td class="px-4 py-3">{{ fila.tipo_cita }}</td>
                    <td class="px-4 py-3">{{ fila.resultado }}</td>
                    <td class="px-4 py-3">
                        {% if fila.modulacion_id %}
                        <a class="text-emerald-700" href="{% url 'modulacion:detail' fila.modulacion_id %}">#{{ fila.modulacion_id }}</a>
                        {% else %}—{% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Panel en el dashboard**

En `templates/modulacion/dashboard.html`, dentro de `.dash-page-actions` (antes del enlace "Ver lista"), añadir:

```html
            <a href="{% url 'modulacion:lctpc_list' %}"
               class="inline-flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg font-semibold text-sm transition min-h-[44px]">
                Programaciones LCTPC
            </a>
```

Y justo antes del `</div>` que cierra `.max-w-7xl` (después del bloque "Últimas modulaciones"), añadir:

```html
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden mt-6">
        <div class="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <h2 class="text-sm font-semibold text-gray-700">Programaciones LCTPC recientes</h2>
            <form method="post" action="{% url 'modulacion:lctpc_importar' %}">
                {% csrf_token %}
                <button type="submit"
                        class="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg font-semibold text-xs transition min-h-[36px]">
                    Importar ahora
                </button>
            </form>
        </div>
        {% if importaciones_lctpc %}
        <table class="w-full text-sm">
            <thead>
                <tr class="bg-gray-50 border-b border-gray-100 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    <th class="px-4 py-3">Recibido</th>
                    <th class="px-4 py-3">Asunto</th>
                    <th class="px-4 py-3">Estado</th>
                    <th class="px-4 py-3">Creadas / Actualizadas</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
                {% for imp in importaciones_lctpc %}
                <tr class="hover:bg-gray-50 transition cursor-pointer"
                    onclick="window.location='{% url 'modulacion:lctpc_detail' imp.pk %}'">
                    <td class="px-4 py-3">{{ imp.fecha_recibido|date:"d/m/Y H:i" }}</td>
                    <td class="px-4 py-3">{{ imp.asunto }}</td>
                    <td class="px-4 py-3">{{ imp.get_estado_display }}</td>
                    <td class="px-4 py-3">{{ imp.creadas }} / {{ imp.actualizadas }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="py-10 text-center text-gray-400"><p class="text-sm">Aún no se procesan programaciones de LCTPC.</p></div>
        {% endif %}
    </div>
```

- [ ] **Step 7: Admin**

En `modulos/modulacion/admin.py`:

```python
from .models import Agencia, ImportacionProgramacionLCTPC, Modulacion, TerminalPortuaria
```

En `ModulacionAdmin.list_display` añadir `'tipo_cita'` después de `'origen'`; en `list_filter` añadir `'tipo_cita'`.

Al final del archivo:

```python
@admin.register(ImportacionProgramacionLCTPC)
class ImportacionProgramacionLCTPCAdmin(admin.ModelAdmin):
    list_display = [
        'fecha_recibido', 'asunto', 'estado', 'fecha_modulacion_aduana',
        'total_renglones', 'creadas', 'actualizadas', 'ambiguas',
    ]
    list_filter = ['estado']
    search_fields = ['asunto', 'graph_message_id']
    date_hierarchy = 'fecha_recibido'
    ordering = ['-fecha_recibido']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
```

- [ ] **Step 8: Correr — deben pasar**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion.tests_lctpc.ImportacionLCTPCViewsTests --settings=test_settings -v 2`
Expected: PASS (4 tests).

- [ ] **Step 9: Correr toda la suite de la feature + la del módulo**

Run: `.venvKasu/bin/python manage.py test modulos.modulacion --settings=test_settings -v 1`
Expected: PASS (todo el módulo, incluidos los tests preexistentes de `tests.py`).

- [ ] **Step 10: Commit**

```bash
git add modulos/modulacion/views.py modulos/modulacion/urls.py modulos/modulacion/admin.py templates/modulacion/ modulos/modulacion/tests_lctpc.py
git commit -m "feat(modulacion): UI de importación LCTPC (botón, lista, detalle, admin)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01L9VJK8wNw2vCheFNyGLcgV"
```

---

## Task 9: Documentación (`CLAUDE.md`)

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Variables de entorno**

En la sección `## Environment Variables (`.env`)`, añadir al bloque:

```
# Microsoft Graph — importación de programación de citas de LCTPC
GRAPH_TENANT_ID=...
GRAPH_CLIENT_ID=...
GRAPH_CLIENT_SECRET=...            # permiso de aplicación Mail.Read
MODULACION_LCTPC_MAILBOX=calidad@transporteskasu.com.mx
MODULACION_LCTPC_REMITENTE=atencionspf@lctpc.com.mx
MODULACION_TERMINAL_LCTPC=L.C. Terminal Portuaria de Contenedores, S.A. de C.V.
MODULACION_LCTPC_POLL_MINUTOS=15
```

- [ ] **Step 2: Nota funcional**

En la tabla de módulos (`### Core Modules`), en la fila de un módulo `modulacion` si existe, o como nota bajo "Key Patterns", añadir:

```markdown
### Importación de programación de citas LCTPC (`modulos/modulacion/services_*`)
- Un job de APScheduler (cada `MODULACION_LCTPC_POLL_MINUTOS`, def. 15) y el botón
  "Importar ahora" del dashboard de modulación ejecutan
  `importar_programaciones_lctpc()`.
- `services_graph.py` lee el buzón por Microsoft Graph (app-only, `Mail.Read`);
  `services_lctpc.py` parsea el adjunto (tabla HTML con extensión `.xls`,
  ISO-8859-1) y clasifica FULL/SENCILLO por la hora de inicio de la ventana de
  registro (pares en orden del Excel; sobrante impar → SENCILLO).
- Por cada contenedor: se actualiza la Modulación de la terminal LCTPC no
  cerrada (rellena `fecha_modulacion_aduana`, `hora_registro`, `hora_ingreso`,
  `tipo_cita`, `grupo_cita`) o se crea un stub `origen='LCTPC'` incompleto.
- `ImportacionProgramacionLCTPC` da idempotencia (`graph_message_id` único) y
  el reporte por correo (contadores + `detalle` JSON).
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: importación de programación de citas LCTPC en modulación

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01L9VJK8wNw2vCheFNyGLcgV"
```

---

## Verificación final

- [ ] `.venvKasu/bin/python manage.py test modulos.modulacion --settings=test_settings` → toda la suite en verde.
- [ ] `.venvKasu/bin/python manage.py check` → sin errores.
- [ ] `.venvKasu/bin/python manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] Revisar `git log --oneline` → 9 commits, uno por tarea.
- [ ] Smoke manual (opcional, requiere credenciales Graph reales en `.env`):
      `.venvKasu/bin/python manage.py importar_programacion_lctpc` imprime el resumen sin trazas.

## Notas de despliegue (fuera del código)

- Registrar una aplicación en Entra ID (Azure AD) con **permiso de aplicación**
  `Mail.Read`, consentimiento de administrador, y un client secret.
- Idealmente acotar el acceso al solo buzón `calidad@transporteskasu.com.mx`
  con una *Application Access Policy* de Exchange Online.
- Poner `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` en el `.env`
  de producción. Sin ellos, el job y el botón reportan "Graph API no configurada"
  y no rompen nada.
