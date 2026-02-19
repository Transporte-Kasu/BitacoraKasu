# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BitacoraKasu is a Django 5.2.7-based fleet management system for a Mexican transport company. It tracks drivers (operadores), vehicles (unidades), trip logs (bitácoras), fuel consumption (combustible), workshop repairs (taller), purchases (compras), and warehouse inventory (almacén).

**Stack:** Python 3.14, Django 5.2.7, PostgreSQL (production), SQLite (dev)
**Virtual env:** `.venvKasu`
**Language:** Spanish (es-mx), all model names, comments, and UI in Spanish

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
└── almacen/

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
- `signals.py` - Auto-update logic (combustible, taller, almacen only)

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

### Status Workflows

**combustible:** INICIADO → EN_PROCESO → COMPLETADO / CANCELADO

**taller:** PENDIENTE → EN_DIAGNOSTICO → ESPERANDO_PIEZAS → EN_REPARACION → EN_PRUEBAS → COMPLETADA / CANCELADA

**compras/requisicion:** PENDIENTE → APROBADA → EN_COMPRA → COMPLETADA / RECHAZADA / CANCELADA

**compras/orden:** PENDIENTE → ENVIADA → CONFIRMADA → EN_TRANSITO → RECIBIDA / CANCELADA

**almacen/solicitud:** PENDIENTE → AUTORIZADA → PROCESADA / RECHAZADA / CANCELADA

### Context Processors
`config/context_processors.py`: Injects `alertas_combustible_pendientes` count into every template for superusers.

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
```

## Production Deployment

- **WSGI:** `gunicorn config.wsgi` (Procfile)
- **Static files:** WhiteNoise (`CompressedManifestStaticFilesStorage`)
- **Media:** DigitalOcean Spaces (SFO3)
- **Email:** SendGrid SMTP backend
- **Database:** PostgreSQL via `DBURL`
