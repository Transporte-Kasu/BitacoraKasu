# Diseño: App Vacíos (retorno de contenedores vacíos a la naviera)

**Fecha:** 2026-08-28
**Estado:** Aprobado, pendiente de plan de implementación
**Módulo nuevo:** `modulos/vacios`

## Contexto del proceso

El servicio principal de Transportes Kasu:

1. Una agencia aduanal solicita la extracción de un contenedor o un *full* (dos
   de 40; uno de 40 y uno de 20; uno de 40 y dos de 20; cuatro de 20). Se extrae
   de una terminal (APM o HPH), pasa por la selección automatizada de la aduana
   (desaduanamiento libre o reconocimiento aduanal) y, concluida la modulación,
   se lleva al **Patio Esperanza**. Todo esto vive en la app **Modulación**
   (`modulos/modulacion`, ya implementada).
2. Estando en Patio Esperanza, el cliente puede solicitar contenedores
   disponibles; los lleva Transportes Kasu u otro transporte. El viaje al
   cliente vive en la app **Bitácora** (`modulos/bitacoras`, ya implementada).
3. **App Vacíos (este diseño).** Una vez que Kasu entrega el contenedor al
   cliente, se hace el vaciado del contenedor para su retorno a la naviera.
   Al registrarse la entrega del contenedor al cliente, el contenedor pasa
   automáticamente a Vacíos. Es un proceso logístico y puede sufrir retrasos
   (en la maniobra de entrega, o en el viaje de regreso). Los vacíos llegan al
   Patio Esperanza; una vez disponibles, la app asigna un operador libre (que no
   esté haciendo extracción de contenedores) para ir a entregar el vacío a la
   naviera. Esa asignación puede cambiar de operador. Se hace un conteo semanal
   de entregas de vacíos para revisión/análisis. Ante un retraso se notifica a
   la agencia aduanal para que reasigne la fecha de entrega (ese trámite lo
   lleva personal de la agencia aduanal, fuera del sistema).

## Decisiones tomadas

| Tema | Decisión |
|------|----------|
| Disparador de creación | `post_save` sobre `BitacoraViaje`: al quedar registrada la fecha de entrega real de un contenedor (`fecha_hora_entrega` / `fecha_hora_entrega_2`). |
| Alcance | **Todas** las bitácoras, sin importar modalidad ni si vienen de Modulación. |
| Full / Local Full | **Un Vacío por contenedor** (viaje FULL con 2 fechas de entrega → 2 Vacíos). |
| Estados | 4: `POR_VACIAR` → `EN_PATIO_ESPERANZA` → `ASIGNADO` → `ENTREGADO_NAVIERA`. Los retrasos son eventos, no estados. |
| Retrasos | Evento estructurado (`tipo`, `motivo`, `fecha_estimada_nueva`) + historial + **aviso automático** a la agencia. |
| Canal de aviso | Correo electrónico (backend SendGrid ya configurado). |
| Asignación de operador | La app **sugiere** operadores LOCAL libres; el usuario **confirma**. Flujo unidad → operador (auto-llenado del operador ligado a la unidad). |
| Cambio de operador | Historial estructurado con causa (`NO_CONFIRMA` / `SE_NIEGA` / `ULTIMA_HORA`) y conteo en el reporte semanal. Puede cambiar **unidad y/o operador**. |
| Tramo a la naviera | **No** genera `BitacoraViaje`. Se registra dentro del propio `Vacio`. |
| Fecha de entrega a naviera | Campo editable en el `Vacio` (`fecha_compromiso_naviera`); la agencia la reasigna por fuera tras el aviso de retraso. |
| Naviera | Catálogo nuevo `Naviera` + captura manual en cada Vacío (puede quedar vacía al inicio). |
| Reporte | Como los de Modulación: generador en `modulos/reportes/`, programable vía `ConfiguracionReporte`, con vista en pantalla. |

## Arquitectura

