# Datos de terminal (carril/horarios) en Modulación — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar 5 campos operativos (carril, hora de registro/ingreso/carga, fecha de
modulación ante aduana) a `Modulacion`, y exponer un formulario público (sin login, token
firmado) para que el capturista de HAL9MIL los complete después de que el registro ya
existe, sin tocar el resto de la app.

**Architecture:** El registro `Modulacion` ya existe (lo crea `recibir_modulacion` cuando
HAL9MIL hace push). Este trabajo solo agrega: (1) los 5 campos nuevos + banderas de
configuración por terminal en el catálogo `TerminalPortuaria`, (2) un módulo pequeño
`tokens.py` que firma/valida un token opaco atado al `pk` de la `Modulacion`, (3) que
`recibir_modulacion` regrese ese link en su respuesta JSON, y (4) una vista pública nueva
(no requiere login) que usa el token para mostrar/guardar solo esos 5 campos de un único
registro, mientras su `estado` siga en `'PENDIENTE'`.

**Tech Stack:** Django 5.2.7, `django.core.signing` (firma de tokens, ya viene con Django,
sin dependencia nueva), SQLite (test/dev).

## Global Constraints

- Todo el código, `verbose_name` de modelos, mensajes de UI y comentarios van en español
  (convención del repo, ver `CLAUDE.md`).
- Los campos nuevos son `null=True, blank=True` (o `blank=True` para `CharField`) — nacen
  vacíos, igual que `fecha_patio_esperanza`/`fecha_retiro` ya existentes en `Modulacion`.
- La vista pública **no** lleva `LoginRequiredMixin` ni `@login_required` — es la única
  vista sin sesión del módulo. Sí usa el CSRF token normal de Django (se sirve y postea
  desde el propio dominio, el capturista solo abre el link en su navegador).
- Correr pruebas con: `python manage.py test modulos.modulacion`.
- Después de cualquier tarea que toque modelos: `python manage.py makemigrations --check
  --dry-run modulacion` debe no reportar cambios pendientes (o, si los reporta antes de
  generar la migración del propio task, es el resultado esperado de ese paso).

---

### Task 1: Modelo — campos nuevos en `Modulacion` y banderas en `TerminalPortuaria`

**Files:**
- Modify: `modulos/modulacion/models.py`
- Modify: `modulos/modulacion/admin.py`
- Modify: `modulos/modulacion/forms.py` (solo `TerminalPortuariaForm`)
- Create: `modulos/modulacion/migrations/0006_datos_terminal.py` (autogenerado por Django,
  el nombre exacto puede variar)
- Test: `modulos/modulacion/tests.py`

**Interfaces:**
- Produces: `Modulacion.carril` (`CharField`), `Modulacion.hora_registro`,
  `Modulacion.hora_ingreso`, `Modulacion.hora_carga` (`DateTimeField`),
  `Modulacion.fecha_modulacion_aduana` (`DateField`); `TerminalPortuaria.requiere_datos_extra`,
  `TerminalPortuaria.requiere_carril`, `TerminalPortuaria.requiere_hora_ingreso`,
  `TerminalPortuaria.requiere_hora_carga` (todos `BooleanField(default=False)`).

- [ ] **Step 1: Escribir la prueba que falla**

Agregar al final de `modulos/modulacion/tests.py` (después de `ModulacionModelTests`, antes
de `RecibirModulacionApiTests`):

```python
class DatosTerminalCamposTests(TestCase):
    def test_modulacion_nace_sin_datos_de_terminal(self):
        modulacion = _crear_modulacion()
        self.assertEqual(modulacion.carril, '')
        self.assertIsNone(modulacion.hora_registro)
        self.assertIsNone(modulacion.hora_ingreso)
        self.assertIsNone(modulacion.hora_carga)
        self.assertIsNone(modulacion.fecha_modulacion_aduana)

    def test_modulacion_guarda_datos_de_terminal(self):
        modulacion = _crear_modulacion(
            carril='7',
            hora_registro=timezone.now(),
            hora_ingreso=timezone.now(),
            hora_carga=timezone.now(),
            fecha_modulacion_aduana=timezone.localdate(),
        )
        modulacion.refresh_from_db()
        self.assertEqual(modulacion.carril, '7')
        self.assertIsNotNone(modulacion.hora_registro)
        self.assertIsNotNone(modulacion.hora_ingreso)
        self.assertIsNotNone(modulacion.hora_carga)
        self.assertIsNotNone(modulacion.fecha_modulacion_aduana)

    def test_terminal_portuaria_banderas_default_false(self):
        terminal = _crear_terminal('Terminal Sin Config')
        self.assertFalse(terminal.requiere_datos_extra)
        self.assertFalse(terminal.requiere_carril)
        self.assertFalse(terminal.requiere_hora_ingreso)
        self.assertFalse(terminal.requiere_hora_carga)
```

