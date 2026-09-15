# Envío por WhatsApp del Programa de Despacho — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar a la pantalla del reporte "Programa de despacho" (`modulacion:reporte_despacho`) la opción de enviar, por WhatsApp vía WAHA, un mensaje de texto por cada grupo de cliente (mismo agrupamiento/orden/numeración que el `.xlsx`), a un número interno fijo configurado en settings, con vista previa obligatoria antes de confirmar el envío.

**Architecture:** Se extrae la agrupación/numeración de `modulos/modulacion/reportes.py` a una función pura compartida (`_agrupar_y_numerar`). Un nuevo módulo `mensajes_whatsapp.py` la reutiliza para construir el texto de cada mensaje. Dos vistas nuevas (previsualizar/enviar) reutilizan `config/services/whatsapp_service.enviar_mensaje` ya existente en el proyecto — sin dependencias nuevas.

**Tech Stack:** Django 5.2.7, WAHA (`config/services/whatsapp_service.py`, ya existente), `openpyxl` (sin cambios), Python 3.14.

## Global Constraints

- Todo el código, comentarios, `verbose_name` y texto de UI en español (proyecto es-mx).
- No agregar dependencias nuevas a `requirements.txt`.
- No modificar `config/services/twilio_service.py` ni `TWILIO_*` settings — esta feature usa WAHA exclusivamente.
- El envío va siempre al número fijo `settings.WA_PROGRAMA_DESPACHO_NUMERO`, nunca a `Cliente.celular`.
- El grupo sin cliente asignado (etiqueta `—`, `cliente_id is None`) nunca se envía por WhatsApp (sigue apareciendo solo en el `.xlsx`).
- El número de maniobra en los mensajes de WhatsApp debe coincidir exactamente con el que produce `construir_programa_despacho` para la misma fecha.
- Sin abreviaturas inventadas; sin comentarios explicando el qué (solo el porqué cuando no sea obvio).

---

### Task 1: Refactor — agrupación/numeración compartida en `reportes.py`

**Files:**
- Modify: `modulos/modulacion/reportes.py:102-186` (`construir_programa_despacho`)
- Test: `modulos/modulacion/tests_reporte.py` (existente — debe seguir pasando sin cambios; se añade un test nuevo para la función extraída)

**Interfaces:**
- Produces: `_agrupar_y_numerar(fecha) -> list[tuple[str, int | None, list[tuple[int, Modulacion]]]]`
  — una entrada `(etiqueta, cliente_id, items)` por grupo, en el orden ya definido por `_clave_orden`; `items` es `[(numero_maniobra, Modulacion), ...]` con `numero_maniobra` corrido de 1..N sobre **todo** el reporte (no reinicia por grupo).

- [ ] **Step 1: Escribir el test que fija el contrato de `_agrupar_y_numerar`**

Agregar a `modulos/modulacion/tests_reporte.py`, dentro de una nueva clase al final del archivo:

```python
from modulos.modulacion.reportes import _agrupar_y_numerar


class AgruparYNumerarTests(TestCase):
    def test_agrupa_y_numera_igual_que_el_xlsx(self):
        moy = Cliente.objects.create(nombre='Moya', alias='MOY')
        nol = Cliente.objects.create(nombre='Nolasco SA')  # sin alias
        _mod(cliente=moy, contenedor='AAAU1111111')
        _mod(cliente=moy, contenedor='AAAU2222222')
        _mod(cliente=nol, contenedor='BBBU3333333')
        _mod(cliente=None, contenedor='CCCU4444444')

        grupos = _agrupar_y_numerar(FECHA)

        etiquetas = [g[0] for g in grupos]
        self.assertEqual(etiquetas, ['MOY', 'Nolasco SA', '—'])

        cliente_ids = [g[1] for g in grupos]
        self.assertEqual(cliente_ids, [moy.pk, nol.pk, None])

        # numeración corrida 1..4 sobre todo el reporte, no por grupo
        todos_los_numeros = [num for _e, _c, items in grupos for num, _m in items]
        self.assertEqual(todos_los_numeros, [1, 2, 3, 4])

        contenedores_moy = [m.contenedor for _num, m in grupos[0][2]]
        self.assertEqual(contenedores_moy, ['AAAU1111111', 'AAAU2222222'])
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `python manage.py test modulos.modulacion.tests_reporte.AgruparYNumerarTests -v 2`
Expected: `ImportError: cannot import name '_agrupar_y_numerar'` (la función no existe aún).

- [ ] **Step 3: Implementar `_agrupar_y_numerar` y reescribir `construir_programa_despacho` para usarla**

En `modulos/modulacion/reportes.py`, reemplazar el cuerpo de `construir_programa_despacho` (líneas 102-186) por:

```python
def _agrupar_y_numerar(fecha):
    """
    Filtra, ordena, agrupa y numera las modulaciones de `fecha` igual que
    el xlsx: mismo orden (`_clave_orden`), mismo agrupamiento (`_clave_grupo`)
    y misma numeración de maniobra corrida sobre todo el reporte. La usan
    tanto `construir_programa_despacho` como `mensajes_whatsapp.py`, para
    que el número de maniobra coincida entre el xlsx y los mensajes de WA.

    Devuelve una lista de (etiqueta, cliente_id, items), donde items es
    [(numero_maniobra, Modulacion), ...].
    """
    modulaciones = sorted(
        Modulacion.objects
        .filter(fecha_modulacion_aduana=fecha)
        .select_related('cliente', 'operador', 'unidad', 'agencia', 'terminal_portuaria'),
        key=_clave_orden,
    )

    grupos = []
    maniobra = 0
    for _clave, grupo_iter in groupby(modulaciones, key=_clave_grupo):
        grupo = list(grupo_iter)
        items = []
        for m in grupo:
            maniobra += 1
            items.append((maniobra, m))
        grupos.append((_etiqueta_grupo(grupo[0]), grupo[0].cliente_id, items))
    return grupos


def construir_programa_despacho(fecha):
    grupos = _agrupar_y_numerar(fecha)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Programa de despacho'

    for col, texto in enumerate(ENCABEZADOS, start=1):
        c = ws.cell(row=1, column=col, value=texto)
        c.font = Font(bold=True)
        c.fill = _FILL_HEADER
        c.border = _BORDER
        c.alignment = _CENTRO_WRAP
    ws.merge_cells('J1:L1')
    ws['J1'].value = 'REGISTRO'
    ws['G1'].fill = _FILL_MORADO
    ws['H1'].fill = _FILL_MORADO
    for i, ancho in enumerate(_ANCHOS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.freeze_panes = 'A2'

    fila = 2
    for etiqueta, _cliente_id, items in grupos:
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=14)
        gc = ws.cell(row=fila, column=1, value=f'{etiqueta} — {len(items)} maniobra(s)')
        gc.font = Font(bold=True)
        gc.fill = _FILL_GRUPO
        fila += 1

        for maniobra, m in items:
            horas = [m.hora_registro, m.hora_ingreso, m.hora_carga]
            presentes = [h for h in horas if h is not None]
            operador_txt = (
                f'{m.operador.nombre}\n{_linea_unidad(m.unidad)}'.rstrip()
                if m.operador_id else _linea_unidad(m.unidad)
            )
            valores = [
                _fecha_es(fecha),
                m.terminal_portuaria.etiqueta if m.terminal_portuaria_id else '',
                m.agencia.nombre if m.agencia_id else '',
                _tipo(m),
                float(m.peso_toneladas) if m.peso_toneladas is not None else None,
                m.contenedor,
                operador_txt,
                _etiqueta_grupo(m),
                m.carril or 'NA',
                None, None, None,
                'SÍ' if m.sello_colocado else 'NO',
                maniobra,
            ]
            for col, v in enumerate(valores, start=1):
                c = ws.cell(row=fila, column=col, value=v)
                c.border = _BORDER
            ws.cell(row=fila, column=5).number_format = '0.00'
            ws.cell(row=fila, column=7).alignment = _WRAP
            ws.cell(row=fila, column=8).font = Font(bold=True)
            ws.row_dimensions[fila].height = 30

            if len(presentes) >= 2:
                for col, h in ((10, horas[0]), (11, horas[1]), (12, horas[2])):
                    c = ws.cell(row=fila, column=col, value=_texto_hora(h, fecha))
                    c.border = _BORDER
                    c.alignment = _CENTRO
                    if h is not None:
                        c.fill = _FILL_REG[col]
            else:
                ws.merge_cells(start_row=fila, start_column=10, end_row=fila, end_column=12)
                texto = _texto_hora(presentes[0], fecha) if presentes else 'CITA PENDIENTE'
                c = ws.cell(row=fila, column=10, value=texto)
                c.alignment = _CENTRO
                for col in (10, 11, 12):
                    ws.cell(row=fila, column=col).border = _BORDER
            fila += 1

    return wb
