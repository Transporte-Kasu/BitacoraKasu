# Importación automática de la programación de citas de LCTPC

**Fecha:** 2026-09-08
**Módulo:** `modulos/modulacion`
**Estado:** Aprobado — listo para plan de implementación

## Contexto

LCTPC ("L.C. Terminal Portuaria de Contenedores, S.A. de C.V.", Hutchison Ports)
envía a diario un correo desde `atencionspf@lctpc.com.mx` al buzón
`calidad@transporteskasu.com.mx` con el asunto
*"Programacion de contenedores a SPF, por horario preferente, para el <fecha>"*
y un archivo adjunto `3ZYM_<AAAAMMDDhhmm>.xls`.

El adjunto **no es Excel**: es una tabla HTML con extensión `.xls`, codificación
ISO-8859-1. Estructura constante:

- Celda título `class="oscuro"` con `colspan="5"`:
  `"Programación de contenedores a SPF, para el 07 September 2026"`
  (el nombre del mes llega a veces en inglés — `September` — y a veces en
  español — `Septiembre`).
- Encabezados: `CONTENEDOR | TRANSPORTISTA | FOLIO | VENTANA DE REGISTRO | HORARIO DE CITA`.
- Filas de datos: p. ej.
  `GXYU5129072 | 3ZYM | 617210 | 01:30-03:00 | 03:00-03:59`.

Reglas de negocio (definidas por el usuario):

- **Fecha de modulación ante aduana:** la del asunto del correo y la de la celda
  título del Excel. Es la fecha de la cita.
- **Horario de registro:** la hora de **inicio** de `VENTANA DE REGISTRO`
  (`01:30` en el ejemplo).
- **Horario de ingreso:** la hora de **inicio** de `HORARIO DE CITA`
  (`03:00` en el ejemplo).
- **Carril** y **hora de carga:** no vienen en este Excel; quedan opcionales/vacíos.
- **FULL / SENCILLO:** las filas que comparten la misma hora de inicio de
  `VENTANA DE REGISTRO` se emparejan de 2 en 2 (en el orden del Excel) formando
  un **FULL** (2 contenedores por tracto). El sobrante de un grupo impar queda
  como **SENCILLO**. En el archivo de ejemplo: 6 filas a las 01:30 → 3 FULL;
  02:30, 04:30, 06:30, 07:30 con una fila cada uno → 4 SENCILLO.
  (Nota: la leyenda del correo dice "Camión Full = mismo folio", pero en los
  datos reales los folios son distintos; manda la regla del usuario:
  agrupación por hora de inicio de la ventana de registro.)

El módulo `modulacion` ya existe: `Modulacion` es un registro por contenedor
(origen `HAL9MIL` vía API, o `MANUAL`), con los campos `carril`,
`hora_registro` (`DateTimeField`), `hora_ingreso` (`DateTimeField`),
`hora_carga` (`DateTimeField`) y `fecha_modulacion_aduana` (`DateField`) ya
presentes. También existen `TerminalPortuaria`, `Agencia`, el dashboard de
modulación y el scheduler unificado en `config/scheduler.py`
(`BackgroundScheduler` arrancado desde `modulos/reportes/apps.py::ready()`,
que ejecuta management commands vía `call_command`).

## Objetivo

Cuando llega el correo de LCTPC, BitacoraKasu debe leerlo por Microsoft Graph
API, parsear el adjunto y, por cada contenedor:

- **Actualizar** la Modulación existente de ese contenedor en la terminal LCTPC
  (si existe y no está cerrada), rellenando `fecha_modulacion_aduana`,
  `hora_registro`, `hora_ingreso`, `tipo_cita` y `grupo_cita`.
- **Crear** una Modulación *stub* marcada como incompleta si el contenedor no
  tiene Modulación previa.

Disparado tanto por un poll programado (cada 15 min) como por un botón
"Importar ahora" en el dashboard. Cada correo procesado deja una fila de
auditoría que además sirve de idempotencia.

## Decisiones tomadas durante el brainstorming

