# Generar Full a partir de dos viajes Sencillo

**Fecha:** 2026-09-01
**Módulos afectados:** `modulos/bitacoras`, `modulos/modulacion`

## 1. Problema

En Bitácoras de Viaje, cuando se registran dos viajes **SENCILLO** con la
**misma unidad** y el **mismo operador**, físicamente se trata de un único
viaje **FULL** (dos contenedores en la misma unidad). Hoy el sistema permite
guardar los dos sencillos por separado, lo que deja la operación mal
representada y duplica registros.

Se requiere que, al guardar el segundo viaje sencillo con esa combinación,
el sistema **advierta con un modal** (como la referencia visual aportada) y
ofrezca **generar un Full**, comparando antes el **cliente** y el **código
postal de destino** para decidir el tipo de Full. Debe aplicar al **alta
manual**, a la **edición** y al **traslado desde Modulación**. La **carga
masiva** queda fuera: ya arma los Full directamente.

## 2. Reglas de negocio

### 2.1 "En curso"

Un viaje está en curso cuando `completado == False`.

### 2.2 Capacidad de la unidad

Cada unidad carga como máximo **2 contenedores en curso**:

| Modalidad | Contenedores |
|---|---|
| `SENCILLO`, `LOCAL` | 1 |
| `FULL`, `LOCAL_FULL` | 2 |

- Unidad con **0 o 1** contenedor en curso → seleccionable en el formulario.
- Unidad con **2** (un FULL, o —solo por datos heredados— dos sencillos) →
  **no aparece** en el selector de unidad y se **rechaza** si se fuerza por
  POST, con mensaje: *"La unidad {X} ya tiene 2 contenedores en curso."*

### 2.3 Segundo sencillo sobre una unidad que ya tiene un sencillo en curso

Al guardar o editar un viaje `SENCILLO` cuya unidad ya tiene **un** `SENCILLO`
en curso:

| Caso | Resultado |
|---|---|
| **Mismo operador** que el sencillo existente | Modal **"Generar Full" / "Cancelar"**. No existe la opción de guardar como sencillo separado. |
| **Operador distinto** | Se rechaza con: *"La unidad {X} ya tiene un viaje sencillo en curso con el operador {A}. Una unidad no puede llevar dos sencillos por separado; para un segundo contenedor genere un Full con el mismo operador."* |

Una unidad **no puede** quedar con dos sencillos separados a través de estos
flujos. Si el usuario no acepta generar el Full, el guardado no se realiza.

### 2.4 Emparejamiento

El "sencillo apareable" es: `modalidad='SENCILLO'` + `completado=False` +
misma `unidad` + mismo `operador`. Por la regla de capacidad (2.2) solo puede
existir **un** candidato; si hubiera más (datos heredados), se toma el más
reciente por `fecha_carga`.

### 2.5 Tipo de Full resultante (automático)

Comparando el segundo contenedor contra el sencillo existente:

- `cliente` **y** `cp_destino` **iguales** → Full **directo**: `reparto=False`,
  `cliente_2` y `cp_destino_2` quedan vacíos.
- `cliente` **o** `cp_destino` **distintos** → Full **con reparto**:
  `reparto=True`, `cliente_2` ← cliente del 2º, `cp_destino_2` ← CP del 2º.

Comparación de `cliente` nulo: dos nulos = iguales; uno nulo y otro con valor
= distintos.

## 3. Arquitectura

### 3.1 Módulo de lógica compartida — `modulos/bitacoras/services_full.py`

Funciones puras salvo `fusionar_en_full` (escribe).

