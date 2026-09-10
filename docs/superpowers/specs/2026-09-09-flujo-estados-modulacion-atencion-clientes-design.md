# Flujo de estados de Modulación + vista "Atención a Clientes" — Diseño

**Fecha:** 2026-09-09
**Módulo:** `modulos/modulacion/`

## Objetivo

Dos cambios en `modulos/modulacion/`:

1. **LCTPC deja de asignar FULL.** Al leer las citas de la programación LCTPC,
   aunque varios contenedores compartan la hora de inicio de la ventana de
   registro, todos quedan como `SENCILLO`.
2. **Nuevo flujo de estados de `Modulacion`** para dar seguimiento aduanal, con
   historial de transiciones y una vista nueva **"Atención a Clientes"** (tablero
   por estado con botones de avance).

Aplica a **todas** las modulaciones sin importar `origen` (HAL9MIL, MANUAL,
LCTPC). El acceso a la vista y a las transiciones es **solo login** (sin permiso
nuevo), consistente con el resto de `modulacion`.

---

## Parte A — LCTPC: quitar la clasificación FULL/SENCILLO

### Estado actual

- `services_lctpc.clasificar(renglones)` agrupa por `registro_inicio`, empareja de
  2 en 2 → `tipo_cita='FULL'` con `grupo_cita` compartido; el sobrante impar y los
  grupos de 1 → `SENCILLO`.
- `services_importacion._procesar_correo` llama a `clasificar(prog.renglones)`
  antes de procesar los renglones.
- `_procesar_renglon` copia `r.tipo_cita` / `r.grupo_cita` a la `Modulacion`.

### Cambios

- **Eliminar** la función `clasificar()` de `services_lctpc.py` y su clase de
  tests `ClasificarTests` en `tests_lctpc.py`. Nada más la usa
  (`services_full.py`, la fusión manual de sencillos en `bitacoras`, es un
  sistema aparte y **no se toca**).
- En `services_importacion._procesar_correo`: quitar la llamada a `clasificar()`.
- En `services_importacion._procesar_renglon`: fijar **siempre**
  `tipo_cita='SENCILLO'` y `grupo_cita=''` en la `Modulacion` (tanto en el camino
  de actualización como en el de creación de stub), en lugar de copiar
  `r.tipo_cita` / `r.grupo_cita`.
- El `dataclass RenglonLCTPC` conserva sus campos `tipo_cita` / `grupo_cita` (su
  default `''` ya no se sobrescribe); el `detalle` JSON de auditoría sigue
  llevando la clave `tipo_cita` (ahora siempre `'SENCILLO'`).
- Los campos `Modulacion.tipo_cita` / `grupo_cita`, su columna en el admin y la
  columna "Tipo de cita" del detalle LCTPC **se quedan**; simplemente LCTPC ya no
  produce `FULL`.

### Tests (Parte A)

- Con el fixture `3ZYM_202609051401.xls` (que hoy da 6 FULL / 4 SENCILLO): tras
  el import, **todas** las `Modulacion` creadas/actualizadas tienen
  `tipo_cita='SENCILLO'` y `grupo_cita=''`.
- El `detalle` de la fila `ImportacionProgramacionLCTPC` tiene
  `tipo_cita='SENCILLO'` en todos los renglones.

---

## Parte B — Flujo de estados + Atención a Clientes

### B1. `Modulacion.ESTADO_CHOICES`

Nuevo conjunto y orden:

| clave | label | notas |
|---|---|---|
| `PENDIENTE` | Pendiente de modulación | inicial (default) |
| `MODULADO` | Modulado | **legacy**: se conserva el choice para filas históricas; ningún flujo nuevo lo asigna |
| `ASIGNADO` | Asignado / pendiente de ingreso | nuevo |
| `INGRESADO` | Ingresado | nuevo |
| `DESADUANAMIENTO_LIBRE` | Desaduanamiento libre (verde) | nuevo |
| `RECONOCIMIENTO_ADUANAL` | Reconocimiento aduanal (rojo) | nuevo |
| `RETENIDO` | Retenido (esperando aduana) | nuevo |
| `VERIFICACION_EN_TRANSPORTE` | Verificación en transporte | nuevo |
| `EN_PATIO_ESPERANZA` | En Patio Esperanza | existe |
| `ENVIADO_BITACORA` | Enviado a Bitácora de Viajes | existe (terminal) |
| `RETIRADO_TERCERO` | Retirado por transporte externo | existe (terminal) |