App Django estándar `modulos/vacios`, con la misma estructura que el resto de
`modulos/`: `models.py`, `views.py`, `urls.py`, `forms.py`, `admin.py`,
`signals.py`, `apps.py` (con `ready()` que importa los signals), `tests.py`,
`migrations/`, `notificaciones.py`, y `management/` si hiciera falta.

`CLAUDE.md` indica que solo `combustible`, `taller` y `almacen` usan signals;
este diseño añade `vacios` a esa lista (se debe actualizar `CLAUDE.md`).

### Alta en el proyecto

- `config/settings.py`: `'modulos.vacios'` en `INSTALLED_APPS`.
- `config/urls.py`: `path('vacios/', include('modulos.vacios.urls'))`.
- `templates/base.html`: enlace en el sidebar de navegación.
- `config/views.py` (`IndexView`): tarjeta con conteos de vacíos.

## Modelos

### `Naviera` (catálogo, en `modulos/vacios`)

| Campo | Tipo | Notas |
|-------|------|-------|
| `nombre` | `CharField(120)` | `unique=True` |
| `direccion_retorno` | `TextField(blank=True)` | Patio / domicilio donde se entrega el vacío |
| `activo` | `BooleanField(default=True)` | |
| `created_at` | `DateTimeField(auto_now_add=True)` | |

`Meta.ordering = ['nombre']`. `__str__` → `nombre`.

### `Vacio` (principal)

Un registro = un contenedor vaciado.

| Campo | Tipo | Notas |
|-------|------|-------|
| `folio` | `CharField(20, unique=True, editable=False)` | `VAC-YYYYMMDD-XXX`; generación con reintento anti-colisión copiada de `Modulacion.save()`, agrupada por `fecha_entrega_cliente`. |
| `bitacora_viaje` | `FK('bitacoras.BitacoraViaje', PROTECT, related_name='vacios')` | Origen. |
| `numero_contenedor` | `CharField(1, choices=[('1','1'),('2','2')], default='1')` | Cuál de los dos contenedores del viaje. |
| `contenedor` | `CharField(50)` | Copiado de la bitácora al crear. |
| `cliente` | `FK('bitacoras.Cliente', SET_NULL, null=True, blank=True, related_name='vacios')` | Copiado al crear. |
| `tipo_contenedor` | `CharField(2, choices=[('20','20 pies'),('40','40 pies')], default='40')` | Copiado al crear. |
| `agencia` | `FK('modulacion.Agencia', SET_NULL, null=True, blank=True, related_name='vacios')` | Auto-llenado si `bitacora_viaje.modulacion` existe; si no, captura manual. Destino del aviso de retraso. |
| `naviera` | `FK('vacios.Naviera', SET_NULL, null=True, blank=True, related_name='vacios')` | Captura manual posterior. |
| `estado` | `CharField(20, choices=ESTADO_CHOICES, default='POR_VACIAR')` | Ver máquina de estados. |
| `fecha_entrega_cliente` | `DateTimeField` | Copiada de `fecha_hora_entrega[_2]`. Arranque del ciclo. |
| `fecha_retorno_patio` | `DateTimeField(null=True, blank=True)` | Sellada al pasar a `EN_PATIO_ESPERANZA`. |
| `unidad` | `FK('unidades.Unidad', SET_NULL, null=True, blank=True, related_name='vacios')` | Asignada junto con el operador. |
| `operador` | `FK('operadores.Operador', SET_NULL, null=True, blank=True, related_name='vacios')` | |
| `fecha_asignacion` | `DateTimeField(null=True, blank=True)` | Sellada la **primera** vez que se asigna unidad+operador. |
| `fecha_compromiso_naviera` | `DateTimeField(null=True, blank=True)` | Fecha de entrega a naviera; editable; la agencia la reasigna por fuera. |
| `fecha_salida_naviera` | `DateTimeField(null=True, blank=True)` | Salida del Patio Esperanza rumbo a la naviera. |
| `fecha_entrega_naviera` | `DateTimeField(null=True, blank=True)` | Entrega efectiva. Fin del ciclo. |
| `tiene_retraso` | `BooleanField(default=False)` | Cache para listados; se activa al crear un `RetrasoVacio`. |
| `observaciones` | `TextField(blank=True)` | |
| `created_at` / `updated_at` | auto | |

