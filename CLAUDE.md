# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BitacoraKasu is a Django 5.2.7-based fleet management system for a Mexican transport company. It tracks drivers (operadores), vehicles (unidades), trip logs (bitácoras), fuel consumption (combustible), workshop repairs (taller), purchases (compras), and warehouse inventory (almacén).

**Stack:** Python 3.14, Django 5.2.7, PostgreSQL (production), SQLite (dev)
**Virtual env:** `.venvKasu`
**Language:** Spanish (es-mx), all model names, comments, and UI in Spanish

## Efficiency Rules

Merged from [claude-token-efficient](https://github.com/drona23/claude-token-efficient) (coding + compressed profiles).

- Read existing files before writing. Don't re-read unless changed.
- Thorough in reasoning, concise in output. Short sentences, no filler/preamble/pleasantries.
- Return code first; explain after only if non-obvious. No boilerplate unless requested.
- Simplest working solution. No over-engineering, no speculative features, no abstractions for single-use code.
- No error handling for scenarios that cannot happen. Three similar lines beats a premature abstraction.
- No docstrings/type annotations on code not being changed.
- Review/debug: state the bug/cause, show the fix, stop. No guessing without reading code first; say so if cause is unclear.
- No sycophantic openers, no closing fluff, no compliments before/after a review.
- No emojis, em-dashes, or decorative Unicode. Plain hyphens and straight quotes. Spanish/accented text stays as required by this project's language rules above.
- Do not guess APIs, versions, flags, commit SHAs, or package names — verify by reading code or docs.

## Development Commands

```bash
# Start development server
python manage.py runserver

# Database migrations
python manage.py makemigrations
python manage.py migrate

# Run tests
python manage.py test

# Run tests for a specific module
python manage.py test modulos.almacen

# Django shell
python manage.py shell

# Create superuser
python manage.py createsuperuser
```

## Architecture

### Project Structure
```
config/                     # Django project settings, URLs, services
├── settings.py
├── urls.py
├── views.py                # IndexView (main dashboard with statistics)
├── context_processors.py   # Injects alertas_combustible count into all templates
├── storage_backends.py     # DigitalOcean Spaces / local storage switching
└── services/
    └── google_maps.py      # GoogleMapsService (Distance Matrix API)

modulos/                    # Business domain Django apps
├── operadores/
├── unidades/
├── bitacoras/
├── combustible/
├── taller/
├── compras/
├── almacen/
└── vacios/

templates/                  # HTML templates (79 total)
static/                     # CSS, JS, images
media/                      # User-uploaded files (local dev)
```

### Module Organization
Each module in `modulos/` follows standard Django app structure:
- `models.py` - Database models
- `views.py` - Views (class-based with LoginRequiredMixin)
- `urls.py` - URL routing
- `forms.py` - Django ModelForms with validation
- `admin.py` - Django admin configuration
- `signals.py` - Auto-update logic (combustible, taller, almacen, vacios only)

### Core Modules

| Module | Description | Key Models |
|--------|-------------|------------|
| **operadores** | Driver management | `Operador` (LOCAL/FORANEO/ESPERANZA) |
| **unidades** | Vehicle management | `Unidad` with fuel/maintenance tracking |
| **bitacoras** | Trip logs | `BitacoraViaje` with Google Maps integration |
| **combustible** | Fuel loading | `CargaCombustible`, `AlertaCombustible`, `Despachador`, `FotoCandadoNuevo` |
| **taller** | Workshop orders | `OrdenTrabajo`, `PiezaRequerida`, `TipoMantenimiento`, `SeguimientoOrden`, `HistorialMantenimiento` |
| **compras** | Purchasing | `Requisicion`, `OrdenCompra`, `Proveedor`, `Producto`, `Inventario` |
| **almacen** | Warehouse | `ProductoAlmacen`, `EntradaAlmacen`, `SolicitudSalida`, `SalidaAlmacen`, `MovimientoAlmacen`, `AlertaStock`, `SalidaRapidaConsumible` |
| **vacios** | Retorno de contenedores vacíos a la naviera | `Vacio`, `Naviera`, `RetrasoVacio`, `CambioOperadorVacio` |

### URL Structure
```
/                       → Dashboard (IndexView)
/login/ /logout/        → Auth
/admin/                 → Django admin
/operadores/            → operadores app
/unidades/              → unidades app
/bitacoras/             → bitacoras app
/combustible/           → combustible app
/taller/                → taller app
/compras/               → compras app
/almacen/               → almacen app (51 URL patterns)
/vacios/                → vacios app
```

## Key Services

### GoogleMapsService (`config/services/google_maps.py`)
- `calcular_distancia(cp_origen, cp_destino)` → `{success, distancia_km, duracion_min, distancia_texto, duracion_texto}`
- `batch_calcular_distancias(lista_destinos, cp_origen)` → batch processing
- `validar_codigo_postal(cp, pais)` → validation via Geocoding API
- Used via `BitacoraViaje.calcular_distancia_google()` and AJAX endpoint

## Database

- **Production:** PostgreSQL via `DBURL` environment variable
- **Development:** SQLite fallback
- **ORM:** Standard Django ORM with select_related/prefetch_related for performance

## File Storage (`config/storage_backends.py`)

When `USE_SPACES=True`:
- `StaticStorage` / `MediaStorage` → DigitalOcean Spaces (SFO3, CDN-backed)
- Signed URLs expire in 1 hour for private files
- Auto-adds timestamp to avoid filename collisions
- Organized by date: `/YYYY/MM/`

Otherwise: local filesystem storage.

**Upload paths:**
- `combustible/{type}/%Y/%m/`
- `almacen/productos/%Y/%m/`
- `almacen/facturas/%Y/%m/`
- `taller/seguimientos/`

## Language and Localization

- All code comments, model verbose_name, and UI text in Spanish
- `LANGUAGE_CODE = 'es-mx'`
- `TIME_ZONE = 'America/Mexico_City'`
- Default origin postal code: `40812`
- Currency: MXN (peso mexicano), formatted with `formatMXN()` JS helper

## Template System

Templates extend `base.html` which provides:
- Navigation sidebar with all module links
- Django messages display (success, error, warning, info)
- CSS utility classes: `.card`, `.grid`, `.btn-primary`, `.badge-*`
- JavaScript helpers: `formatMXN()`, `formatDate()`, `showNotification()`

Available blocks: `title`, `extra_css`, `breadcrumb`, `content`, `extra_js`

**Template counts by module:** almacen (23), compras (14), combustible (8), operadores/unidades/bitacoras/taller (4-5 each)

## Authentication & Permissions

- All views require login via `LoginRequiredMixin`
- Login URL: `/login/` → `registration/login.html`
- After login redirects to: `inicio` (IndexView)
- Admin panel: `/admin/`

**Custom model permissions:**
- `compras`: `aprobar_requisicion`, `procesar_compra`, `gestionar_almacen`
- `taller`: `diagnosticar_orden`, `asignar_mecanico`, `aprobar_orden`, `cerrar_orden`
- `almacen`: `autorizar_salida_almacen`

## Key Patterns

### Model Save Overrides
`BitacoraViaje.save()` automatically:
- Validates date and kilometraje consistency
- Sets `completado=True` when `fecha_llegada` is provided
- Updates `unidad.kilometraje_actual`

### Fusión de Sencillos en Full (`modulos/bitacoras/services_full.py`)
- Al guardar/editar un viaje `SENCILLO` cuya unidad ya tiene otro `SENCILLO` en curso con el **mismo operador**, se ofrece (modal JS + endpoint `bitacoras:verificar_full`) fusionarlos en un `FULL`: `directo` si coinciden `cliente` y `cp_destino`, `reparto` si difieren (llena `cliente_2`/`cp_destino_2`).
- Capacidad por unidad: máx. 2 contenedores en curso (SENCILLO=1, FULL=2). Unidad llena → fuera del selector (`unidades_bloqueadas_ids`). Operador distinto sobre una unidad con sencillo en curso → bloqueado (no se permiten dos sencillos separados).
- Aplica a alta manual (`BitacoraCreateView`), edición (`BitacoraUpdateView`) y `EnviarABitacoraView` de modulación (esta liga la Modulación al FULL sin crear un 2º `BitacoraViaje`). La carga masiva no pasa por aquí.

### Django Signals

**combustible/signals.py:**
- Auto-generate `AlertaCombustible` when candado state is ALTERADO/VIOLADO/SIN_CANDADO on `CargaCombustible.save()`

**taller/signals.py:**
- Update `Unidad.ultimo_mantenimiento` and `proximo_mantenimiento` when `OrdenTrabajo` is completed
- Update `Unidad.kilometraje_actual` from service exit mileage

**almacen/signals.py:**
- Auto-generate `AlertaStock` when `ProductoAlmacen` stock changes (STOCK_MINIMO, STOCK_AGOTADO, PROXIMO_CADUCAR, CADUCADO)
- Create `MovimientoAlmacen` entries as audit trail
- Reduce stock when `ItemSalidaAlmacen` or `SalidaRapidaConsumible` is created
- Increase stock when `ItemEntradaAlmacen` is added

**vacios/signals.py:**
- `post_save` sobre `BitacoraViaje`: crea un `Vacio` por contenedor con fecha de entrega registrada (`fecha_hora_entrega` / `fecha_hora_entrega_2`). Idempotente; solo crea, nunca borra.

**storage_backends.py signals:**
- `post_delete`: auto-delete files from storage when model is deleted
- `pre_save`: delete old file when file field is updated

### Folio Generation (auto-generated in `save()`)
- `Requisicion`: `REQ-YYYYMMDD-XXX`
- `OrdenCompra`: `OC-YYYYMMDD-XXX`
- `OrdenTrabajo`: `OT-YYYYMMDD-XXX`
- `EntradaAlmacen`: `ENT-YYYYMMDD-XXX`
- `SolicitudSalida`: `SOL-YYYYMMDD-XXX`
- `SalidaAlmacen`: `SAL-YYYYMMDD-XXX`
- `SalidaRapidaConsumible`: `CON-YYYYMMDD-XXX`
- `Vacio`: `VAC-YYYYMMDD-XXX`

### Status Workflows

**combustible:** INICIADO → EN_PROCESO → COMPLETADO / CANCELADO

**taller:** PENDIENTE → EN_DIAGNOSTICO → ESPERANDO_PIEZAS → EN_REPARACION → EN_PRUEBAS → COMPLETADA / CANCELADA

**compras/requisicion:** PENDIENTE → APROBADA → EN_COMPRA → COMPLETADA / RECHAZADA / CANCELADA

**compras/orden:** PENDIENTE → ENVIADA → CONFIRMADA → EN_TRANSITO → RECIBIDA / CANCELADA

**almacen/solicitud:** PENDIENTE → AUTORIZADA → PROCESADA / RECHAZADA / CANCELADA

**vacios:** POR_VACIAR → EN_PATIO_ESPERANZA → ASIGNADO → ENTREGADO_NAVIERA

### Context Processors
`config/context_processors.py`: Injects `alertas_combustible_pendientes` count into every template for superusers.

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

## Dashboard (IndexView)

Main dashboard at `/` shows statistics for all modules:
- Operadores activos, Unidades con mantenimiento próximo
- Bitácoras del mes, viajes en curso, alertas de rendimiento
- Cargas de combustible del día, alertas de candado pendientes
- Órdenes de taller activas, unidades en servicio
- Requisiciones pendientes, órdenes de compra activas
- Productos con stock bajo, valor total de inventario, alertas sin resolver

## Dependencies (`requirements.txt`)

```
Django==5.2.7
psycopg2-binary==2.9.11      # PostgreSQL
django-environ==0.12.0        # .env management
django-storages==1.14.6       # S3/Spaces storage
django-template-maths==0.2.0  # Math operations in templates
boto3==1.41.5                 # AWS SDK (DigitalOcean Spaces)
pillow==12.0.0                # Image processing
requests==2.32.5              # HTTP (Google Maps)
python-dotenv==1.2.1          # .env support
python-decouple==3.8          # Config management
whitenoise                    # Static files for production
gunicorn                      # WSGI server
```

## Environment Variables (`.env`)

```
DEBUG=True
SECRET_KEY=...
DBURL=postgres://user:pass@host:port/db
GOOGLE_MAPS_API_KEY=...
EMAIL_HOST_PASSWORD=...        # SendGrid API key
USE_SPACES=True/False
SPACES_ACCESS_KEY=...
SPACES_SECRET_KEY=...
SPACES_BUCKET_NAME=...
SPACES_REGION=sfo3
SPACES_CDN_ENDPOINT=...
# Microsoft Graph — importación de programación de citas de LCTPC
GRAPH_TENANT_ID=...
GRAPH_CLIENT_ID=...
GRAPH_CLIENT_SECRET=...            # permiso de aplicación Mail.Read
MODULACION_LCTPC_MAILBOX=calidad@transporteskasu.com.mx
MODULACION_LCTPC_REMITENTE=atencionspf@lctpc.com.mx
MODULACION_TERMINAL_LCTPC=L.C. Terminal Portuaria de Contenedores, S.A. de C.V.
MODULACION_LCTPC_POLL_MINUTOS=15
```

## Production Deployment

- **WSGI:** `gunicorn config.wsgi` (Procfile)
- **Static files:** WhiteNoise (`CompressedManifestStaticFilesStorage`)
- **Media:** DigitalOcean Spaces (SFO3)
- **Email:** SendGrid SMTP backend
- **Database:** PostgreSQL via `DBURL`

## Reparto con Codex

El plugin de Codex está instalado. El trabajo se reparte así.

Te quedas tú (Claude):
- Entender el problema y preguntar lo que falte.
- Planear los pasos antes de tocar archivos.
- Decidir la arquitectura y los límites de cada cambio.
- Revisar todo lo que vuelva de Codex.

Se le pasa a Codex, con el subagente codex-rescue y sin esperar a que
te lo pida:
- Construcción repetitiva y larga.
- Refactors grandes que tocan muchos archivos.
- Errores atorados que ya se intentaron una vez.

Reglas fijas:
- Nada de lo que vuelve de Codex se da por bueno sin revisar.
- Si Codex falla dos veces en la misma tarea, la tarea regresa a ti.
- Delegar no es desentenderse: dime qué pediste y qué volvió.## Reparto con Codex

El plugin de Codex está instalado. El trabajo se reparte así.

Te quedas tú (Claude):
- Entender el problema y preguntar lo que falte.
- Planear los pasos antes de tocar archivos.
- Decidir la arquitectura y los límites de cada cambio.
- Revisar todo lo que vuelva de Codex.

Se le pasa a Codex, con el subagente codex-rescue y sin esperar a que
te lo pida:
- Construcción repetitiva y larga.
- Refactors grandes que tocan muchos archivos.
- Errores atorados que ya se intentaron una vez.

Reglas fijas:
- Nada de lo que vuelve de Codex se da por bueno sin revisar.
- Si Codex falla dos veces en la misma tarea, la tarea regresa a ti.
- Delegar no es desentenderse: dime qué pediste y qué volvió.