- `Modulacion.estado`: `max_length` de `20` → `30`
  (`VERIFICACION_EN_TRANSPORTE` = 26).

### B2. Mapa de transiciones + helper `transicionar()`

En `modulos/modulacion/models.py` (constante a nivel de módulo):

```python
TRANSICIONES_MODULACION = {
    'PENDIENTE': ['ASIGNADO'],                                   # normalmente automática
    'MODULADO': ['ASIGNADO'],                                    # legacy
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

ESTADOS_EN_SEGUIMIENTO = [
    'ASIGNADO', 'INGRESADO', 'DESADUANAMIENTO_LIBRE', 'RECONOCIMIENTO_ADUANAL',
    'RETENIDO', 'VERIFICACION_EN_TRANSPORTE', 'EN_PATIO_ESPERANZA',
]


class TransicionInvalida(Exception):
    """Se intentó un cambio de estado que el mapa no permite."""
```

Método en `Modulacion`:

```python
def transicionar(self, nuevo_estado, *, usuario=None, nota=''):
    permitidos = TRANSICIONES_MODULACION.get(self.estado, [])
    if nuevo_estado not in permitidos:
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

- La validación del mapa **no** aplica a ediciones directas en el admin (power
  user): ahí `estado` sigue siendo un campo editable normal.
- `transicionar()` es el único camino que escribe `SeguimientoModulacion`.

### B3. Auto `PENDIENTE → ASIGNADO`

Cuando una `Modulacion` en `PENDIENTE` queda con `unidad` **y** `operador`, pasa
sola a `ASIGNADO`.

- El único formulario que asigna ambos campos a la vez es
  `AsignarUnidadOperadorForm` vía `AsignarUnidadOperadorView`
  (`ModulacionForm` **no** incluye `unidad`/`operador`).
- En `AsignarUnidadOperadorView.form_valid`, tras guardar unidad+operador y
  sellar `fecha_asignacion`:
  ```python
  if modulacion.estado == 'PENDIENTE' and modulacion.unidad_id and modulacion.operador_id:
      modulacion.transicionar('ASIGNADO', usuario=self.request.user)
  ```
- Solo desde `PENDIENTE`. Una modulación ya avanzada (INGRESADO, etc.) que se
  reasigna **no** cambia de estado.
- Si en el futuro otro camino asigna unidad+operador juntos (API, carga masiva),
  debe replicar esta llamada. Hoy no aplica.
- No hay auto-retroceso si luego se quita unidad u operador.

### B4. Modelo `SeguimientoModulacion` (historial)

```python
class SeguimientoModulacion(models.Model):
    modulacion = models.ForeignKey(
        Modulacion, on_delete=models.CASCADE, related_name='seguimientos',
        verbose_name='Modulación',
    )
    estado = models.CharField(max_length=30, choices=Modulacion.ESTADO_CHOICES,
                              verbose_name='Estado')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Usuario',
    )
    nota = models.TextField(blank=True, verbose_name='Nota')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Seguimiento de modulación'
        verbose_name_plural = 'Seguimientos de modulación'
        ordering = ['creado_en']

    def __str__(self):
        return f'{self.modulacion.folio} → {self.get_estado_display()}'