```

No se toca nada más del archivo (imports, constantes, funciones `_fecha_es`/`_hora_es`/etc. quedan igual).

- [ ] **Step 4: Correr el test nuevo y confirmar que pasa**

Run: `python manage.py test modulos.modulacion.tests_reporte.AgruparYNumerarTests -v 2`
Expected: `OK` (1 test).

- [ ] **Step 5: Correr toda la suite de `tests_reporte.py` para confirmar que no hay regresión**

Run: `python manage.py test modulos.modulacion.tests_reporte -v 2`
Expected: `OK`, todos los tests existentes (`ConstruirProgramaDespachoTests`, `ReporteDespachoViewTests`) siguen en verde.

- [ ] **Step 6: Commit**

```bash
git add modulos/modulacion/reportes.py modulos/modulacion/tests_reporte.py
git commit -m "$(cat <<'EOF'
refactor(modulacion): extrae agrupacion/numeracion del reporte a _agrupar_y_numerar

Prepara la reutilizacion de la misma agrupacion y numeracion de
maniobra (hoy solo en el xlsx) para los mensajes de WhatsApp.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Módulo `mensajes_whatsapp.py` — construcción de texto por grupo

**Files:**
- Create: `modulos/modulacion/mensajes_whatsapp.py`
- Test: Create `modulos/modulacion/tests_mensajes_whatsapp.py`

**Interfaces:**
- Consumes: `_agrupar_y_numerar(fecha)` de `modulos.modulacion.reportes` (Task 1); helpers `_fecha_es`, `_texto_hora` del mismo módulo.
- Produces: `construir_mensajes_whatsapp(fecha) -> list[tuple[Cliente, str]]` — un `(cliente, texto)` por grupo **con** cliente asignado (excluye el grupo `cliente_id is None`). `cliente` es la instancia real `modulos.bitacoras.models.Cliente` (se obtiene de `items[0][1].cliente`).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `modulos/modulacion/tests_mensajes_whatsapp.py`:

```python
import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from modulos.bitacoras.models import Cliente
from modulos.modulacion.mensajes_whatsapp import construir_mensajes_whatsapp
from modulos.modulacion.models import Agencia, Modulacion, TerminalPortuaria

FECHA = datetime.date(2026, 9, 11)


def _aware(y, mo, d, h, mi):
    return timezone.make_aware(datetime.datetime(y, mo, d, h, mi))


def _mod(**kw):
    kw.setdefault('agencia', Agencia.objects.get_or_create(nombre='LOGINCO')[0])
    kw.setdefault(
        'terminal_portuaria',
        TerminalPortuaria.objects.get_or_create(
            nombre='L.C. Terminal', defaults={'nombre_corto': 'LCTPC'})[0],
    )
    kw.setdefault('tipo_contenedor', '40HC')
    kw.setdefault('peso_toneladas', Decimal('0.00'))
    kw.setdefault('contenedor', 'CSNU6799471')
    kw.setdefault('fecha_modulacion_aduana', FECHA)
    return Modulacion.objects.create(**kw)


class ConstruirMensajesWhatsappTests(TestCase):
    def test_un_mensaje_por_cliente_excluye_sin_cliente(self):
        mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        nol = Cliente.objects.create(nombre='Nolasco SA', alias='NOL')
        _mod(cliente=mazal, contenedor='CSNU6799471')
        _mod(cliente=mazal, contenedor='CSLU6002657')
        _mod(cliente=nol, contenedor='BBBU3333333')
        _mod(cliente=None, contenedor='DDDU5555555')

        mensajes = construir_mensajes_whatsapp(FECHA)

        self.assertEqual(len(mensajes), 2)
        clientes_enviados = [c for c, _texto in mensajes]
        self.assertEqual(clientes_enviados, [mazal, nol])

    def test_contenido_del_mensaje_trae_encabezado_y_maniobras(self):
        mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        _mod(cliente=mazal, contenedor='CSNU6799471',
             hora_registro=_aware(2026, 9, 11, 10, 30),
             hora_ingreso=_aware(2026, 9, 11, 12, 0))
        _mod(cliente=mazal, contenedor='CSLU6002657')

        mensajes = construir_mensajes_whatsapp(FECHA)
        _cliente, texto = mensajes[0]

        self.assertIn('11-sep-26', texto)
        self.assertIn('MAZAL TOV IMPORTACIONES, SA DE CV', texto)
        self.assertIn('2 maniobra(s)', texto)
        self.assertIn('Maniobra Nº 1', texto)
        self.assertIn('Maniobra Nº 2', texto)
        self.assertIn('Contenedor: CSNU6799471', texto)
        self.assertIn('Contenedor: CSLU6002657', texto)
        self.assertIn('Registro:', texto)
        self.assertIn('CITA PENDIENTE', texto)  # el segundo contenedor no tiene horas

    def test_sin_clientes_en_la_fecha_devuelve_lista_vacia(self):
        self.assertEqual(construir_mensajes_whatsapp(FECHA), [])
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python manage.py test modulos.modulacion.tests_mensajes_whatsapp -v 2`
Expected: `ModuleNotFoundError: No module named 'modulos.modulacion.mensajes_whatsapp'`