**`ESTADO_CHOICES`:**

```python
ESTADO_CHOICES = [
    ('POR_VACIAR', 'Por vaciar (entregado al cliente)'),
    ('EN_PATIO_ESPERANZA', 'En Patio Esperanza (vacío disponible)'),
    ('ASIGNADO', 'Operador asignado'),
    ('ENTREGADO_NAVIERA', 'Entregado a la naviera'),
]
```

**`Meta`:**

- `verbose_name = "Vacío"`, `verbose_name_plural = "Vacíos"`.
- `ordering = ['-fecha_entrega_cliente']`.
- `constraints`: `UniqueConstraint(fields=['bitacora_viaje', 'numero_contenedor'], name='uniq_vacio_bitacora_contenedor')`.

**`save()`:** genera `folio` con el mismo patrón de reintento anti-colisión de
`Modulacion.save()` (bloqueo `select_for_update()` sobre el último folio del día,
5 reintentos, agrupado por la fecha de `fecha_entrega_cliente`).

### `RetrasoVacio` (evento)

| Campo | Tipo | Notas |
|-------|------|-------|
| `vacio` | `FK(Vacio, CASCADE, related_name='retrasos')` | |
| `tipo` | `CharField(10, choices=[('MANIOBRA','Cambio por maniobra'),('RETORNO','Retraso de retorno')])` | |
| `motivo` | `TextField` | |
| `fecha_estimada_nueva` | `DateField` | Nueva fecha estimada de entrega a naviera. |
| `notificado_agencia` | `BooleanField(default=False)` | |
| `fecha_notificacion` | `DateTimeField(null=True, blank=True)` | |
| `creado_por` | `FK(settings.AUTH_USER_MODEL, SET_NULL, null=True, blank=True)` | |
| `created_at` | `DateTimeField(auto_now_add=True)` | |

`Meta.ordering = ['-created_at']`.

### `CambioOperadorVacio` (historial de reasignación)

| Campo | Tipo | Notas |
|-------|------|-------|
| `vacio` | `FK(Vacio, CASCADE, related_name='cambios_operador')` | |
| `unidad_saliente` | `FK('unidades.Unidad', SET_NULL, null=True, blank=True, related_name='+')` | |
| `unidad_entrante` | `FK('unidades.Unidad', SET_NULL, null=True, blank=True, related_name='+')` | |
| `operador_saliente` | `FK('operadores.Operador', SET_NULL, null=True, blank=True, related_name='+')` | |
| `operador_entrante` | `FK('operadores.Operador', SET_NULL, null=True, blank=True, related_name='+')` | |
| `causa` | `CharField(15, choices=[('NO_CONFIRMA','Operador no confirma'),('SE_NIEGA','Operador se niega a la entrega'),('ULTIMA_HORA','Cambio de última hora')])` | |
| `motivo` | `TextField(blank=True)` | Opcional. |
| `creado_por` | `FK(settings.AUTH_USER_MODEL, SET_NULL, null=True, blank=True)` | |
| `created_at` | `DateTimeField(auto_now_add=True)` | |

`Meta.ordering = ['-created_at']`.

### Cambio en `modulacion.Agencia`

Añadir:

| Campo | Tipo | Notas |
|-------|------|-------|
| `email_contacto` | `EmailField(blank=True)` | Destino del aviso automático de retraso. No rompe la API `recibir_modulacion` (campo opcional). |

Migración en `modulos/modulacion/migrations/`.

## Flujo y creación automática

### Signal de creación (`modulos/vacios/signals.py`)