```python
def contenedores_en_curso(unidad, *, excluir_pk=None) -> int
    """Suma 2 por FULL/LOCAL_FULL y 1 por SENCILLO/LOCAL con completado=False."""

def unidad_bloqueada(unidad, *, excluir_pk=None) -> bool
    """True si contenedores_en_curso(...) >= 2."""

def sencillo_apareable(unidad, operador, *, excluir_pk=None) -> BitacoraViaje | None
    """SENCILLO + completado=False + misma unidad + mismo operador.
    El más reciente por fecha_carga; None si no hay."""

def evaluar_fusion(unidad, operador, cliente, cp_destino, *, excluir_pk=None) -> dict
    """`cliente` es una instancia de Cliente o None; `cp_destino` es str.
    El endpoint resuelve los ids de query param a instancias antes de llamar;
    las vistas pasan `form.cleaned_data` directamente.
    Orquesta la decisión. Devuelve exactamente uno de:
       {'accion': 'ninguna'}
       {'accion': 'bloqueo', 'mensaje': str}
       {'accion': 'ofrecer_full', 'sencillo': BitacoraViaje,
        'tipo_full': 'directo' | 'reparto'}
    Lógica:
      - excluir_pk sirve para editar (no compararse a sí mismo ni contarse).
      - Si unidad_bloqueada(...) y no hay sencillo apareable -> bloqueo (2/2).
      - Si hay >=1 SENCILLO en curso en la unidad con OTRO operador -> bloqueo
        (operador distinto).
      - Si hay sencillo apareable (mismo operador) -> ofrecer_full, calculando
        tipo_full con la regla 2.5.
      - En cualquier otro caso -> ninguna."""

def fusionar_en_full(sencillo_existente, datos_segundo, *, tipo_full) -> BitacoraViaje
    """Muta y guarda sencillo_existente como FULL. datos_segundo es dict:
       {contenedor, peso, sellos, cliente, cp_destino}.
       - modalidad='FULL'
       - contenedor_2, peso_2, sellos_2  <- datos_segundo
       - tipo_full=='reparto': reparto=True, cliente_2, cp_destino_2 <- datos_segundo
       - tipo_full=='directo': reparto=False, cliente_2='', cp_destino_2=''
       - full_clean() + save()
       - si quedó reparto con cp_destino_2 y hay GOOGLE_MAPS_API_KEY:
         recalcula la 2ª distancia (calcular_distancia_google()).
       Devuelve el registro FULL. El borrado del 2º registro / ligado de la
       Modulación lo hace el caller."""
```

### 3.2 Endpoint de verificación — `verificar_full`

`GET /bitacoras/verificar-full/` (LoginRequired). Query params:
`unidad` (id, requerido), `operador` (id, requerido), `cliente` (id, opcional),
`cp_destino` (str, opcional), `excluir_pk` (id, opcional — edición).

Respuesta JSON según `evaluar_fusion`:

```jsonc
// accion = ninguna
{ "accion": "ninguna" }

// accion = bloqueo
{ "accion": "bloqueo", "mensaje": "La unidad ECO 001 ya tiene un viaje sencillo en curso con el operador SERGIO. ..." }

// accion = ofrecer_full
{
  "accion": "ofrecer_full",
  "tipo_full": "reparto",
  "sencillo": {
    "id": 24,
    "contenedor": "BEAU4257674",
    "cliente": "IMPORTADORA GLOBAL JUPITER, SA DE CV",
    "cp_destino": "62520"
  },
  "nuevo": {
    "cliente": "LUZ KELIBIZ INTERNATIONAL SA DE CV",
    "cp_destino": "40810"
  }
}
```

Si faltan `unidad`/`operador` → `{ "accion": "ninguna" }` (el JS no bloquea el
alta por datos incompletos; la validación real del form sigue su curso).

### 3.3 Formularios

**`BitacoraViajeForm`** (`modulos/bitacoras/forms.py`):

- `__init__`: el queryset de `unidad` excluye `unidad_bloqueada()`, preservando
  la unidad actual al editar (`excluir_pk=self.instance.pk` si `self.instance.pk`).
- Campo extra no-modelo `confirmar_full = forms.BooleanField(required=False,
  widget=forms.HiddenInput)`.
- `clean()`: si `modalidad == 'SENCILLO'`, llama `evaluar_fusion(unidad,
  operador, cliente, cp_destino, excluir_pk=self.instance.pk or None)`:
  - `accion == 'bloqueo'` → `add_error('unidad', mensaje)`.
  - `accion == 'ofrecer_full'` y `confirmar_full` no marcado → `add_error(None,
    'Esta unidad ya tiene un viaje sencillo en curso. Genere un Full para
    agregar el segundo contenedor.')` (red de seguridad; en uso normal el
    modal lo intercepta antes del submit).

**`PromoverBitacoraForm`** (`modulos/modulacion/forms.py`):

- Queryset de `unidad` filtra `unidad_bloqueada()`.
- Campo extra `confirmar_full` (HiddenInput, no requerido).
- La verificación se hace en la vista (`EnviarABitacoraView.post`), no en el
  `clean()` del form, porque los datos del 2º contenedor vienen de la
  Modulación y el ligado es responsabilidad de la vista.

### 3.4 Vistas

**`BitacoraCreateView.form_valid`** — antes del `save()` actual:

1. Si `modalidad != 'SENCILLO'` → flujo actual intacto.
2. `res = evaluar_fusion(unidad, operador, cliente, cp_destino)`.
3. `res['accion'] == 'bloqueo'` → `form.add_error(...)`, `return self.form_invalid(form)`.
4. `res['accion'] == 'ofrecer_full'` y `not confirmar_full` → `form.add_error(...)`,
   `form_invalid`.