```

- Una fila por transición hecha con `transicionar()`.
- Sin backfill: el historial arranca vacío para las modulaciones existentes.
- Se muestra como línea de tiempo en `ModulacionDetailView` y alimenta la fecha
  de "última actualización" en el tablero de Atención a Clientes.

### B5. Rutas existentes que cambian de estado → pasan por `transicionar()`

| Vista / función | Hoy | Cambio |
|---|---|---|
| `ModulacionCreateView.form_valid` | `estado = 'MODULADO'` | quitar la línea: la modulación manual nace `PENDIENTE` |
| `ModulacionUpdateView.form_valid` | `if estado == 'PENDIENTE': estado = 'MODULADO'` | quitar ese bloque |
| `enviar_a_patio_esperanza` | fija `EN_PATIO_ESPERANZA` desde cualquier estado | `modulacion.transicionar('EN_PATIO_ESPERANZA', usuario=request.user)`; si el estado actual no lo permite → `messages.error` y redirect. Queda limitado a `DESADUANAMIENTO_LIBRE` / `RECONOCIMIENTO_ADUANAL` / `RETENIDO` / `VERIFICACION_EN_TRANSPORTE` |
| `retirar_de_patio` (rama externa) | fija `RETIRADO_TERCERO` + `transportista_externo` | setea `transportista_externo`, luego `transicionar('RETIRADO_TERCERO', usuario=request.user)` |
| `EnviarABitacoraView` | fija `ENVIADO_BITACORA` (2 puntos) | `transicionar('ENVIADO_BITACORA', usuario=request.user)` tras crear el `BitacoraViaje`; conserva su guard actual `estado == 'EN_PATIO_ESPERANZA'` (coincide con el mapa) |

- `completar_datos_terminal` **no** cambia de estado (solo carril/horarios); su
  guard de "acceso cerrado" pasa de dispararse en `!= 'PENDIENTE'` a hacerlo
  cuando la modulación deja `PENDIENTE` (es decir, al llegar a `ASIGNADO`).
  No requiere cambio de código; sí una nota: el link público queda abierto hasta
  que se asigna unidad+operador.

### B6. Vista "Atención a Clientes"

- **URL:** `path('atencion-clientes/', views.AtencionClientesView.as_view(), name='atencion_clientes')`
  y `path('atencion-clientes/<int:pk>/avanzar/', views.avanzar_estado_modulacion, name='avanzar_estado')`.
- `AtencionClientesView(LoginRequiredMixin, TemplateView)`:
  - Query base: `Modulacion.objects.filter(estado__in=ESTADOS_EN_SEGUIMIENTO)`
    con `select_related('cliente', 'unidad', 'operador', 'agencia', 'terminal_portuaria')`.
  - `prefetch_related` del último `SeguimientoModulacion` (o anotación con
    `Max('seguimientos__creado_en')`).
  - **Filtros** (GET, opcionales): `estado`, `cliente`, `fecha_desde` / `fecha_hasta`
    (sobre `fecha_recepcion`).
  - El contexto agrupa las modulaciones por `estado` en el orden de
    `ESTADOS_EN_SEGUIMIENTO`; para cada una expone las transiciones válidas
    (`TRANSICIONES_MODULACION[estado]`) con su label.
- **Template** `templates/modulacion/atencion_clientes.html` (extiende `base.html`):
  - Encabezado con filtros.
  - Una sección por estado (con su badge de color); dentro, tarjetas con:
    folio, contenedor, cliente, unidad/operador, fecha del último seguimiento,
    y un `<form method="post">` por cada transición válida con un botón y un
    `<input name="nota">` opcional compartido.
  - Sin JS pesado; navegación y avance por POST normal.
- `avanzar_estado_modulacion(request, pk)` — `@login_required @require_POST`:
  - Lee `nuevo_estado` y `nota` del POST.
  - `try: modulacion.transicionar(nuevo_estado, usuario=request.user, nota=nota)`
    - éxito → `messages.success`
    - `TransicionInvalida` → `messages.error`
  - Redirige a `modulacion:atencion_clientes` **conservando los filtros**
    (se reenvían como querystring desde un `<input type="hidden">` o
    `request.POST.get('next')`).
- **Navegación:** enlace "Atención a Clientes" en `.dash-page-actions` de
  `templates/modulacion/dashboard.html` (junto a "Ver lista" / "Programaciones
  LCTPC").

### B7. Badges de estado centralizados

- Nueva `Modulacion.badge_class` (property) que devuelve la clase Tailwind del
  chip según `estado`:

  | estado | color |
  |---|---|
  | `PENDIENTE` | gris |
  | `MODULADO` | gris |
  | `ASIGNADO` | índigo |
  | `INGRESADO` | azul |
  | `DESADUANAMIENTO_LIBRE` | verde |
  | `RECONOCIMIENTO_ADUANAL` | rojo |
  | `RETENIDO` | ámbar |
  | `VERIFICACION_EN_TRANSPORTE` | morado |
  | `EN_PATIO_ESPERANZA` | verde |
  | `ENVIADO_BITACORA` | azul |
  | `RETIRADO_TERCERO` | gris |

- Se usa en `templates/modulacion/modulacion_list.html` (reemplaza la cadena
  `{% if m.get_estado_display == "..." %}`), en el tablero de Atención a Clientes
  y donde haga falta. La lista LCTPC (`importacion_lctpc_list.html`) queda fuera
  de alcance salvo que su chip comparta el helper trivialmente.

### B8. Admin

- `SeguimientoModulacionInline(admin.TabularInline)` read-only
  (`has_add_permission`/`has_change_permission`/`has_delete_permission` → `False`,
  `readonly_fields` = todos) dentro de `ModulacionAdmin`.
- Registrar `SeguimientoModulacion` como `ModelAdmin` independiente read-only:
  `list_display = ['creado_en', 'modulacion', 'estado', 'usuario']`,
  `list_filter = ['estado']`, `search_fields = ['modulacion__folio', 'modulacion__contenedor']`.
- `ModulacionAdmin.list_filter` ya tiene `estado`; no cambia.

### B9. Migración

Una sola migración en `modulacion`:

- `AlterField` de `Modulacion.estado` (`max_length` 30, nuevos `choices`).
- `CreateModel` `SeguimientoModulacion`.

Sin `RunPython`. Las filas con `estado='MODULADO'` quedan intactas y siguen
mostrándose bien (el choice se conserva).

---

## Estructura de archivos

| Archivo | Acción | Qué |
|---|---|---|
| `modulos/modulacion/services_lctpc.py` | Modificar | quitar `clasificar()` |
| `modulos/modulacion/services_importacion.py` | Modificar | no llamar `clasificar()`; forzar `SENCILLO`/`''` en `_procesar_renglon` |
| `modulos/modulacion/models.py` | Modificar | `ESTADO_CHOICES`, `estado.max_length`, `TRANSICIONES_MODULACION`, `ESTADOS_EN_SEGUIMIENTO`, `TransicionInvalida`, `Modulacion.transicionar()`, `Modulacion.badge_class`, modelo `SeguimientoModulacion` |
| `modulos/modulacion/migrations/0008_*.py` | Crear (auto) | AlterField estado + CreateModel SeguimientoModulacion |
| `modulos/modulacion/views.py` | Modificar | quitar `MODULADO` de Create/Update; `enviar_a_patio_esperanza` / `retirar_de_patio` / `EnviarABitacoraView` → `transicionar()`; auto-ASIGNADO en `AsignarUnidadOperadorView`; `AtencionClientesView`; `avanzar_estado_modulacion` |
| `modulos/modulacion/urls.py` | Modificar | 2 rutas nuevas (`atencion_clientes`, `avanzar_estado`) |
| `modulos/modulacion/admin.py` | Modificar | inline read-only + registro de `SeguimientoModulacion` |
| `templates/modulacion/atencion_clientes.html` | Crear | tablero por estado con botones de avance |
| `templates/modulacion/dashboard.html` | Modificar | enlace "Atención a Clientes" |
| `templates/modulacion/modulacion_list.html` | Modificar | usar `badge_class` |
| `templates/modulacion/modulacion_detail.html` | Modificar | línea de tiempo de `seguimientos` |
| `modulos/modulacion/tests.py` o `tests_estados.py` | Crear/Modificar | ver Testing. **No** tocar `tests_lctpc.py` salvo Parte A (quitar `ClasificarTests`, ajustar aserciones de tipo_cita) |

Los tests nuevos de la Parte B van en un archivo nuevo
`modulos/modulacion/tests_estados.py` (patrón de `tests_lctpc.py`; `tests.py`
existe y no permite crear paquete `tests/`).

---

## Testing

### Parte A
- Import LCTPC con fixture de 10 renglones y horarios repetidos → cada
  `Modulacion` resultante: `tipo_cita='SENCILLO'`, `grupo_cita=''`.
- `detalle` de la fila de auditoría: `tipo_cita='SENCILLO'` en todos.
- `clasificar` y `ClasificarTests` ya no existen (no import errors).

### Parte B — `transicionar()`
- Transición válida (`ASIGNADO → INGRESADO`): cambia `estado`, crea 1
  `SeguimientoModulacion` con `usuario` y `nota`.
- Transición inválida (`ASIGNADO → EN_PATIO_ESPERANZA`): `TransicionInvalida`,
  `estado` sin cambio, 0 filas de seguimiento.
- `EN_PATIO_ESPERANZA` sella `fecha_patio_esperanza` solo la primera vez;
  `RETIRADO_TERCERO` sella `fecha_retiro`.

### Parte B — auto ASIGNADO
- `AsignarUnidadOperadorView` con unidad+operador sobre una `PENDIENTE` →
  `estado='ASIGNADO'`, `fecha_asignacion` sellada, 1 fila de seguimiento con el
  usuario de la request.
- La misma vista sobre una `INGRESADO` (reasignación) → `estado` sigue
  `INGRESADO`, sin fila de seguimiento nueva.
- Asignar solo unidad (sin operador) → sigue `PENDIENTE`.

### Parte B — Atención a Clientes
- La vista lista **solo** modulaciones con estado en `ESTADOS_EN_SEGUIMIENTO`
  (no `PENDIENTE`, no `ENVIADO_BITACORA`).
- Cada tarjeta ofrece exactamente los botones de
  `TRANSICIONES_MODULACION[estado]` (p.ej. `INGRESADO` → 2 botones).
- `avanzar_estado` con `nuevo_estado` válido → mueve + historial + redirect con
  `messages.success`, filtros conservados en la URL.
- `avanzar_estado` con `nuevo_estado` inválido → sin cambios, `messages.error`.
- Sin login → 302 al login.
- Filtro por `estado` y por `cliente` acota el listado.

### Parte B — rutas existentes
- `enviar_a_patio_esperanza` desde `DESADUANAMIENTO_LIBRE` → `EN_PATIO_ESPERANZA`
  + fila de seguimiento; desde `ASIGNADO` → `messages.error`, sin cambio.
- `EnviarABitacoraView` desde `EN_PATIO_ESPERANZA` → `ENVIADO_BITACORA` + fila de
  seguimiento (además de crear el `BitacoraViaje` como hoy).
- `retirar_de_patio` rama externa desde `EN_PATIO_ESPERANZA` → `RETIRADO_TERCERO`
  + `transportista_externo` + fila de seguimiento.

### Parte B — badges
- `badge_class` devuelve la clase esperada para cada estado (incluye los nuevos).

### Regresión
- Suite completa `modulos.modulacion` en verde (incluye `tests.py` y
  `tests_lctpc.py` ya existentes).

---

## Fuera de alcance

- Permiso dedicado para Atención a Clientes (queda solo-login).
- Kanban con drag-and-drop (se usa tablero con botones).
- Retroceso automático de estado al quitar unidad/operador.
- Backfill de historial para modulaciones previas.
- Tocar `services_full.py` / la fusión de sencillos en `bitacoras`.
- Cambios en el chip de estado de `importacion_lctpc_list.html` (salvo que
  reutilice `badge_class` sin fricción).
- Notificaciones (correo / WhatsApp) al cambiar de estado.