`post_save` sobre `bitacoras.BitacoraViaje`. Para cada contenedor del viaje con
fecha de entrega registrada y sin `Vacio` todavía:

- `fecha_hora_entrega` presente → `get_or_create` de `Vacio` con
  `numero_contenedor='1'`, `contenedor=bitacora.contenedor`,
  `cliente=bitacora.cliente`, `tipo_contenedor=bitacora.tipo_contenedor`,
  `fecha_entrega_cliente=bitacora.fecha_hora_entrega`, `estado='POR_VACIAR'`.
- `fecha_hora_entrega_2` presente → `Vacio` con `numero_contenedor='2'`,
  `contenedor=bitacora.contenedor_2`,
  `cliente=bitacora.cliente_2 or bitacora.cliente`,
  `fecha_entrega_cliente=bitacora.fecha_hora_entrega_2`.
- `agencia` se auto-llena desde `bitacora.modulacion.agencia` si esa relación
  existe (`OneToOne` inverso `BitacoraViaje.modulacion`).

Reglas:

- El signal **solo crea**. Nunca borra ni revierte un `Vacio` si luego se limpia
  la fecha en la bitácora; en ese caso el `Vacio` se elimina manualmente.
- Idempotente: `UniqueConstraint(bitacora_viaje, numero_contenedor)` +
  `get_or_create`.
- Registrado en `VaciosConfig.ready()` importando `modulos.vacios.signals`.

### Máquina de estados (acciones manuales, vistas `@require_POST`)

```
POR_VACIAR ──(registrar retorno a patio)──▶ EN_PATIO_ESPERANZA
EN_PATIO_ESPERANZA ──(asignar unidad + operador)──▶ ASIGNADO
ASIGNADO ──(reasignar)──▶ ASIGNADO            (crea CambioOperadorVacio)
ASIGNADO ──(registrar salida a naviera)──▶ ASIGNADO   (sella fecha_salida_naviera)
ASIGNADO ──(registrar entrega a naviera)──▶ ENTREGADO_NAVIERA
(cualquier estado ≠ ENTREGADO_NAVIERA) ──(registrar retraso)──▶ (mismo estado, crea RetrasoVacio)
```

1. **Registrar retorno a Patio Esperanza** → `estado='EN_PATIO_ESPERANZA'`,
   sella `fecha_retorno_patio`. El vaciado en sitio ocurre durante `POR_VACIAR`
   y no se modela como estado propio.
2. **Asignar unidad y operador** (`AsignarUnidadOperadorVacioForm`): solo
   operadores `LOCAL` activos y libres; auto-llenado del operador ligado a la
   unidad (`Operador.unidad_asignada`) en el navegador, editable. →
   `estado='ASIGNADO'`, sella `fecha_asignacion` la primera vez.
3. **Reasignar**: crea `CambioOperadorVacio` (unidad/operador saliente y
   entrante, causa, motivo), actualiza `unidad`/`operador` del `Vacio`,
   permanece `ASIGNADO`.
4. **Registrar salida a naviera**: sella `fecha_salida_naviera`.
5. **Registrar entrega a naviera**: `estado='ENTREGADO_NAVIERA'`, sella
   `fecha_entrega_naviera`. Fin del ciclo.
6. **Registrar retraso**: crea `RetrasoVacio`, marca `tiene_retraso=True`,
   dispara el correo a la agencia.

### "Operador libre"

`Operador` con `tipo='LOCAL'`, `activo=True`, que **no** aparezca como:

- `operador` de una `Modulacion` en estado `MODULADO` o `EN_PATIO_ESPERANZA`, ni
- `operador` de un `Vacio` en estado `ASIGNADO`, ni
- `operador` de una `BitacoraViaje` con `completado=False`.

Se listan ordenados por disponibilidad (p. ej. mayor tiempo sin viaje). El
usuario confirma la selección; no hay auto-asignación.

## Notificación a la agencia aduanal