5. `res['accion'] == 'ofrecer_full'` y `confirmar_full` → dentro de
   `transaction.atomic()`:
   - `datos_segundo` desde `form.cleaned_data`
     (`contenedor`, `peso`, `sellos`, `cliente`, `cp_destino`).
   - `full = fusionar_en_full(res['sencillo'], datos_segundo, tipo_full=res['tipo_full'])`.
   - `messages.success('Full generado: el viaje #{full.pk} ahora lleva 2
     contenedores.')`.
   - `redirect('bitacoras:detail', pk=full.pk)`. **No** se crea `BitacoraViaje` nuevo.
6. `res['accion'] == 'ninguna'` → flujo actual intacto.

**`BitacoraUpdateView.form_valid`** — misma lógica, con `excluir_pk=self.object.pk`
en todas las llamadas. Al confirmar la fusión: se fusiona en el **otro**
sencillo (`res['sencillo']`) y **se elimina** `self.object` (el que se estaba
editando); `redirect` al FULL.

**`EnviarABitacoraView.post`** — tras validar el form y antes de crear la
bitácora:

1. `res = evaluar_fusion(unidad, operador, cliente=modulacion.cliente,
   cp_destino=form.cleaned_data['cp_destino'])`.
2. `bloqueo` → `messages.warning(res['mensaje'])`, re-render del form.
3. `ofrecer_full` sin `confirmar_full` → re-render con aviso (el modal debió
   interceptar).
4. `ofrecer_full` con `confirmar_full` → `transaction.atomic()`:
   - `datos_segundo = {contenedor: modulacion.contenedor,
     peso: modulacion.peso_toneladas, sellos: '',
     cliente: modulacion.cliente, cp_destino: form.cleaned_data['cp_destino']}`.
   - `full = fusionar_en_full(res['sencillo'], datos_segundo, tipo_full=res['tipo_full'])`.
   - `modulacion.bitacora_viaje = full`; `modulacion.estado = 'ENVIADO_BITACORA'`;
     `modulacion.fecha_retiro = timezone.now()`; `modulacion.save()`.
   - `messages.success('Modulación {folio} unida al Full #{full.pk}.')`.
   - `redirect('bitacoras:detail', pk=full.pk)`. **No** se crea `BitacoraViaje` nuevo.
5. `ninguna` → flujo actual intacto (crea el sencillo).

### 3.5 Frontend (modal)

JS en el bloque `extra_js` de `templates/bitacoras/bitacora_form.html` y
`templates/modulacion/enviar_a_bitacora.html`. Marcado del modal reutilizable
(oculto por defecto).

Al `submit` del formulario:

1. En `bitacora_form.html`: si `#id_modalidad` ≠ `SENCILLO` → submit normal.
   En `enviar_a_bitacora.html`: siempre se verifica (modalidad siempre SENCILLO).
2. `preventDefault`; `fetch` GET al endpoint con `unidad`, `operador`,
   `cliente`, `cp_destino` (+ `excluir_pk` al editar).