- [ ] **Step 2: Correr la prueba para verificar que falla**

Run: `python manage.py test modulos.modulacion.tests.DatosTerminalCamposTests -v 2`
Expected: FAIL — `AttributeError` o `TypeError: 'carril' is an invalid keyword argument`
(los campos todavía no existen en el modelo).

- [ ] **Step 3: Agregar los campos al modelo**

En `modulos/modulacion/models.py`, dentro de `class TerminalPortuaria(models.Model):`,
justo antes de `created_at = models.DateTimeField(auto_now_add=True)`:

```python
    requiere_datos_extra = models.BooleanField(
        default=False,
        verbose_name="Requiere datos de terminal",
        help_text="Si está activo, el correo de HAL9MIL incluye un link para "
                   "que el capturista complete carril/horarios de este contenedor.",
    )
    requiere_carril = models.BooleanField(default=False, verbose_name="Requiere carril")
    requiere_hora_ingreso = models.BooleanField(default=False, verbose_name="Requiere hora de ingreso")
    requiere_hora_carga = models.BooleanField(default=False, verbose_name="Requiere hora de carga")
```

Dentro de `class Modulacion(models.Model):`, justo antes de
`observaciones = models.TextField(blank=True, verbose_name="Observaciones")`:

```python
    carril = models.CharField(max_length=10, blank=True, verbose_name="Carril")
    hora_registro = models.DateTimeField(null=True, blank=True, verbose_name="Hora de registro")
    hora_ingreso = models.DateTimeField(null=True, blank=True, verbose_name="Hora de ingreso")
    hora_carga = models.DateTimeField(null=True, blank=True, verbose_name="Hora de carga")
    fecha_modulacion_aduana = models.DateField(
        null=True, blank=True, verbose_name="Fecha de modulación ante aduana",
    )
```

- [ ] **Step 4: Generar la migración**

Run: `python manage.py makemigrations modulacion`
Expected: crea un archivo nuevo en `modulos/modulacion/migrations/` (algo como
`0006_modulacion_carril_modulacion_fecha_modulacion_aduana_and_more.py`) listando los 9
campos nuevos (5 en `Modulacion`, 4 en `TerminalPortuaria`).

- [ ] **Step 5: Correr la prueba para verificar que pasa**