| Tema | Decisión |
|---|---|
| Alcance | Integración automática en BitacoraKasu (no lectura manual puntual). |
| Qué hacer con los datos | Actualizar si la Modulación existe; crear stub si no. |
| Conexión al buzón | Microsoft Graph API, OAuth2 client credentials (app-only), permiso **`Mail.Read`** (solo lectura). |
| Disparador | Poll programado (APScheduler, 15 min) **y** botón manual "Importar ahora". |
| Formato del adjunto | Tabla HTML con extensión `.xls`, ISO-8859-1. Parser con **`beautifulsoup4`** (dependencia nueva). |
| Grupo impar en FULL | El sobrante queda como `SENCILLO` (emparejar 2 a 2 en orden del Excel). |
| Folio de LCTPC | Se anexa a `observaciones` de la Modulación (sin campo nuevo para el folio). |
| Representación FULL/SENCILLO | Opción A: dos campos nuevos en `Modulacion` (`tipo_cita`, `grupo_cita`). Sin modelo `CitaTerminal`. |
| Crear Modulación sin datos | Stub con placeholders (`agencia='POR DEFINIR'`, `tipo_contenedor=''`, `peso_toneladas=0`, sin cliente) + nota en `observaciones`; visible como "incompleta". |
| Conjunto de match | Cualquier Modulación de la terminal LCTPC cuyo `estado` **no** sea `ENVIADO_BITACORA` ni `RETIRADO_TERCERO` (permite reescribir horarios si LCTPC manda una programación corregida). |
| Idempotencia | Tabla `ImportacionProgramacionLCTPC` con `graph_message_id` único (no se depende de marcar el correo como leído). |

## Arquitectura

```
config/scheduler.py ──interval 15 min──┐
dashboard modulación "Importar ahora" ─┤
management command ────────────────────┴──► services_importacion.importar_programaciones_lctpc()
                                              │
        ┌─────────────────────────────────────┼──────────────────────────────────┐
        ▼                                     ▼                                  ▼
 services_graph.py                    services_lctpc.py                 models.ImportacionProgramacionLCTPC
 (MS Graph, app-only, solo red)       (parser HTML + mes ES/EN +        (idempotencia + reporte por correo)
                                       clasificación FULL/SENCILLO,
                                       puro: sin BD ni red)
```

Todos los archivos nuevos viven en `modulos/modulacion/`.

| Archivo | Responsabilidad | Dependencias |
|---|---|---|
| `services_graph.py` | Token client-credentials; listar correos del remitente; bajar el adjunto `.xls`. Sin lógica de negocio. | `requests`, `settings` |
| `services_lctpc.py` | `parsear_programacion(bytes, asunto) -> ProgramacionParseada`; parseo de mes ES/EN; `clasificar(renglones) -> renglones con tipo_cita/grupo_cita`. Puro. | `bs4` |
| `services_importacion.py` | Orquesta: correos no procesados → parsear → match/crear Modulaciones → escribir `ImportacionProgramacionLCTPC`. | los dos anteriores + models |
| `management/commands/importar_programacion_lctpc.py` | Envoltura fina: llama al orquestador, imprime resumen. | orquestador |

### `services_graph.py`

- **Auth:** OAuth2 client credentials (app-only). POST a
  `https://login.microsoftonline.com/{GRAPH_TENANT_ID}/oauth2/v2.0/token`
  con `client_id`, `client_secret`, `scope=https://graph.microsoft.com/.default`,
  `grant_type=client_credentials`, usando `requests` (no se agrega `msal`).
  Token cacheado en memoria del proceso hasta ~60 s antes de expirar.
- **Permiso de aplicación:** `Mail.Read` (solo lectura). No se pide
  `Mail.ReadWrite`.
- **Listar correos:**
  `GET /users/{MAILBOX}/messages`
  `?$filter=from/emailAddress/address eq '{REMITENTE}'`
  `&$select=id,subject,receivedDateTime`
  `&$orderby=receivedDateTime desc&$top=25`.
- **Adjunto:**
  `GET /users/{MAILBOX}/messages/{id}/attachments` → primer
  `#microsoft.graph.fileAttachment` cuyo `name` termine en `.xls`
  (case-insensitive); se devuelve `base64decode(contentBytes)`.
- Fallos de red / token / HTTP != 2xx → excepción propia `GraphError`. El
  orquestador la captura y la registra sin abortar el resto del proceso.

