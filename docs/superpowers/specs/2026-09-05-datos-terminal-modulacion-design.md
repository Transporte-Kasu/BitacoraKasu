# Captura de datos de terminal (carril/horarios) en Modulación vía link público

Fecha: 2026-09-05
Repos afectados: `BitacoraKasu` (este repo, lado receptor/formulario) y `Proyecto_HAL9MIL`
(lado emisor/correo) — mismo documento de diseño commiteado en ambos, cada uno con su
propia spec/plan de implementación.
Módulos afectados en este repo: `modulos/modulacion`

## Contexto

Hoy la comunicación entre HAL9MIL y BitacoraKasu es de un solo sentido: HAL9MIL sincroniza
el DODA desde Firebird y hace `POST /modulacion/api/recibir/` (uno por contenedor) que crea
un registro `Modulacion` con los datos que ya trae el pedimento/DODA (terminal, tipo de
contenedor, peso, cliente, num_pedimento, num_doda, etc. — ver `views_api.py`).

Faltan 5 campos que **no vienen de Firebird**: los conoce el capturista de HAL9MIL (la
agencia aduanal LOGINCO) recién agenda la cita de extracción con la terminal portuaria,
**después** de que el DODA ya se sincronizó y el `Modulacion` ya existe en BitacoraKasu:

| Campo | Aplica a |
|---|---|
| `hora_registro` | L.C. Terminal Portuaria de Contenedores **y** APM Terminal Lazaro Cardenas |
| `fecha_modulacion_aduana` | L.C. Terminal Portuaria de Contenedores **y** APM Terminal Lazaro Cardenas |
| `carril` | Solo L.C. Terminal Portuaria de Contenedores |
| `hora_ingreso` | Solo L.C. Terminal Portuaria de Contenedores |
| `hora_carga` | Solo L.C. Terminal Portuaria de Contenedores |

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Dónde vive el formulario de captura | **En BitacoraKasu**, como vista pública sin login (no en HAL9MIL). |
| Cómo llega el capturista | HAL9MIL le manda el link dentro del **mismo correo** que ya envía hoy al crear el DODA (PDF + aviso de extracción); no hay correo nuevo. |
| Quién genera el link | **BitacoraKasu**, al crear (o reencontrar) el `Modulacion` — lo regresa en la respuesta JSON de `recibir_modulacion`. HAL9MIL solo lo reenvía. |
| Alcance por terminal | Solo terminales con la bandera `TerminalPortuaria.requiere_datos_extra=True`. Configurable desde el catálogo (no hardcodeado por nombre). |
| Vigencia del link | Editable **solo mientras `Modulacion.estado == 'PENDIENTE'`**. En cuanto cambia de estado, el link deja de funcionar (muestra "ya no se puede editar"). Sin expiración por tiempo. |
| Seguridad del token | Firmado con `django.core.signing.dumps/loads` (no adivinable, no requiere tabla de tokens aparte). El formulario solo expone estos 5 campos de un único registro — nunca `estado`, `unidad`, `operador`, etc. |
| Campo nuevo pedido por el usuario | `fecha_modulacion_aduana` — captura manual del capturista, común a ambas terminales, junto con los demás. |

---

## Parte A — Modelo y catálogo

### A1. `Modulacion` (`modulos/modulacion/models.py`)

Nuevos campos, todos opcionales a nivel BD (igual patrón que `fecha_patio_esperanza`/
`fecha_retiro` ya existentes — nacen vacíos y se llenan después):

| Campo | Tipo | Verbose name |
|---|---|---|
| `carril` | `CharField(max_length=10, blank=True)` | "Carril" |
| `hora_registro` | `DateTimeField(null=True, blank=True)` | "Hora de registro" |
| `hora_ingreso` | `DateTimeField(null=True, blank=True)` | "Hora de ingreso" |
| `hora_carga` | `DateTimeField(null=True, blank=True)` | "Hora de carga" |
| `fecha_modulacion_aduana` | `DateField(null=True, blank=True)` | "Fecha de modulación ante aduana" |