Run: `python manage.py test modulos.modulacion.tests.DatosTerminalCamposTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 6: Actualizar `TerminalPortuariaForm` para exponer las banderas**

En `modulos/modulacion/forms.py`, reemplazar la clase `TerminalPortuariaForm` completa por:

```python
class TerminalPortuariaForm(forms.ModelForm):
    class Meta:
        model = TerminalPortuaria
        fields = [
            'nombre', 'activo', 'requiere_datos_extra',
            'requiere_carril', 'requiere_hora_ingreso', 'requiere_hora_carga',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la terminal'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requiere_datos_extra': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requiere_carril': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requiere_hora_ingreso': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requiere_hora_carga': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
```

- [ ] **Step 7: Actualizar `TerminalPortuariaAdmin`**

En `modulos/modulacion/admin.py`, reemplazar la clase `TerminalPortuariaAdmin` por:

```python
@admin.register(TerminalPortuaria)
class TerminalPortuariaAdmin(admin.ModelAdmin):
    list_display = [
        'nombre', 'activo', 'requiere_datos_extra',
        'requiere_carril', 'requiere_hora_ingreso', 'requiere_hora_carga', 'created_at',
    ]
    list_filter = ['activo', 'requiere_datos_extra']
    search_fields = ['nombre']
```

- [ ] **Step 8: Correr toda la suite del módulo para verificar que nada se rompió**

Run: `python manage.py test modulos.modulacion -v 2`
Expected: PASS (todos los tests existentes + los 3 nuevos).

- [ ] **Step 9: Commit**

```bash
git add modulos/modulacion/models.py modulos/modulacion/admin.py modulos/modulacion/forms.py modulos/modulacion/migrations/ modulos/modulacion/tests.py
git commit -m "feat(modulacion): agrega campos de carril/horarios y banderas de terminal"
```

---

### Task 2: `tokens.py` — firmar y resolver el link del formulario público

**Files:**
- Create: `modulos/modulacion/tokens.py`
- Test: `modulos/modulacion/tests.py`

**Interfaces:**
- Consumes: `Modulacion` (Task 1, sin campos nuevos requeridos aquí, solo `pk`).
- Produces: `generar_token(modulacion) -> str`,
  `resolver_modulacion(token) -> Modulacion` (levanta `Modulacion.DoesNotExist` si el
  token es inválido, está manipulado, o el `pk` que contiene ya no existe).

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `modulos/modulacion/tests.py` (después de `DatosTerminalCamposTests`):

```python
from .tokens import generar_token, resolver_modulacion


class TokensCompletarDatosTests(TestCase):
    def test_generar_y_resolver_token_valido(self):
        modulacion = _crear_modulacion()
        token = generar_token(modulacion)
        resuelto = resolver_modulacion(token)
        self.assertEqual(resuelto.pk, modulacion.pk)

    def test_token_manipulado_levanta_does_not_exist(self):
        modulacion = _crear_modulacion()
        token = generar_token(modulacion)
        with self.assertRaises(Modulacion.DoesNotExist):
            resolver_modulacion(token + 'x')

    def test_token_de_modulacion_borrada_levanta_does_not_exist(self):
        modulacion = _crear_modulacion()
        token = generar_token(modulacion)
        modulacion.delete()
        with self.assertRaises(Modulacion.DoesNotExist):
            resolver_modulacion(token)
```

(El import `from .tokens import ...` va arriba del archivo, junto a los demás imports
relativos — se agrega en este mismo step aunque el módulo aún no exista, para que el
Step 2 falle por el motivo correcto.)

- [ ] **Step 2: Correr la prueba para verificar que falla**

Run: `python manage.py test modulos.modulacion.tests.TokensCompletarDatosTests -v 2`
Expected: FAIL con `ModuleNotFoundError: No module named 'modulos.modulacion.tokens'`.

- [ ] **Step 3: Crear `tokens.py`**

```python
"""
Token firmado para el formulario público de "completar datos de terminal"
(carril/horarios) en Modulación. No requiere tabla propia: el token es el
pk de la Modulación firmado con SECRET_KEY (django.core.signing), así que
es opaco y no se puede fabricar sin conocer la clave del proyecto.

Vigencia por estado, no por tiempo: el token no expira solo, pero
completar_datos_terminal (views.py) rechaza el acceso en cuanto
Modulacion.estado deja de ser 'PENDIENTE'.
"""
from django.core import signing

from .models import Modulacion

_SALT = 'modulacion.completar_datos_terminal'


def generar_token(modulacion):
    return signing.dumps({'modulacion_id': modulacion.pk}, salt=_SALT)


def resolver_modulacion(token):
    """Devuelve la Modulacion del token, o levanta Modulacion.DoesNotExist
    si el token es inválido, fue manipulado, o el registro ya no existe."""
    try:
        data = signing.loads(token, salt=_SALT)
        modulacion_id = data['modulacion_id']
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise Modulacion.DoesNotExist('Token inválido')
    return Modulacion.objects.select_related('terminal_portuaria').get(pk=modulacion_id)
```

- [ ] **Step 4: Correr la prueba para verificar que pasa**

Run: `python manage.py test modulos.modulacion.tests.TokensCompletarDatosTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modulos/modulacion/tokens.py modulos/modulacion/tests.py
git commit -m "feat(modulacion): token firmado para el link de completar datos de terminal"
```

---

### Task 3: `recibir_modulacion` regresa `completar_datos_url`

**Files:**
- Modify: `modulos/modulacion/views_api.py`
- Test: `modulos/modulacion/tests.py`

**Interfaces:**
- Consumes: `tokens.generar_token(modulacion) -> str` (Task 2),
  `TerminalPortuaria.requiere_datos_extra` (Task 1).
- Produces: la respuesta JSON de `POST /modulacion/api/recibir/` incluye la llave
  `completar_datos_url` (string) cuando la terminal del registro tiene
  `requiere_datos_extra=True`; la omite en caso contrario. Aplica tanto a la rama de
  creación como a la rama `duplicado`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar dentro de `class RecibirModulacionApiTests(TestCase):` en `tests.py`, después del
método `test_reutiliza_catalogos_existentes`:

```python
    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_terminal_sin_requiere_datos_extra_no_incluye_link(self):
        response = self._post(self.payload)  # terminal 'TIMSA', nace con banderas en False
        data = json.loads(response.content)
        self.assertNotIn('completar_datos_url', data)

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_terminal_con_requiere_datos_extra_incluye_link(self):
        terminal = _crear_terminal('LC Terminal Portuaria')
        terminal.requiere_datos_extra = True
        terminal.save()
        payload = dict(self.payload, terminal_portuaria='LC Terminal Portuaria')

        response = self._post(payload)
        data = json.loads(response.content)
        modulacion = Modulacion.objects.get(pk=data['id'])

        self.assertIn('completar_datos_url', data)
        prefijo = reverse('modulacion:completar_datos_terminal', args=['x']).replace('x/', '')
        self.assertIn(prefijo, data['completar_datos_url'])
        token = data['completar_datos_url'].rstrip('/').rsplit('/', 1)[-1]
        self.assertEqual(resolver_modulacion(token).pk, modulacion.pk)

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_duplicado_con_requiere_datos_extra_incluye_link(self):
        terminal = _crear_terminal('LC Terminal Portuaria')
        terminal.requiere_datos_extra = True
        terminal.save()
        payload = dict(self.payload, terminal_portuaria='LC Terminal Portuaria')

        self._post(payload)
        segunda = self._post(payload)
        data = json.loads(segunda.content)

        self.assertTrue(data.get('duplicado'))
        self.assertIn('completar_datos_url', data)
```

(La primera prueba extrae el `<token>` de `.../completar/<token>/` con
`rstrip('/').rsplit('/', 1)[-1]`, sin dar por hecho el dominio completo, y verifica dos
cosas: que la llave está presente y que el token adentro resuelve a la `Modulacion`
correcta vía `resolver_modulacion` — importado en Task 2 junto con `generar_token`.)

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python manage.py test modulos.modulacion.tests.RecibirModulacionApiTests -v 2`
Expected: las 3 pruebas nuevas FALLAN — `test_terminal_sin_requiere_datos_extra_no_incluye_link`
puede pasar de casualidad (la llave todavía no existe en ningún caso), pero las otras dos
fallan con `KeyError: 'completar_datos_url'` o `AssertionError` en el `assertIn`. Si la
primera pasa "gratis", no es problema — lo relevante es que las otras dos fallan antes del
Step 3.

- [ ] **Step 3: Implementar el helper y usarlo en ambas ramas**

En `modulos/modulacion/views_api.py`, agregar imports arriba (junto a los existentes):

```python
from django.urls import reverse

from .tokens import generar_token
```

Agregar la función, después de `_parsear_fecha_doda` y antes de `recibir_modulacion`:

```python
def _completar_datos_url(request, modulacion):
    """Link firmado para completar carril/horarios, o None si la terminal
    de esta modulación no requiere datos extra."""
    if not modulacion.terminal_portuaria.requiere_datos_extra:
        return None
    token = generar_token(modulacion)
    return request.build_absolute_uri(
        reverse('modulacion:completar_datos_terminal', args=[token])
    )
```

Modificar la rama `duplicado` (dentro de `recibir_modulacion`), que hoy dice:

```python
    if num_doda:
        existente = Modulacion.objects.filter(num_doda=num_doda, contenedor=contenedor).first()
        if existente:
            return JsonResponse({'success': True, 'id': existente.id, 'folio': existente.folio, 'duplicado': True}, status=200)
```

por:

```python
    if num_doda:
        existente = Modulacion.objects.select_related('terminal_portuaria').filter(
            num_doda=num_doda, contenedor=contenedor
        ).first()
        if existente:
            data = {'success': True, 'id': existente.id, 'folio': existente.folio, 'duplicado': True}
            url = _completar_datos_url(request, existente)
            if url:
                data['completar_datos_url'] = url
            return JsonResponse(data, status=200)
```

Modificar el `return` final de éxito, que hoy dice:

```python
    return JsonResponse({'success': True, 'id': modulacion.id, 'folio': modulacion.folio}, status=201)
```

por:

```python
    data = {'success': True, 'id': modulacion.id, 'folio': modulacion.folio}
    url = _completar_datos_url(request, modulacion)
    if url:
        data['completar_datos_url'] = url
    return JsonResponse(data, status=201)
```

**Nota:** `_completar_datos_url` hace `reverse('modulacion:completar_datos_terminal', ...)`,
que todavía no existe (se crea en Task 5) — hasta entonces, cualquier test que ejercite el
camino con `requiere_datos_extra=True` fallará con `NoReverseMatch`, lo cual es correcto:
ese es exactamente el estado "test que falla" para las pruebas de este Task antes de tener
la URL. Para que este Task quede verde de forma aislada (sin depender de Task 5), agregar
también aquí mismo la entrada mínima de URL (el Task 5 la completa con la vista real):

En `modulos/modulacion/urls.py`, agregar temporalmente, junto a las demás rutas del
módulo (antes de la línea `# API de recepción (HAL9MIL)`):

```python
    # Formulario público (sin login) para completar datos de terminal
    path('completar/<str:token>/', views.completar_datos_terminal, name='completar_datos_terminal'),
```

Y en `modulos/modulacion/views.py`, agregar un placeholder mínimo (Task 5 lo reemplaza por
la implementación completa):

```python
def completar_datos_terminal(request, token):
    from django.http import HttpResponse
    return HttpResponse(status=501)
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python manage.py test modulos.modulacion.tests.RecibirModulacionApiTests -v 2`
Expected: PASS (todas, incluidas las 3 nuevas).

- [ ] **Step 5: Correr toda la suite del módulo**

Run: `python manage.py test modulos.modulacion -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modulos/modulacion/views_api.py modulos/modulacion/urls.py modulos/modulacion/views.py modulos/modulacion/tests.py
git commit -m "feat(modulacion): recibir_modulacion regresa completar_datos_url cuando aplica"
```

---

### Task 4: `DatosTerminalForm` — subconjunto de campos según la terminal

**Files:**
- Modify: `modulos/modulacion/forms.py`
- Test: `modulos/modulacion/tests.py`

**Interfaces:**
- Consumes: `Modulacion` (Task 1), `TerminalPortuaria.requiere_carril` /
  `requiere_hora_ingreso` / `requiere_hora_carga` (Task 1).
- Produces: `DatosTerminalForm(instance=modulacion, terminal=terminal_portuaria,
  data=request.POST opcional)` — `ModelForm` cuyo conjunto de `fields` varía según las
  banderas de `terminal`. `hora_registro` y `fecha_modulacion_aduana` siempre presentes;
  `carril`, `hora_ingreso`, `hora_carga` presentes solo si la bandera correspondiente es
  `True`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests.py`, después de `TokensCompletarDatosTests`:

```python
from .forms import DatosTerminalForm


class DatosTerminalFormTests(TestCase):
    def test_terminal_sin_banderas_solo_expone_campos_comunes(self):
        terminal = _crear_terminal('APM Terminal Lazaro Cardenas')
        terminal.requiere_datos_extra = True
        terminal.save()
        modulacion = _crear_modulacion(terminal_portuaria=terminal)

        form = DatosTerminalForm(instance=modulacion, terminal=terminal)

        self.assertEqual(set(form.fields), {'hora_registro', 'fecha_modulacion_aduana'})

    def test_terminal_con_todas_las_banderas_expone_los_5_campos(self):
        terminal = _crear_terminal('LC Terminal Portuaria')
        terminal.requiere_datos_extra = True
        terminal.requiere_carril = True
        terminal.requiere_hora_ingreso = True
        terminal.requiere_hora_carga = True
        terminal.save()
        modulacion = _crear_modulacion(terminal_portuaria=terminal)

        form = DatosTerminalForm(instance=modulacion, terminal=terminal)

        self.assertEqual(
            set(form.fields),
            {'carril', 'hora_registro', 'hora_ingreso', 'hora_carga', 'fecha_modulacion_aduana'},
        )

    def test_guardar_form_actualiza_la_modulacion(self):
        terminal = _crear_terminal('LC Terminal Portuaria 2')
        terminal.requiere_datos_extra = True
        terminal.requiere_carril = True
        terminal.requiere_hora_ingreso = True
        terminal.requiere_hora_carga = True
        terminal.save()
        modulacion = _crear_modulacion(terminal_portuaria=terminal)

        form = DatosTerminalForm(data={
            'carril': '3',
            'hora_registro': '2026-09-05T08:00',
            'hora_ingreso': '2026-09-05T09:00',
            'hora_carga': '2026-09-05T10:00',
            'fecha_modulacion_aduana': '2026-09-05',
        }, instance=modulacion, terminal=terminal)

        self.assertTrue(form.is_valid(), form.errors)
        guardada = form.save()
        self.assertEqual(guardada.carril, '3')
        self.assertIsNotNone(guardada.hora_ingreso)
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python manage.py test modulos.modulacion.tests.DatosTerminalFormTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'DatosTerminalForm'`.

- [ ] **Step 3: Implementar el formulario**

En `modulos/modulacion/forms.py`, agregar al final del archivo:

```python
class DatosTerminalForm(forms.ModelForm):
    """Formulario público (sin login) para que el capturista de HAL9MIL
    complete carril/horarios de terminal. Solo expone estos 5 campos de
    Modulacion — nunca estado, unidad, operador, etc."""

    class Meta:
        model = Modulacion
        fields = ['carril', 'hora_registro', 'hora_ingreso', 'hora_carga', 'fecha_modulacion_aduana']
        widgets = {
            'carril': forms.TextInput(attrs={'class': 'form-input'}),
            'hora_registro': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
                'class': 'form-input', 'type': 'datetime-local'}),
            'hora_ingreso': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
                'class': 'form-input', 'type': 'datetime-local'}),
            'hora_carga': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
                'class': 'form-input', 'type': 'datetime-local'}),
            'fecha_modulacion_aduana': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'form-input', 'type': 'date'}),
        }

    def __init__(self, *args, terminal, **kwargs):
        super().__init__(*args, **kwargs)
        if not terminal.requiere_carril:
            del self.fields['carril']
        if not terminal.requiere_hora_ingreso:
            del self.fields['hora_ingreso']
        if not terminal.requiere_hora_carga:
            del self.fields['hora_carga']