- **Disparo:** automático al crear un `RetrasoVacio`.
- **Canal:** correo, `django.core.mail.EmailMultiAlternatives` (backend SendGrid
  ya configurado, mismo que usa `generar_reportes`).
- **Destinatario:** `vacio.agencia.email_contacto`.
- **Sin destinatario:** si no hay `agencia` o no tiene `email_contacto`, se
  guarda el `RetrasoVacio` igual con `notificado_agencia=False`, y la vista
  muestra un `warning` con enlace para capturar el correo y un botón
  "Reenviar aviso".
- **Contenido:** folio del vacío, contenedor, cliente, tipo de retraso
  (Maniobra / Retorno), motivo, fecha comprometida anterior
  (`fecha_compromiso_naviera`) y nueva fecha estimada
  (`fecha_estimada_nueva`), y la petición explícita de reasignar la fecha de
  entrega. Plantillas `templates/vacios/email/retraso_agencia.html` (+ texto
  plano).
- **Helper:** `modulos/vacios/notificaciones.py` →
  `notificar_retraso_agencia(retraso) -> bool`. En éxito sella
  `notificado_agencia=True` y `fecha_notificacion`. Los fallos se registran con
  `logger` y **no** lanzan excepción que tumbe la request.

## Reportes

Generador `modulos/reportes/generadores/vacios.py`, siguiendo el patrón de
`modulos/reportes/generadores/modulacion.py` (helpers `_rango_semana_iso`,
`_etiqueta_semana`; salida con `tipo`, `titulo`, `resumen`, `filas`, `tablas`).

### `VACIOS_ENTREGAS_SEMANAL`

- Entregas a naviera por operador y semana ISO, contadas por
  `fecha_entrega_naviera` dentro del rango; totales por operador.
- Tabla de cambios de operador por causa en el período (conteo de
  `CambioOperadorVacio` por `causa`).
- Snapshot de vacíos aún sin entregar (`estado != 'ENTREGADO_NAVIERA'`) con días
  transcurridos desde `fecha_entrega_cliente`.
- `resumen`: total entregados, operadores activos, operador top, promedio por
  operador, cambios de operador totales, vacíos pendientes.

### `VACIOS_RETRASOS`

- Retrasos del período (por `RetrasoVacio.created_at`) por tipo (Maniobra /
  Retorno), con folio, contenedor, cliente, motivo, fecha estimada nueva y si se
  notificó a la agencia.
- `resumen`: total retrasos, por tipo, % notificados a la agencia.

### Registro

- `GENERADORES` en `modulos/reportes/management/commands/generar_reportes.py`
  (`**gen_vacios.GENERADORES`).
- `modulos/reportes/generadores/narrativa.py`: entradas de narrativa para ambos
  tipos.
- `ConfiguracionReporte`: nuevos valores en `TIPO_CHOICES` y en `MODULO_CHOICES`
  (`VACIOS`). Migración en `modulos/reportes/migrations/`.

### Vista en pantalla

`EntregasVaciosPorOperadorView` en `modulos/reportes/views.py`, ruta
`/reportes/vacios/entregas-por-operador/`, con rango de fechas configurable,
reutilizando `generar_entregas_por_operador`. Enlace desde
`templates/reportes/historial.html`. Plantilla
`templates/reportes/entregas_vacios_por_operador.html` (basada en
`contenedores_por_operador.html`).

## UI

Plantillas en `templates/vacios/`, extendiendo `base.html`, usando las clases
utilitarias existentes (`.card`, `.grid`, `.btn-primary`, `.badge-*`) y los
helpers JS (`formatDate`, `showNotification`).