- [ ] **Step 3: Implementar `mensajes_whatsapp.py`**

Crear `modulos/modulacion/mensajes_whatsapp.py`:

```python
"""
Construcción de los mensajes de WhatsApp del "Programa de despacho": un
texto por grupo de cliente, mismo contenido y numeración de maniobra que
el reporte xlsx (`reportes.py`). Módulo puro: no envía nada, no toca
request/response ni servicios externos.
"""
from .reportes import _agrupar_y_numerar, _fecha_es, _texto_hora


def _linea_horas(m, fecha):
    horas = [
        ('Registro', m.hora_registro),
        ('Ingreso', m.hora_ingreso),
        ('Carga', m.hora_carga),
    ]
    if not any(h for _etq, h in horas):
        return '  Horario: CITA PENDIENTE'
    return '\n'.join(
        f'  {etiqueta}: {_texto_hora(h, fecha) or "—"}' for etiqueta, h in horas
    )


def _bloque_maniobra(numero, m, fecha):
    operador_txt = m.operador.nombre if m.operador_id else '—'
    unidad_txt = (
        f'ECO {m.unidad.numero_economico} PLACAS {m.unidad.placa}'
        if m.unidad_id else ''
    )
    operador_unidad = f'{operador_txt} {unidad_txt}'.strip() if m.operador_id or m.unidad_id else '—'

    lineas = [
        f'Maniobra Nº {numero}',
        f'  Contenedor: {m.contenedor}',
        f'  Terminal: {m.terminal_portuaria.etiqueta if m.terminal_portuaria_id else "—"}',
        f'  Agencia: {m.agencia.nombre if m.agencia_id else "—"}',
        f'  Tipo: {m.tipo_contenedor or "—"}   Peso: {m.peso_toneladas if m.peso_toneladas is not None else "—"} t',
        f'  Operador/Unidad: {operador_unidad}',
        f'  Carril: {m.carril or "NA"}',
        _linea_horas(m, fecha),
        f'  Sello: {"SÍ" if m.sello_colocado else "NO"}',
    ]
    return '\n'.join(lineas)


def construir_mensajes_whatsapp(fecha):
    """
    Un (Cliente, texto) por cada grupo con cliente asignado, para la fecha
    dada. El grupo sin cliente (etiqueta '—') se omite — no hay a quién
    reenviárselo.
    """
    mensajes = []
    for etiqueta, cliente_id, items in _agrupar_y_numerar(fecha):
        if cliente_id is None:
            continue
        cliente = items[0][1].cliente
        bloques = '\n\n'.join(_bloque_maniobra(numero, m, fecha) for numero, m in items)
        partes = [
            f'*Programa de despacho — {_fecha_es(fecha)}*',
            f'*{etiqueta}* — {len(items)} maniobra(s)',
            '',
            bloques,
            '',
            '_BitacoraKasu — Modulación_',
        ]
        texto = '\n'.join(partes)
        mensajes.append((cliente, texto))
    return mensajes
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `python manage.py test modulos.modulacion.tests_mensajes_whatsapp -v 2`
Expected: `OK` (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modulos/modulacion/mensajes_whatsapp.py modulos/modulacion/tests_mensajes_whatsapp.py
git commit -m "$(cat <<'EOF'
feat(modulacion): construccion de mensajes WhatsApp del Programa de despacho

Un mensaje de texto por grupo de cliente, mismo contenido y numeracion
de maniobra que el xlsx. Reutiliza _agrupar_y_numerar; modulo puro,
no envia nada todavia.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Setting + vista previa + botón en `reporte_despacho.html`

**Files:**
- Modify: `config/settings.py` (junto al bloque `TWILIO_*`, líneas 226-233)
- Modify: `modulos/modulacion/urls.py`
- Modify: `modulos/modulacion/views.py`
- Modify: `templates/modulacion/reporte_despacho.html`
- Create: `templates/modulacion/whatsapp_preview.html`
- Test: `modulos/modulacion/tests_mensajes_whatsapp.py` (se añade una clase de test de vista al final)

**Interfaces:**
- Consumes: `construir_mensajes_whatsapp(fecha)` (Task 2); `_parse_fecha` ya existente en `views.py:626-630`.
- Produces: URL `modulacion:reporte_despacho_whatsapp_preview` (GET, `?fecha=YYYY-MM-DD`); context de template `mensajes` (lista de `{'cliente': Cliente, 'texto': str}`), `fecha`, `numero_configurado` (bool).

- [ ] **Step 1: Escribir los tests de la vista previa que fallan**

Agregar al final de `modulos/modulacion/tests_mensajes_whatsapp.py`:

```python
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse


class PrevisualizarWhatsappDespachoViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')

    def test_requiere_login(self):
        resp = self.client.get(reverse('modulacion:reporte_despacho_whatsapp_preview'))
        self.assertEqual(resp.status_code, 302)

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='5217531234567')
    def test_muestra_un_bloque_por_mensaje(self):
        self.client.force_login(self.user)
        mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        _mod(cliente=mazal, contenedor='CSNU6799471')
        resp = self.client.get(
            reverse('modulacion:reporte_despacho_whatsapp_preview'), {'fecha': FECHA.isoformat()})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'MAZAL TOV IMPORTACIONES, SA DE CV')
        self.assertContains(resp, 'Maniobra Nº 1')
        self.assertContains(resp, 'Confirmar y enviar')

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='')
    def test_sin_numero_configurado_deshabilita_envio(self):
        self.client.force_login(self.user)
        mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        _mod(cliente=mazal, contenedor='CSNU6799471')
        resp = self.client.get(
            reverse('modulacion:reporte_despacho_whatsapp_preview'), {'fecha': FECHA.isoformat()})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'WA_PROGRAMA_DESPACHO_NUMERO')
        self.assertNotContains(resp, 'Confirmar y enviar')

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='5217531234567')
    def test_sin_grupos_muestra_aviso(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse('modulacion:reporte_despacho_whatsapp_preview'), {'fecha': FECHA.isoformat()})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No hay maniobras con cliente asignado')


class ReporteDespachoBotonWhatsappTests(TestCase):
    def test_boton_vista_previa_presente(self):
        user = get_user_model().objects.create_user('u2', 'u2@e.com', 'pw')
        self.client.force_login(user)
        resp = self.client.get(reverse('modulacion:reporte_despacho'))
        self.assertContains(resp, reverse('modulacion:reporte_despacho_whatsapp_preview'))
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python manage.py test modulos.modulacion.tests_mensajes_whatsapp -v 2`
Expected: `NoReverseMatch: Reverse for 'reporte_despacho_whatsapp_preview' not found`

- [ ] **Step 3: Agregar el setting**

En `config/settings.py`, inmediatamente después de la línea `TWILIO_CONTENT_SID_BITACORA = env.str('TWILIO_CONTENT_SID_BITACORA', default='')` (línea 233):

```python