### `services_lctpc.py`

- **Decodificación:** `contenido.decode('iso-8859-1')`.
- **HTML:** `BeautifulSoup(texto, 'html.parser')`. Se toma la primera
  `<table>` que tenga el encabezado `CONTENEDOR`; se recorren sus `<tr>`
  tomando el texto de cada `<td>` (se ignoran las filas de `<th>`).
- **Fecha:**
  - Del asunto del correo: regex `para el (.+)$` → `"07 September 2026"`.
  - De la celda título del Excel (`class="oscuro"`): mismo regex sobre su texto.
  - Parseo con diccionario de meses **ES + EN** (`enero..diciembre`,
    `january..december`), case-insensitive, formato `d[d] <mes> yyyy`.
  - Si ambas fechas existen y **difieren**, se usa la del **asunto** y se
    registra el aviso en el reporte. Si solo hay una, se usa esa. Si no hay
    ninguna → error de parseo del correo.
- **Salida:**

  ```python
  @dataclass
  class RenglonLCTPC:
      contenedor: str            # normalizado: .strip().upper()
      transportista: str
      folio_lctpc: str
      registro_inicio: datetime.time
      registro_fin: datetime.time
      cita_inicio: datetime.time
      cita_fin: datetime.time
      tipo_cita: str = ''        # 'FULL' | 'SENCILLO', lo pone clasificar()
      grupo_cita: str = ''       # uuid4().hex compartido por el par FULL

  @dataclass
  class ProgramacionParseada:
      fecha: datetime.date
      fecha_titulo_excel: datetime.date | None
      fecha_asunto: datetime.date | None
      renglones: list[RenglonLCTPC]
      avisos: list[str]
  ```

- **Rangos horarios:** `"01:30-03:00"` → `(time(1,30), time(3,0))`. Formato
  esperado `HH:MM-HH:MM`; un valor que no matchee levanta error de parseo
  (queda en el reporte como correo con `ERROR`).
- **`clasificar(renglones)`:** agrupa por `registro_inicio` **preservando el
  orden de aparición**; dentro de cada grupo empareja `[0,1] [2,3] ...`; cada
  par → ambos `tipo_cita='FULL'` con el mismo `grupo_cita = uuid4().hex`; el
  elemento sobrante de un grupo impar → `tipo_cita='SENCILLO'`, `grupo_cita=''`.
  Grupo de tamaño 1 → `SENCILLO`.

### `services_importacion.py`

`importar_programaciones_lctpc() -> ResumenImportacion` (dataclass con
`correos_procesados`, `correos_saltados`, `correos_con_error`, `creadas`,
`actualizadas`, `ambiguas`).