Migración nueva (siguiente número disponible en `modulos/modulacion/migrations/`).

### A2. `TerminalPortuaria` (`modulos/modulacion/models.py`)

Banderas de configuración (evita comparar `nombre` contra strings fijos en el código —
así una tercera terminal se da de alta desde el catálogo sin tocar código):

| Campo | Tipo | Default |
|---|---|---|
| `requiere_datos_extra` | `BooleanField` | `False` — si es `False`, `recibir_modulacion` no genera link y el formulario público no aplica. |
| `requiere_carril` | `BooleanField` | `False` |
| `requiere_hora_ingreso` | `BooleanField` | `False` |
| `requiere_hora_carga` | `BooleanField` | `False` |

`hora_registro` y `fecha_modulacion_aduana` se muestran siempre que
`requiere_datos_extra=True` (son comunes a ambas terminales del alcance actual).

Carga inicial de datos: alta/edición manual desde el catálogo ya existente
(`TerminalPortuariaUpdateView`, o `/admin/`) — no requiere migración de datos ni fixture.
Configurar `L.C. Terminal Portuaria de Contenedores, S.A. de C.V.` con las 4 banderas en
`True`; `APM Terminal Lazaro Cardenas, S.A de C.V.` solo con `requiere_datos_extra=True`.
Si esos registros de `TerminalPortuaria` aún no existen (la terminal llega vía
`get_or_create` desde `recibir_modulacion`), crearlos primero con esas banderas antes de
que llegue el siguiente push, o editarlos después de que HAL9MIL los cree automáticamente.

### A3. Admin y formulario del catálogo

- `TerminalPortuariaAdmin.list_display` += las 4 banderas nuevas.
- `TerminalPortuariaForm` (`forms.py`) += las 4 banderas como `CheckboxInput` (para que se
  puedan configurar desde el CRUD del módulo, no solo desde `/admin/`).
- `ModulacionAdmin`: agregar los 5 campos nuevos a la vista de cambio (no necesariamente a
  `list_display`, para no saturar la lista).

---

## Parte B — Endpoint de recepción: regresar el link

### B1. `views_api.py::recibir_modulacion`

Nuevo helper:

```python
from django.core import signing
from django.urls import reverse

def _completar_datos_url(request, modulacion):
    """Link firmado para completar carril/horarios, o None si la terminal
    de esta modulación no requiere datos extra."""
    if not modulacion.terminal_portuaria.requiere_datos_extra:
        return None
    token = signing.dumps({'modulacion_id': modulacion.id})
    return request.build_absolute_uri(
        reverse('modulacion:completar_datos_terminal', args=[token])
    )
```

Se agrega `completar_datos_url` a **ambas** ramas de respuesta:

- Rama `duplicado` (registro ya existente por `num_doda`+`contenedor`): usar
  `existente.terminal_portuaria` (ya cargado) para el helper — hoy esta rama regresa antes
  de resolver `terminal_portuaria`, así que no cambia el orden del resto de la función.
- Rama de creación exitosa: después de `Modulacion.objects.create(...)`.

Contrato de respuesta resultante (ejemplo, terminal con `requiere_datos_extra=True`):

```json
{
  "success": true,
  "id": 123,
  "folio": "MOD-20260905-007",
  "completar_datos_url": "https://bitacora.kasu.com.mx/modulacion/completar/<token>/"
}
```

Cuando la terminal no aplica, `completar_datos_url` simplemente no aparece en el JSON (no
se manda como `null` explícito ni se cambia el resto del contrato — retrocompatible con
cualquier consumidor que ignore llaves desconocidas).

---

## Parte C — Vista pública del formulario

### C1. Form (`forms.py`)