# WhatsApp interno (WAHA) — envío del Programa de despacho agrupado por cliente
WA_PROGRAMA_DESPACHO_NUMERO = env.str('WA_PROGRAMA_DESPACHO_NUMERO', default='')
```

- [ ] **Step 4: Agregar las URLs**

En `modulos/modulacion/urls.py`, después de la línea `path('reporte-despacho/xlsx/', ...)`:

```python
    path('reporte-despacho/whatsapp/preview/', views.previsualizar_whatsapp_despacho,
         name='reporte_despacho_whatsapp_preview'),
    path('reporte-despacho/whatsapp/enviar/', views.enviar_whatsapp_despacho,
         name='reporte_despacho_whatsapp_enviar'),
```

- [ ] **Step 5: Implementar la vista previa**

En `modulos/modulacion/views.py`:

1. Agregar el import, junto a `from .reportes import construir_programa_despacho` (línea 36):

```python
from .mensajes_whatsapp import construir_mensajes_whatsapp
```

2. Agregar al final del archivo (después de `descargar_programa_despacho`):

```python
@login_required
def previsualizar_whatsapp_despacho(request):
    fecha = _parse_fecha(request.GET.get('fecha')) or timezone.localdate()
    mensajes = construir_mensajes_whatsapp(fecha)
    return render(request, 'modulacion/whatsapp_preview.html', {
        'fecha': fecha.isoformat(),
        'mensajes': [{'cliente': c, 'texto': t} for c, t in mensajes],
        'numero_configurado': bool(settings.WA_PROGRAMA_DESPACHO_NUMERO),
    })
```

3. Agregar el import de `settings` si no está ya presente. Revisar el bloque de imports (líneas 1-38): `django.conf.settings` no aparece — agregarlo junto a los demás imports de `django`:

```python
from django.conf import settings
```

- [ ] **Step 6: Crear el template de vista previa**

Crear `templates/modulacion/whatsapp_preview.html`:

```html
{% extends "base.html" %}