```
correos = services_graph.listar_correos(REMITENTE)          # más nuevo primero, top 25
para cada correo:
    si ImportacionProgramacionLCTPC.objects.filter(graph_message_id=correo.id).exists():
        correos_saltados += 1;  continuar

    try:
        xls = services_graph.descargar_adjunto_xls(correo.id)
        prog = services_lctpc.parsear_programacion(xls, correo.asunto)
        services_lctpc.clasificar(prog.renglones)
    except (GraphError, ErrorParseoLCTPC) as exc:
        ImportacionProgramacionLCTPC.objects.create(
            graph_message_id=correo.id, asunto=correo.asunto,
            fecha_recibido=correo.received, estado='ERROR',
            mensaje_error=str(exc)[:2000])
        correos_con_error += 1;  continuar

    with transaction.atomic():                               # todo el correo o nada
        terminal = TerminalPortuaria.objects.get_or_create(
            nombre=settings.MODULACION_TERMINAL_LCTPC)[0]
        detalle = []
        para cada r in prog.renglones:
            qs = (Modulacion.objects
                  .filter(terminal_portuaria=terminal, contenedor=r.contenedor)
                  .exclude(estado__in=['ENVIADO_BITACORA', 'RETIRADO_TERCERO'])
                  .order_by('-fecha_recepcion'))
            m = qs.first()
            hora_reg = _aware(prog.fecha, r.registro_inicio)
            hora_ing = _aware(prog.fecha, r.cita_inicio)
            si m:
                m.fecha_modulacion_aduana = prog.fecha
                m.hora_registro = hora_reg
                m.hora_ingreso  = hora_ing
                m.tipo_cita     = r.tipo_cita
                m.grupo_cita    = r.grupo_cita
                _anexar_observacion(m, r)          # idempotente (ver abajo)
                m.save()
                resultado = 'ACTUALIZADA_AMBIGUA' si qs.count() > 1 else 'ACTUALIZADA'
            si no:
                m = Modulacion.objects.create(
                    agencia=Agencia.objects.get_or_create(nombre='POR DEFINIR')[0],
                    terminal_portuaria=terminal,
                    tipo_contenedor='', peso_toneladas=Decimal('0'),
                    contenedor=r.contenedor, cliente=None,
                    origen='LCTPC', estado='PENDIENTE',
                    fecha_modulacion_aduana=prog.fecha,
                    hora_registro=hora_reg, hora_ingreso=hora_ing,
                    tipo_cita=r.tipo_cita, grupo_cita=r.grupo_cita,
                    observaciones=('Creada desde programación LCTPC — '
                                   'faltan agencia/cliente/tipo/peso.\n'
                                   + _linea_observacion(r)))
                resultado = 'CREADA'
            detalle.append({'contenedor': r.contenedor, 'folio_lctpc': r.folio_lctpc,
                            'resultado': resultado, 'modulacion_id': m.id, 'tipo_cita': r.tipo_cita})

        ImportacionProgramacionLCTPC.objects.create(
            graph_message_id=correo.id, asunto=correo.asunto,
            fecha_recibido=correo.received,
            fecha_modulacion_aduana=prog.fecha,
            estado='OK_CON_AVISOS' si (prog.avisos or hay ambiguas) else 'OK',
            total_renglones=len(prog.renglones),
            creadas=..., actualizadas=..., ambiguas=...,
            detalle=detalle, mensaje_error='\n'.join(prog.avisos))
```

- `_aware(fecha, hora)` = `timezone.make_aware(datetime.combine(fecha, hora))`
  en `settings.TIME_ZONE` (`America/Mexico_City`). `hora_carga` y `carril` no
  se tocan.
- `_linea_observacion(r)` = `f"Cita LCTPC {r.folio_lctpc} — reg {r.registro_inicio:%H:%M} / cita {r.cita_inicio:%H:%M} ({r.tipo_cita})"`.
- `_anexar_observacion(m, r)`: agrega `_linea_observacion(r)` a `m.observaciones`
  en una línea nueva **solo si esa línea exacta aún no está** (re-correr el
  mismo correo, o una programación corregida con el mismo folio, no duplica).
- Nuevo choice en `Modulacion.ORIGEN_CHOICES`: `('LCTPC', 'Programación LCTPC')`.

### `management/commands/importar_programacion_lctpc.py`

`handle()` llama a `importar_programaciones_lctpc()` y hace
`self.stdout.write` con el resumen. Sin argumentos.

## Modelos

### Nuevo: `ImportacionProgramacionLCTPC`

| Campo | Tipo | Nota |
|---|---|---|
| `graph_message_id` | `CharField(max_length=255, unique=True)` | idempotencia |
| `asunto` | `CharField(max_length=300)` | |
| `fecha_recibido` | `DateTimeField` | `receivedDateTime` del correo |
| `fecha_modulacion_aduana` | `DateField(null=True, blank=True)` | fecha parseada de la cita |
| `estado` | `CharField(max_length=15, choices=OK / OK_CON_AVISOS / ERROR)` | |
| `total_renglones` | `PositiveIntegerField(default=0)` | |
| `creadas` | `PositiveIntegerField(default=0)` | |
| `actualizadas` | `PositiveIntegerField(default=0)` | |
| `ambiguas` | `PositiveIntegerField(default=0)` | match con >1 candidata |
| `detalle` | `JSONField(default=list)` | `[{contenedor, folio_lctpc, resultado, modulacion_id, tipo_cita}]` |
| `mensaje_error` | `TextField(blank=True)` | traza corta si `ERROR`; avisos si `OK_CON_AVISOS` |
| `creado_en` | `DateTimeField(auto_now_add=True)` | |