| Plantilla | Contenido |
|-----------|-----------|
| `dashboard.html` | Conteos por estado, retrasos abiertos, vacíos recientes. |
| `vacio_list.html` | Filtro mes/año (patrón `ModulacionListView`), búsqueda por folio/contenedor/cliente, filtros por estado y por naviera, badge de retraso, columna de días en proceso. |
| `vacio_detail.html` | Datos generales, línea de tiempo de estados, historial de `RetrasoVacio` y `CambioOperadorVacio`, botones de acción según estado, formularios de captura de naviera / agencia / `fecha_compromiso_naviera`. |
| `asignar_unidad_operador.html` | Reutiliza el `unidad_operador_map` (JSON unidad→operador) y el JS de auto-llenado de `templates/modulacion/asignar_unidad_operador.html`. |
| `vacio_confirm_delete.html` | Confirmación de borrado. |
| `naviera_list.html` / `naviera_form.html` / `naviera_confirm_delete.html` | CRUD del catálogo. |
| `email/retraso_agencia.html` | Cuerpo del correo a la agencia (+ versión texto). |

### Vistas (`modulos/vacios/views.py`)

- `vacios_dashboard` (FBV, `@login_required`).
- `VacioListView` (`LoginRequiredMixin`, `ListView`, `paginate_by=25`, filtro
  mes/año + estado + naviera + búsqueda).
- `VacioDetailView`.
- `VacioUpdateView` (edición de naviera, agencia, `fecha_compromiso_naviera`,
  observaciones).
- `VacioDeleteView`.
- `AsignarUnidadOperadorVacioView` (`UpdateView`), con `unidad_operador_map` en
  el contexto.
- FBVs `@require_POST`: `registrar_retorno_patio`, `reasignar_operador`,
  `registrar_salida_naviera`, `registrar_entrega_naviera`, `registrar_retraso`,
  `reenviar_aviso_retraso`.
- CRUD `Naviera`: `NavieraListView` / `NavieraCreateView` / `NavieraUpdateView`
  / `NavieraDeleteView`.

### URLs (`modulos/vacios/urls.py`, `app_name = 'vacios'`)

```
''                                   → dashboard
'lista/'                             → list
'<int:pk>/'                          → detail
'<int:pk>/editar/'                   → update
'<int:pk>/eliminar/'                 → delete
'<int:pk>/asignar/'                  → asignar
'<int:pk>/retorno-patio/'            → registrar_retorno_patio
'<int:pk>/reasignar/'                → reasignar_operador
'<int:pk>/salida-naviera/'           → registrar_salida_naviera
'<int:pk>/entrega-naviera/'          → registrar_entrega_naviera
'<int:pk>/retraso/'                  → registrar_retraso
'<int:pk>/retraso/<int:rid>/reenviar/' → reenviar_aviso_retraso
'navieras/'                          → naviera_list
'navieras/nueva/'                    → naviera_create
'navieras/<int:pk>/editar/'          → naviera_update
'navieras/<int:pk>/eliminar/'        → naviera_delete
```

### Admin (`modulos/vacios/admin.py`)

- `VacioAdmin`: `list_display` (folio, contenedor, cliente, estado, operador,
  unidad, naviera, `tiene_retraso`, `fecha_entrega_cliente`), `list_filter`
  (estado, naviera, `tiene_retraso`), `search_fields` (folio, contenedor),
  `readonly_fields` de las fechas selladas, inlines de `RetrasoVacio` y
  `CambioOperadorVacio`, `autocomplete_fields` (bitacora_viaje, cliente,
  operador, unidad, naviera, agencia).
- `NavieraAdmin`, `RetrasoVacioAdmin`, `CambioOperadorVacioAdmin`.

### Dashboard principal (`config/views.py` `IndexView`)

Tarjeta "Vacíos" con: por vaciar, en Patio Esperanza, asignados, retrasos
abiertos (vacíos con `tiene_retraso=True` y `estado != 'ENTREGADO_NAVIERA'`).

## Pruebas (`modulos/vacios/tests.py`)

Ejecución local con override a SQLite (mismo método que `modulacion` y
`reportes`, documentado en la memoria del proyecto).