{% block title %}Vista previa WhatsApp — Programa de despacho{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto py-6 space-y-4">
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div class="px-6 py-5 border-b border-gray-100">
            <h1 class="text-lg font-bold text-gray-900">Vista previa — WhatsApp</h1>
            <p class="text-sm text-gray-500 mt-0.5">
                {{ mensajes|length }} mensaje(s) para la fecha {{ fecha }}. Se enviarán al número
                interno configurado, uno por cliente, para reenvío manual.
            </p>
        </div>

        {% if not numero_configurado %}
        <div class="px-6 py-4 bg-amber-50 border-b border-amber-100 text-sm text-amber-800">
            Falta configurar <code>WA_PROGRAMA_DESPACHO_NUMERO</code> en el entorno. No se puede enviar.
        </div>
        {% elif not mensajes %}
        <div class="px-6 py-4 bg-gray-50 text-sm text-gray-600">
            No hay maniobras con cliente asignado para esta fecha.
        </div>
        {% endif %}
    </div>

    {% for m in mensajes %}
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div class="px-6 py-3 border-b border-gray-100 font-medium text-sm text-gray-700">
            {{ m.cliente }}
        </div>
        <pre class="px-6 py-4 text-sm text-gray-800 whitespace-pre-wrap">{{ m.texto }}</pre>
    </div>
    {% endfor %}

    {% if numero_configurado and mensajes %}
    <form method="post" action="{% url 'modulacion:reporte_despacho_whatsapp_enviar' %}"
          class="flex justify-end">
        {% csrf_token %}
        <input type="hidden" name="fecha" value="{{ fecha }}">
        <button type="submit"
                class="px-4 py-2 text-sm font-medium text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 transition min-h-[44px]">
            Confirmar y enviar
        </button>
    </form>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 7: Agregar el botón en `reporte_despacho.html`**

En `templates/modulacion/reporte_despacho.html`, después del `</form>` de descarga de Excel (línea 26) y antes del `</div>` de cierre de la tarjeta (línea 27):

```html
        <form method="get" action="{% url 'modulacion:reporte_despacho_whatsapp_preview' %}"
              class="px-6 py-5 border-t border-gray-100 flex justify-end">
            <input type="hidden" name="fecha" value="{{ fecha }}">
            <button type="submit"
                    class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition min-h-[44px]">
                Vista previa WhatsApp
            </button>
        </form>
```

Nota: el input de fecha del primer form no está ligado por JS al segundo — el botón "Vista previa WhatsApp" usa el valor inicial (`{{ fecha }}`, hoy por defecto) salvo que el usuario haya cambiado el campo del primer form antes de hacer submit del segundo. Es aceptable para esta primera versión: el usuario puede ajustar la fecha directamente en la pantalla de vista previa si hace falta (fuera de alcance agregar JS de sincronización de campos — no se pidió).

- [ ] **Step 8: Correr los tests y confirmar que pasan**

Run: `python manage.py test modulos.modulacion.tests_mensajes_whatsapp -v 2`
Expected: `OK` (7 tests: 3 de `ConstruirMensajesWhatsappTests` + 3 de `PrevisualizarWhatsappDespachoViewTests` + 1 de `ReporteDespachoBotonWhatsappTests`).

- [ ] **Step 9: Correr la suite completa de `modulacion` para confirmar que no hay regresión**

Run: `python manage.py test modulos.modulacion -v 2`
Expected: `OK`, sin fallos ni errores.

- [ ] **Step 10: Commit**

```bash
git add config/settings.py modulos/modulacion/urls.py modulos/modulacion/views.py \
        modulos/modulacion/tests_mensajes_whatsapp.py \
        templates/modulacion/reporte_despacho.html templates/modulacion/whatsapp_preview.html
git commit -m "$(cat <<'EOF'
feat(modulacion): vista previa de envio WhatsApp del Programa de despacho

Nuevo setting WA_PROGRAMA_DESPACHO_NUMERO, boton en la pantalla del
reporte, y pantalla de vista previa que muestra el texto exacto de
cada mensaje antes de confirmar el envio (Task 4).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Vista de envío — `enviar_whatsapp_despacho`

**Files:**
- Modify: `modulos/modulacion/views.py`
- Test: `modulos/modulacion/tests_mensajes_whatsapp.py`

**Interfaces:**
- Consumes: `construir_mensajes_whatsapp(fecha)` (Task 2); `config.services.whatsapp_service.enviar_mensaje(texto, numeros=[...]) -> bool`.
- Produces: URL `modulacion:reporte_despacho_whatsapp_enviar` (`POST`, campo `fecha`); redirige a `modulacion:reporte_despacho?fecha=...` con `django.contrib.messages` de resumen.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `modulos/modulacion/tests_mensajes_whatsapp.py`:

```python
from unittest.mock import patch


class EnviarWhatsappDespachoViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u3', 'u3@e.com', 'pw')
        self.client.force_login(self.user)
        self.mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        self.nol = Cliente.objects.create(nombre='Nolasco SA', alias='NOL')
        _mod(cliente=self.mazal, contenedor='CSNU6799471')
        _mod(cliente=self.nol, contenedor='BBBU3333333')

    def test_requiere_login(self):
        self.client.logout()
        resp = self.client.post(
            reverse('modulacion:reporte_despacho_whatsapp_enviar'), {'fecha': FECHA.isoformat()})
        self.assertEqual(resp.status_code, 302)

    def test_rechaza_get(self):
        resp = self.client.get(
            reverse('modulacion:reporte_despacho_whatsapp_enviar'), {'fecha': FECHA.isoformat()})
        self.assertEqual(resp.status_code, 405)

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='5217531234567')
    @patch('modulos.modulacion.views.enviar_mensaje')
    def test_envia_un_mensaje_por_grupo_con_el_numero_configurado(self, mock_enviar):
        mock_enviar.return_value = True
        resp = self.client.post(
            reverse('modulacion:reporte_despacho_whatsapp_enviar'), {'fecha': FECHA.isoformat()})
        self.assertRedirects(
            resp, f"{reverse('modulacion:reporte_despacho')}?fecha={FECHA.isoformat()}")
        self.assertEqual(mock_enviar.call_count, 2)
        for llamada in mock_enviar.call_args_list:
            self.assertEqual(llamada.kwargs['numeros'], ['5217531234567'])

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='5217531234567')
    @patch('modulos.modulacion.views.enviar_mensaje')
    def test_reporta_fallos_por_cliente(self, mock_enviar):
        mock_enviar.side_effect = [True, False]
        resp = self.client.post(
            reverse('modulacion:reporte_despacho_whatsapp_enviar'), {'fecha': FECHA.isoformat()},
            follow=True)
        mensajes = [str(m) for m in resp.context['messages']]
        self.assertTrue(any('1' in m and 'enviad' in m for m in mensajes))
        self.assertTrue(any('Nolasco SA' in m or 'NOL' in m for m in mensajes))

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='')
    @patch('modulos.modulacion.views.enviar_mensaje')
    def test_sin_numero_configurado_no_envia_nada(self, mock_enviar):
        resp = self.client.post(
            reverse('modulacion:reporte_despacho_whatsapp_enviar'), {'fecha': FECHA.isoformat()},
            follow=True)
        mock_enviar.assert_not_called()
        mensajes = [str(m) for m in resp.context['messages']]
        self.assertTrue(any('WA_PROGRAMA_DESPACHO_NUMERO' in m for m in mensajes))
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python manage.py test modulos.modulacion.tests_mensajes_whatsapp.EnviarWhatsappDespachoViewTests -v 2`
Expected: `NoReverseMatch` o `AttributeError: module 'modulos.modulacion.views' has no attribute 'enviar_mensaje'` (aún no se importó ni se creó la vista).

- [ ] **Step 3: Implementar la vista**

En `modulos/modulacion/views.py`:

1. Agregar el import de la función de envío, junto al de `construir_mensajes_whatsapp` (línea agregada en Task 3). Se importa la función directamente (no el módulo) para que sea *patcheable* como `modulos.modulacion.views.enviar_mensaje` en los tests:

```python
from config.services.whatsapp_service import enviar_mensaje
```

2. Agregar al final del archivo:

```python
@login_required
@require_POST
def enviar_whatsapp_despacho(request):
    fecha = _parse_fecha(request.POST.get('fecha')) or timezone.localdate()
    destino = f"{reverse('modulacion:reporte_despacho')}?fecha={fecha.isoformat()}"

    numero = settings.WA_PROGRAMA_DESPACHO_NUMERO
    if not numero:
        messages.error(request, 'WA_PROGRAMA_DESPACHO_NUMERO no está configurado. No se envió nada.')
        return redirect(destino)

    mensajes = construir_mensajes_whatsapp(fecha)
    if not mensajes:
        messages.warning(request, 'No hay maniobras con cliente asignado para esta fecha.')
        return redirect(destino)

    enviados = 0
    fallidos = []
    for cliente, texto in mensajes:
        if enviar_mensaje(texto, numeros=[numero]):
            enviados += 1
        else:
            fallidos.append(str(cliente))

    if enviados:
        messages.success(request, f'{enviados} mensaje(s) de WhatsApp enviado(s).')
    if fallidos:
        messages.error(
            request,
            f'No se pudo enviar a: {", ".join(fallidos)}. Reintenta desde la vista previa.',
        )

    return redirect(destino)
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `python manage.py test modulos.modulacion.tests_mensajes_whatsapp -v 2`
Expected: `OK` (12 tests en total en el archivo).

- [ ] **Step 5: Correr la suite completa del proyecto para confirmar que no hay regresión**

Run: `python manage.py test`
Expected: `OK`, sin fallos ni errores en ningún módulo.

- [ ] **Step 6: Commit**

```bash
git add modulos/modulacion/views.py modulos/modulacion/tests_mensajes_whatsapp.py
git commit -m "$(cat <<'EOF'
feat(modulacion): envio por WhatsApp del Programa de despacho por cliente

Envia un mensaje por grupo de cliente via WAHA al numero configurado
en WA_PROGRAMA_DESPACHO_NUMERO. Reporta enviados/fallidos por
django.contrib.messages para reenvio manual desde la vista previa.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Post-implementation (fuera de las tareas, manual)

- Agregar `WA_PROGRAMA_DESPACHO_NUMERO=5217531234567` (número real de atención a clientes) al `.env` de cada entorno (dev/staging/prod). No se toca `.env` desde el código — es configuración de despliegue.