`Meta.ordering = ['-fecha_recibido']`. `__str__` → `f"{asunto} ({estado})"`.

### Cambios en `Modulacion`

- `+ tipo_cita = CharField(max_length=10, blank=True, choices=[('FULL','Full'),('SENCILLO','Sencillo')], verbose_name="Tipo de cita")`
- `+ grupo_cita = CharField(max_length=32, blank=True, db_index=True, verbose_name="Grupo de cita FULL", help_text="Comparten valor los 2 contenedores de un mismo FULL.")`
- `ORIGEN_CHOICES += ('LCTPC', 'Programación LCTPC')`

Una sola migración cubre el modelo nuevo y los 3 cambios en `Modulacion`.

## Disparadores y UI

### Scheduler

En `config/scheduler.py::iniciar_scheduler()`, un segundo job en el mismo
`BackgroundScheduler`:

```python
scheduler.add_job(
    func=_ejecutar_importacion_lctpc,      # hace call_command('importar_programacion_lctpc')
    trigger='interval',
    minutes=getattr(settings, 'MODULACION_LCTPC_POLL_MINUTOS', 15),
    id='importar_programacion_lctpc',
    replace_existing=True,
    jobstore='default',
    misfire_grace_time=600,
)
```

`_ejecutar_importacion_lctpc()` sigue el mismo patrón que `_ejecutar_reportes()`
(try/except + `logger.exception`). Se agrega `'importar_programacion_lctpc'` al
set `_SKIP_COMMANDS` en `modulos/reportes/apps.py` para que correr el command a
mano no arranque el scheduler.

### Botón manual + panel

- URL: `path('lctpc/importar/', views.importar_programacion_lctpc, name='lctpc_importar')`
  — vista `LoginRequiredMixin`, solo `POST`, llama al orquestador,
  `messages.success` / `messages.warning` con contadores, redirige al dashboard.
- URL: `path('lctpc/', views.ImportacionProgramacionLCTPCListView.as_view(), name='lctpc_list')`
  y `path('lctpc/<int:pk>/', views.ImportacionProgramacionLCTPCDetailView.as_view(), name='lctpc_detail')`
  (ambas `LoginRequiredMixin`).
- En el template del dashboard de modulación: panel "Programaciones LCTPC" con
  las últimas ~10 filas de `ImportacionProgramacionLCTPC` (fecha recibido,
  asunto, estado con badge, `creadas`/`actualizadas`/`ambiguas`), un `<form method="post">`
  con el botón "Importar ahora" y link al detalle (que renderiza `detalle`
  renglón por renglón).

### Admin

Registrar `ImportacionProgramacionLCTPC` read-only (`list_display` con estado y
contadores, `readonly_fields` = todos). `Modulacion` admin: agregar `tipo_cita`
al `list_display` / `list_filter` si aplica al patrón existente.

## Settings nuevos (`config/settings.py`, todos vía `env`)

```python
# Microsoft Graph — lectura del buzón de calidad
GRAPH_TENANT_ID     = env.str('GRAPH_TENANT_ID', default='')
GRAPH_CLIENT_ID     = env.str('GRAPH_CLIENT_ID', default='')
GRAPH_CLIENT_SECRET = env.str('GRAPH_CLIENT_SECRET', default='')

# Importación de programación de citas de LCTPC
MODULACION_LCTPC_MAILBOX      = env.str('MODULACION_LCTPC_MAILBOX', default='calidad@transporteskasu.com.mx')
MODULACION_LCTPC_REMITENTE    = env.str('MODULACION_LCTPC_REMITENTE', default='atencionspf@lctpc.com.mx')
MODULACION_TERMINAL_LCTPC     = env.str('MODULACION_TERMINAL_LCTPC', default='L.C. Terminal Portuaria de Contenedores, S.A. de C.V.')
MODULACION_LCTPC_POLL_MINUTOS = env.int('MODULACION_LCTPC_POLL_MINUTOS', default=15)
```

Si `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` están vacíos,
`services_graph` levanta `GraphError("Graph API no configurada")` y el job/botón
lo reporta sin romper nada.

## Dependencias

Agregar a `requirements.txt`:

```
beautifulsoup4==4.12.3
```

(o la última 4.x estable al momento de implementar). Instalar en `.venvKasu`.

## Pruebas (TDD)

Fixtures: copiar los 3 `.xls` reales de la raíz del proyecto a
`modulos/modulacion/tests/fixtures/lctpc/`
(`3ZYM_202609031849.xls`, `3ZYM_202609041650.xls`, `3ZYM_202609051401.xls`).

### Parser (`services_lctpc`)

- Extrae las 10 filas del archivo grande con columnas correctas y contenedor
  normalizado a mayúsculas.
- Mes en inglés (`07 September 2026`) y en español (`04 Septiembre 2026`) →
  misma `date`.
- Fecha del título del Excel y fecha del asunto coinciden → sin aviso.
- Fecha del asunto distinta a la del título → usa la del asunto + aviso.
- Decodificación ISO-8859-1: el título contiene `ó` (`Programación`).
- Rango horario mal formado → `ErrorParseoLCTPC`.

### Clasificación

- 6 filas con misma `registro_inicio` → 3 FULL, cada par con `grupo_cita`
  compartido y distinto entre pares.
- 5 filas → 2 FULL + 1 SENCILLO (el último en orden de Excel).
- 1 fila → SENCILLO, `grupo_cita=''`.
- Archivo real `3ZYM_202609051401.xls` → exactamente 3 FULL + 4 SENCILLO.

### Orquestador (`services_graph` mockeado con `unittest.mock.patch`)

- Contenedor sin Modulación previa → crea stub con `origen='LCTPC'`,
  `peso_toneladas=0`, `tipo_contenedor=''`, `agencia.nombre='POR DEFINIR'`,
  nota en `observaciones`.
- Contenedor con Modulación PENDIENTE en terminal LCTPC → la actualiza
  (`hora_registro`, `hora_ingreso`, `fecha_modulacion_aduana`, `tipo_cita`,
  `grupo_cita`) y anexa la línea de observación.
- Re-procesar el mismo correo → saltado por `graph_message_id`; sin cambios.
- Reprocesar una programación equivalente (otro `message_id`, mismo folio) →
  no duplica la línea en `observaciones`.
- Modulación en estado `ENVIADO_BITACORA` / `RETIRADO_TERCERO` → se ignora;
  si no hay otra candidata, se crea stub.
- 2 candidatas activas para el mismo contenedor → actualiza la más reciente por
  `fecha_recepcion` y marca `resultado='ACTUALIZADA_AMBIGUA'` + `ambiguas=1`.
- Correo sin adjunto `.xls` → fila `ImportacionProgramacionLCTPC` con
  `estado='ERROR'`, el resto de correos se sigue procesando.
- `GraphError` al listar → el orquestador no revienta; `ResumenImportacion`
  con `correos_con_error`/log, sin filas nuevas.
- `hora_registro` / `hora_ingreso` quedan aware en `America/Mexico_City` y con
  la fecha de `fecha_modulacion_aduana`.

### Command

- `call_command('importar_programacion_lctpc')` corre el orquestador y no
  arranca el scheduler (`'importar_programacion_lctpc'` en `_SKIP_COMMANDS`).

## Fuera de alcance

- Descarga del correo por navegador / credenciales de usuario.
- Permiso `Mail.ReadWrite`, marcar correos como leídos, mover a carpeta.
- Multi-terminal: el código queda parametrizado por settings, pero solo se
  prueba y se opera LCTPC.
- Completar a mano agencia/cliente/tipo/peso de los stubs (se hace en las
  pantallas de Modulación ya existentes).
- UI para editar `tipo_cita` / `grupo_cita`.
- Notificaciones (correo/WhatsApp) al importar.

## Actualización de documentación

Al terminar, añadir a `CLAUDE.md`:

- Sección de variables de entorno: `GRAPH_*` y `MODULACION_LCTPC_*`.
- En "Django Signals" / servicios de `modulacion`: nota del import LCTPC
  (Graph API + parser HTML + poll 15 min + botón manual).
- En "Folio Generation" no aplica; en la tabla de módulos, mencionar
  `ImportacionProgramacionLCTPC` en `modulacion`.