3. `accion == 'ninguna'` → `form.submit()`.
4. `accion == 'bloqueo'` → modal de alerta simple (título "No se puede
   registrar", texto = `mensaje`, botón "Entendido"); no envía.
5. `accion == 'ofrecer_full'` → modal tipo advertencia:
   - Título: "Se generará un Full".
   - Tabla comparativa: fila Contenedor 1 (`sencillo.contenedor`,
     `sencillo.cliente`, `sencillo.cp_destino`) y fila Contenedor 2
     (contenedor en captura, `nuevo.cliente`, `nuevo.cp_destino`).
   - Leyenda: "Se generará un **Full directo**" o "Se generará un **Full con
     reparto** (dos destinos)".
   - Botón **"Generar Full"** → inserta `<input type="hidden"
     name="confirmar_full" value="1">` en el form y `form.submit()`.
   - Botón **"Cancelar"** → cierra el modal, no envía.
6. Si el `fetch` falla (red/500) → se permite el submit normal; la validación
   servidor es la red de seguridad.

### 3.6 URLs

`modulos/bitacoras/urls.py`: `path('verificar-full/', views.verificar_full,
name='verificar_full')`.

## 4. Detalles de la fusión

Sobre el sencillo existente (= contenedor 1, se conservan **todos** sus datos):

| Campo | Valor |
|---|---|
| `modalidad` | `'FULL'` |
| `contenedor_2`, `peso_2`, `sellos_2` | del segundo contenedor |
| `reparto` | `True` si `tipo_full=='reparto'`, si no `False` |
| `cliente_2`, `cp_destino_2` | del 2º si reparto; vacíos si directo |
| `tipo_contenedor`, fechas, `salida_a_ruta`, `destino`, `domicilio_carta_porte`, kilometraje, diésel | **sin cambios** (los del contenedor 1) |

- `full_clean()` antes de `save()`. Si falla → abortar `transaction.atomic()`,
  `messages.error`, no se borra nada.
- Si quedó `reparto=True` con `cp_destino_2` y hay `GOOGLE_MAPS_API_KEY` →
  `calcular_distancia_google()` para la 2ª distancia.
- **Orden atómico:** guardar el FULL → borrar el 2º registro (alta manual y
  edición; en Modulación no hay 2º registro) → ligar Modulación si aplica.

## 5. Casos borde

- **Unidad en 2/2 sin sencillo apareable** (datos heredados) →
  `accion='bloqueo'`, "La unidad {X} ya tiene 2 contenedores en curso."
- **Modalidad FULL en el alta manual** → la verificación no corre; el filtrado
  del selector ya impide elegir una unidad ocupada.
- **Editar un FULL existente** → sin cambios; `evaluar_fusion` solo actúa sobre
  `SENCILLO`.
- **Carga masiva** → intacta (no pasa por estas vistas).
- **El sencillo apareable se completa o se borra entre el `fetch` y el
  `submit`** → la revalidación servidor devuelve `ninguna` → se guarda como
  sencillo normal. Aceptable.
- **`cliente` nulo** → dos nulos = iguales; uno nulo y otro con valor =
  distintos → reparto.
- **`fetch` del endpoint falla** → submit normal; el servidor revalida.

## 6. Pruebas

### `modulos/bitacoras/tests_full.py`

- **`services_full`**:
  - `contenedores_en_curso`: FULL=2, SENCILLO=1, ignora `completado=True`,
    respeta `excluir_pk`.
  - `unidad_bloqueada`: 0/1 → False, 2 → True.
  - `sencillo_apareable`: match por unidad+operador; None si operador distinto;
    None si el candidato está completado.
  - `evaluar_fusion`: los cuatro caminos (`ninguna`, `bloqueo` por 2/2,
    `bloqueo` por operador distinto, `ofrecer_full` directo, `ofrecer_full`
    reparto).
  - `fusionar_en_full`: directo (sin `cliente_2`/`cp_destino_2`, `reparto=False`)
    y reparto (con ambos, `reparto=True`), con Google Maps mockeado; verifica
    `contenedor_2`/`peso_2`/`sellos_2` y que `modalidad=='FULL'`.
- **Endpoint `verificar_full`**: JSON para `ninguna`, `ofrecer_full` directo,
  `ofrecer_full` reparto, `bloqueo`; 200 y `content-type` JSON.
- **`BitacoraCreateView`**:
  - Unidad libre → alta de sencillo normal (regresión).
  - Sin `confirmar_full` y con sencillo apareable → `form_invalid`, no fusiona.
  - Con `confirmar_full=1` → fusiona, el 2º registro no se crea, redirige al
    FULL, `modalidad=='FULL'`.
  - Operador distinto → error de form.
  - Unidad en 2/2 → error de form.
  - Alta de FULL manual con unidad libre → sigue funcionando (regresión).
- **`BitacoraUpdateView`**: editar un sencillo y cambiar operador para aparear
  con otro → con `confirmar_full=1` fusiona en el otro y elimina el editado.
- **Selector de unidad**: `BitacoraViajeForm` no incluye una unidad con FULL en
  curso; sí incluye la unidad propia al editar ese FULL.

### `modulos/modulacion/tests.py` (ampliación de `EnviarABitacoraViewTests`)

- Con sencillo apareable (misma unidad+operador, en curso) y `confirmar_full=1`
  → `modulacion.bitacora_viaje` es el FULL, `estado=='ENVIADO_BITACORA'`, **no**
  se crea un segundo `BitacoraViaje`, el FULL tiene `contenedor_2 ==
  modulacion.contenedor`.
- Tipo de Full: mismo cliente y CP → `reparto=False`; distinto → `reparto=True`
  con `cliente_2`/`cp_destino_2`.
- Unidad bloqueada (2/2) → `messages.warning`, no se crea bitácora.
- Sin sencillo apareable → se crea el sencillo como hoy (regresión).

## 7. Fuera de alcance

- Capacidad/bloqueo por **operador** (solo se bloquea por unidad; el operador
  se usa únicamente como criterio de emparejamiento).
- "Deshacer" un Full para volver a dos sencillos.
- Cambios en la carga masiva.
- Modalidades `LOCAL` / `LOCAL_FULL` (el flujo foráneo usa unidades `FORANEA`;
  la lógica es modalidad-agnóstica en el conteo de capacidad pero el modal de
  fusión solo se ofrece para `SENCILLO`).