```

`terminal` es un keyword-only argument obligatorio (sin default) — quien instancie el
formulario siempre debe pasarlo explícitamente; no hay caso de uso donde tenga sentido
omitirlo.

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python manage.py test modulos.modulacion.tests.DatosTerminalFormTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modulos/modulacion/forms.py modulos/modulacion/tests.py
git commit -m "feat(modulacion): DatosTerminalForm con subconjunto de campos por terminal"
```

---

### Task 5: Vista pública, URL final y templates

**Files:**
- Modify: `modulos/modulacion/views.py` (reemplaza el placeholder de Task 3)
- Create: `templates/modulacion/completar_datos_terminal.html`
- Create: `templates/modulacion/completar_datos_mensaje.html`
- Test: `modulos/modulacion/tests.py`

**Interfaces:**
- Consumes: `tokens.resolver_modulacion(token)` (Task 2, levanta `Modulacion.DoesNotExist`),
  `DatosTerminalForm(instance=..., terminal=..., data=...)` (Task 4).
- Produces: vista `completar_datos_terminal(request, token)` en
  `modulos/modulacion/views.py`, ya enlazada por la URL `modulacion:completar_datos_terminal`
  agregada en Task 3.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests.py`, después de `DatosTerminalFormTests`:

```python
class CompletarDatosTerminalViewTests(TestCase):
    def setUp(self):
        self.terminal = _crear_terminal('LC Terminal Portuaria 3')
        self.terminal.requiere_datos_extra = True
        self.terminal.requiere_carril = True
        self.terminal.requiere_hora_ingreso = True
        self.terminal.requiere_hora_carga = True
        self.terminal.save()
        self.modulacion = _crear_modulacion(terminal_portuaria=self.terminal)
        from .tokens import generar_token
        self.token = generar_token(self.modulacion)
        self.url = reverse('modulacion:completar_datos_terminal', args=[self.token])

    def test_token_invalido_devuelve_404(self):
        url = reverse('modulacion:completar_datos_terminal', args=['token-invalido'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_terminal_sin_requiere_datos_extra_devuelve_404(self):
        self.terminal.requiere_datos_extra = False
        self.terminal.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_estado_no_pendiente_muestra_mensaje_cerrado(self):
        self.modulacion.estado = 'MODULADO'
        self.modulacion.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ya no admite cambios')

    def test_get_muestra_formulario_con_campos_de_la_terminal(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="carril"')
        self.assertContains(response, 'name="hora_ingreso"')

    def test_post_valido_guarda_y_muestra_gracias(self):
        response = self.client.post(self.url, data={
            'carril': '5',
            'hora_registro': '2026-09-05T08:00',
            'hora_ingreso': '2026-09-05T09:00',
            'hora_carga': '2026-09-05T10:00',
            'fecha_modulacion_aduana': '2026-09-05',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Datos guardados')
        self.modulacion.refresh_from_db()
        self.assertEqual(self.modulacion.carril, '5')

    def test_no_permite_editar_estado_ni_otros_campos(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'name="estado"')
        self.assertNotContains(response, 'name="unidad"')
        self.assertNotContains(response, 'name="operador"')
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python manage.py test modulos.modulacion.tests.CompletarDatosTerminalViewTests -v 2`
Expected: FAIL — el placeholder de Task 3 responde 501 en todos los casos, y los templates
no existen todavía.

- [ ] **Step 3: Implementar la vista (reemplaza el placeholder de Task 3)**

En `modulos/modulacion/views.py`, agregar los imports que falten arriba del archivo:

```python
from .forms import DatosTerminalForm
from .tokens import resolver_modulacion
```

Reemplazar el placeholder `def completar_datos_terminal(request, token): ...` por:

```python
def completar_datos_terminal(request, token):
    """Vista pública (sin login): el capturista de HAL9MIL completa carril
    y horarios de terminal de un contenedor ya recibido. El token firmado
    (tokens.py) apunta a un único registro; el acceso se cierra en cuanto
    Modulacion.estado deja de ser 'PENDIENTE'."""
    try:
        modulacion = resolver_modulacion(token)
    except Modulacion.DoesNotExist:
        return render(request, 'modulacion/completar_datos_mensaje.html',
                      {'tipo': 'invalido'}, status=404)

    if not modulacion.terminal_portuaria.requiere_datos_extra:
        return render(request, 'modulacion/completar_datos_mensaje.html',
                      {'tipo': 'invalido'}, status=404)

    if modulacion.estado != 'PENDIENTE':
        return render(request, 'modulacion/completar_datos_mensaje.html',
                       {'tipo': 'cerrado', 'modulacion': modulacion})

    if request.method == 'POST':
        form = DatosTerminalForm(request.POST, instance=modulacion, terminal=modulacion.terminal_portuaria)
        if form.is_valid():
            form.save()
            return render(request, 'modulacion/completar_datos_mensaje.html',
                           {'tipo': 'gracias', 'modulacion': modulacion})
    else:
        form = DatosTerminalForm(instance=modulacion, terminal=modulacion.terminal_portuaria)

    return render(request, 'modulacion/completar_datos_terminal.html', {
        'form': form, 'modulacion': modulacion,
    })
```

- [ ] **Step 4: Crear el template del formulario**

`templates/modulacion/completar_datos_terminal.html` (standalone, mismo patrón que
`templates/registration/login.html` — no extiende `base.html`, que asume sesión iniciada):

```html
{% load static %}
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Completar datos de terminal - BitacoraKasu</title>
    <link rel="icon" type="image/png" href="{% static 'img/favicon.png' %}">
    <style>
        :root { --primary-color: #2C3E50; --dark-color: #2C3E50; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
            margin: 0;
        }
        .card {
            background: white; border-radius: 1rem;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            padding: 2.5rem; width: 100%; max-width: 480px; margin: 1rem;
        }
        .card-header { text-align: center; margin-bottom: 1.5rem; }
        .card-logo { height: 60px; margin-bottom: 1rem; }
        .card-title { color: var(--primary-color); font-size: 1.35rem; font-weight: 600; margin: 0; }
        .datos-modulacion {
            background: #f9fafb; border-radius: 0.5rem; padding: 1rem;
            margin-bottom: 1.5rem; font-size: 0.875rem; color: #374151;
        }
        .datos-modulacion strong { color: var(--dark-color); }
        .form-group { margin-bottom: 1.25rem; }
        .form-label {
            display: block; color: var(--dark-color); font-weight: 500;
            margin-bottom: 0.5rem; font-size: 0.875rem;
        }
        .form-input {
            width: 100%; padding: 0.75rem 1rem; border: 1px solid #d1d5db;
            border-radius: 0.5rem; font-size: 1rem; box-sizing: border-box;
        }
        .btn-guardar {
            width: 100%; padding: 0.875rem; background-color: var(--primary-color);
            color: white; border: none; border-radius: 0.5rem; font-size: 1rem;
            font-weight: 600; cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="card-header">
            <img src="{% static 'img/logo.png' %}" alt="Logo Kasu" class="card-logo">
            <h1 class="card-title">Completar datos de terminal</h1>
        </div>

        <div class="datos-modulacion">
            <strong>Folio:</strong> {{ modulacion.folio }}<br>
            <strong>Contenedor:</strong> {{ modulacion.contenedor }}<br>
            <strong>Terminal:</strong> {{ modulacion.terminal_portuaria.nombre }}<br>
            <strong>Cliente:</strong> {{ modulacion.cliente.nombre|default:"—" }}
        </div>

        <form method="post">
            {% csrf_token %}
            {% for field in form %}
            <div class="form-group">
                <label for="{{ field.id_for_label }}" class="form-label">{{ field.label }}</label>
                {{ field }}
                {% for error in field.errors %}
                <p style="color:#E74C3C; font-size:0.8rem; margin-top:0.25rem;">{{ error }}</p>
                {% endfor %}
            </div>
            {% endfor %}
            <button type="submit" class="btn-guardar">Guardar</button>
        </form>
    </div>
</body>
</html>
```

- [ ] **Step 5: Crear el template de mensaje**

`templates/modulacion/completar_datos_mensaje.html`:

```html
{% load static %}
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Completar datos de terminal - BitacoraKasu</title>
    <link rel="icon" type="image/png" href="{% static 'img/favicon.png' %}">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
            margin: 0;
        }
        .card {
            background: white; border-radius: 1rem;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            padding: 2.5rem; width: 100%; max-width: 420px; margin: 1rem; text-align: center;
        }
        .card-logo { height: 60px; margin-bottom: 1rem; }
        .mensaje { color: #2C3E50; font-size: 1rem; }
    </style>
</head>
<body>
    <div class="card">
        <img src="{% static 'img/logo.png' %}" alt="Logo Kasu" class="card-logo">
        {% if tipo == 'invalido' %}
        <p class="mensaje">Este link no es válido.</p>
        {% elif tipo == 'cerrado' %}
        <p class="mensaje">Esta modulación ya no admite cambios (folio {{ modulacion.folio }}).</p>
        {% elif tipo == 'gracias' %}
        <p class="mensaje">Datos guardados correctamente. Gracias.</p>
        {% endif %}
    </div>
</body>
</html>
```

- [ ] **Step 6: Correr las pruebas para verificar que pasan**

Run: `python manage.py test modulos.modulacion.tests.CompletarDatosTerminalViewTests -v 2`
Expected: PASS (6 tests).

- [ ] **Step 7: Correr toda la suite del módulo**

Run: `python manage.py test modulos.modulacion -v 2`
Expected: PASS — incluye también las pruebas de `RecibirModulacionApiTests` de Task 3,
que ahora ejercitan la URL real en vez del placeholder 501.

- [ ] **Step 8: Prueba manual rápida**

Levantar el servidor (`python manage.py runserver`), y en shell (`python manage.py shell`):

```python
from modulos.modulacion.tests import _crear_terminal, _crear_modulacion
from modulos.modulacion.tokens import generar_token
t = _crear_terminal('Prueba Manual')
t.requiere_datos_extra = True
t.requiere_carril = True
t.save()
m = _crear_modulacion(terminal_portuaria=t)
print(generar_token(m))
```

Abrir en el navegador `http://127.0.0.1:8000/modulacion/completar/<token impreso>/`,
confirmar que se ve el formulario con folio/contenedor/terminal correctos, guardar, y
confirmar el mensaje "Datos guardados correctamente."

- [ ] **Step 9: Commit**

```bash
git add modulos/modulacion/views.py templates/modulacion/completar_datos_terminal.html templates/modulacion/completar_datos_mensaje.html modulos/modulacion/tests.py
git commit -m "feat(modulacion): formulario público para completar carril/horarios de terminal"
```

---

## Orden de implementación

Task 1 → Task 2 → Task 3 → Task 4 → Task 5 (estrictamente secuencial: cada uno consume
interfaces del anterior). Al terminar Task 5, correr una vez más
`python manage.py test modulos.modulacion` completo antes de considerar el trabajo
terminado.

## Fuera de alcance de este plan

El lado de `Proyecto_HAL9MIL` (recolectar `completar_datos_url` por contenedor y agregarlo
al correo existente) es un plan aparte en ese repo — ver
`docs/superpowers/specs/2026-09-05-datos-terminal-modulacion-design.md` (commiteado en
ambos repos) para el contrato compartido.