```python
class DatosTerminalForm(forms.ModelForm):
    """Formulario público (sin login) para que el capturista de HAL9MIL
    complete carril/horarios de terminal. Solo expone estos 5 campos de
    Modulacion — nunca estado, unidad, operador, etc."""

    class Meta:
        model = Modulacion
        fields = ['carril', 'hora_registro', 'hora_ingreso', 'hora_carga', 'fecha_modulacion_aduana']
        widgets = {
            'carril': forms.TextInput(attrs={'class': 'form-control'}),
            'hora_registro': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
                'class': 'form-control', 'type': 'datetime-local'}),
            'hora_ingreso': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
                'class': 'form-control', 'type': 'datetime-local'}),
            'hora_carga': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
                'class': 'form-control', 'type': 'datetime-local'}),
            'fecha_modulacion_aduana': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'form-control', 'type': 'date'}),
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

`terminal` es un kwarg **obligatorio** (no `None` por default): la vista siempre lo pasa,
ya validó antes que `requiere_datos_extra=True`.

### C2. Vista (`views.py`)

```python
def completar_datos_terminal(request, token):
    try:
        data = signing.loads(token)
        modulacion = Modulacion.objects.select_related('terminal_portuaria').get(
            pk=data['modulacion_id']
        )
    except (signing.BadSignature, KeyError, Modulacion.DoesNotExist):
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

Sin `@login_required` ni `LoginRequiredMixin` — es la única vista pública del módulo.
`csrf_exempt` **no** hace falta: el formulario se sirve y se postea desde el propio
dominio de BitacoraKasu (el capturista solo abre el link en su navegador), así que el CSRF
token normal de Django aplica sin problema.

### C3. URL (`urls.py`)

```python
path('completar/<str:token>/', views.completar_datos_terminal, name='completar_datos_terminal'),
```

Fuera del prefijo de vistas con login (va antes o después de las demás rutas del módulo,
sin `LoginRequiredMixin` ni middleware de sesión especial — el proyecto ya no exige login
global vía middleware, solo por vista/mixin).

### C4. Templates (nuevos)

- **`modulacion/completar_datos_terminal.html`**: standalone, **no** extiende `base.html`
  (ese template asume sesión iniciada + sidebar interno). Página mínima con logo, folio,
  contenedor, terminal y cliente en modo lectura arriba, el form abajo, botón "Guardar".
- **`modulacion/completar_datos_mensaje.html`**: mismo estilo standalone, un solo mensaje
  según `tipo`:
  - `invalido`: "Este link no es válido."
  - `cerrado`: "Esta modulación ya no admite cambios (folio {{ modulacion.folio }})."
  - `gracias`: "Datos guardados correctamente. Gracias."

---

## Parte D — Pruebas (`modulos/modulacion/tests.py`)

- `recibir_modulacion`: `completar_datos_url` presente cuando la terminal tiene
  `requiere_datos_extra=True` (creación **y** rama `duplicado`); ausente cuando es `False`.
- `DatosTerminalForm`: con terminal `requiere_carril=False` no expone `carril` (idem
  `hora_ingreso`/`hora_carga`); con las 4 banderas en `True` expone los 5 campos.
- `completar_datos_terminal` (vista):
  - Token inválido/manipulado → 404 con mensaje `invalido`.
  - Token válido pero terminal sin `requiere_datos_extra` → 404 `invalido`.
  - Token válido, `estado != 'PENDIENTE'` → mensaje `cerrado`, no muestra form.
  - Token válido, `estado == 'PENDIENTE'` → GET muestra form con el subconjunto correcto de
    campos; POST válido guarda y muestra `gracias`.

---

## Fuera de alcance (se documenta aquí, se implementa en `Proyecto_HAL9MIL`)

Cómo HAL9MIL recolecta `completar_datos_url` de cada contenedor y lo agrega al correo que
ya envía al capturista (reordenar push→email en `referencias/modulacion.py`, persistir los
links en `EnvioModulacion` para que un reintento de solo-email los siga teniendo
disponibles). Ver el mismo documento de diseño commiteado en `Proyecto_HAL9MIL`.