1. **Signal de creación:**
   - Bitácora con `fecha_hora_entrega` → 1 `Vacio` `numero_contenedor='1'`.
   - Bitácora FULL con ambas fechas → 2 `Vacio` (`'1'` y `'2'`).
   - Guardar la bitácora dos veces → no duplica (idempotencia).
   - Bitácora sin fecha de entrega → 0 `Vacio`.
   - `agencia` auto-llenada desde `bitacora.modulacion.agencia` cuando existe.
2. **Folio:** único y correlativo por día; agrupado por `fecha_entrega_cliente`.
3. **Transiciones:** cada acción cambia el estado esperado y sella su fecha
   (`fecha_retorno_patio`, `fecha_asignacion`, `fecha_salida_naviera`,
   `fecha_entrega_naviera`). `fecha_asignacion` se sella una sola vez.
4. **Reasignación:** crea `CambioOperadorVacio` con unidad/operador saliente y
   entrante y la causa; el `Vacio` queda con la unidad/operador entrante y sigue
   `ASIGNADO`.
5. **Retraso:** crea `RetrasoVacio`, marca `tiene_retraso=True`, e intenta
   notificar. Con agencia con `email_contacto` → se envía correo
   (`mail.outbox`), `notificado_agencia=True`. Sin correo →
   `notificado_agencia=False` y `warning` en la respuesta; `reenviar_aviso`
   funciona tras capturar el correo.
6. **Operadores libres:** el cálculo excluye operadores ocupados en Modulación
   activa, en `Vacio` asignado, o en `BitacoraViaje` sin completar.
7. **Generadores de reporte:**
   - `VACIOS_ENTREGAS_SEMANAL`: conteo por operador y semana ISO; conteo de
     cambios de operador por causa; snapshot de pendientes con días.
   - `VACIOS_RETRASOS`: conteo por tipo; % notificados.
8. **`modulos/reportes/tests.py`:** ajuste para reconocer los nuevos tipos en
   `ConfiguracionReporte` y en el comando `generar_reportes`.

## Cambios fuera de `modulos/vacios`

| Archivo | Cambio |
|---------|--------|
| `config/settings.py` | `'modulos.vacios'` en `INSTALLED_APPS`. |
| `config/urls.py` | `path('vacios/', include('modulos.vacios.urls'))`. |
| `config/views.py` | Tarjeta de vacíos en `IndexView`. |
| `templates/base.html` | Enlace de navegación a Vacíos. |
| `modulos/modulacion/models.py` | Campo `email_contacto` en `Agencia` + migración. |
| `modulos/modulacion/admin.py` | `email_contacto` en el form de `Agencia` (opcional). |
| `modulos/reportes/generadores/vacios.py` | Nuevo (generadores). |
| `modulos/reportes/generadores/narrativa.py` | Narrativa de los 2 tipos. |
| `modulos/reportes/management/commands/generar_reportes.py` | Registrar `gen_vacios.GENERADORES`. |
| `modulos/reportes/models.py` | `TIPO_CHOICES` + `MODULO_CHOICES` (`VACIOS`) + migración. |
| `modulos/reportes/views.py` + `urls.py` | `EntregasVaciosPorOperadorView`. |
| `templates/reportes/historial.html` | Enlace a la vista de entregas de vacíos. |
| `templates/reportes/entregas_vacios_por_operador.html` | Nueva. |
| `CLAUDE.md` | Documentar la app `vacios`, su signal y sus reportes. |

## Fuera de alcance (YAGNI)

- Generar `BitacoraViaje` para el tramo Patio Esperanza → naviera.
- Integración automática con sistemas de la agencia aduanal para reasignar la
  fecha (el aviso es informativo; la agencia opera por fuera).
- Notificación por WhatsApp del retraso (solo correo en esta versión).
- Auto-asignación de operador sin confirmación humana.
- Modelar el vaciado en sitio como un estado propio.
- Revertir/eliminar el `Vacio` automáticamente si se limpia la fecha de entrega
  en la bitácora.
