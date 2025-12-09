# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

**ProyectoKasu** is a Django 5.2.7 transportation management system for tracking delivery trips, vehicles, and operators. The system integrates with Google Maps Distance Matrix API for route calculations and fuel efficiency monitoring.

### Core Domain

The application manages three primary entities:
- **Operadores** (Operators): Drivers with types LOCAL, FORANEO, ESPERANZA
- **Unidades** (Units/Vehicles): Fleet vehicles with fuel tracking and maintenance schedules
- **Bitácoras de Viaje** (Trip Logs): Detailed trip records with fuel consumption, distance, and performance metrics

### Language & Localization
- All code, models, and UI use Spanish naming conventions
- LANGUAGE_CODE: es-mx
- TIME_ZONE: America/Mexico_City
- Measurements: Mexican standards (km, liters, kg)
- Default origin postal code: 40812

## Development Environment

### Virtual Environment
```bash
source .venvKasu/bin/activate
```

### Database
- **Development**: SQLite (db.sqlite3)
- **Production ready**: PostgreSQL configured via .env (currently not active)
- Database settings in `config/settings.py`

### Environment Variables (.env)
- `DEBUG`: Development mode flag
- `SECRET_KEY`: Django secret key
- `DATABASE_*`: PostgreSQL credentials (not currently in use)
- `GOOGLE_MAPS_API_KEY`: **Required** for distance calculations via GoogleMapsService

## Common Commands

### Development Server
```bash
python manage.py runserver  # Starts on http://localhost:8000
```

### Database Management
```bash
python manage.py makemigrations      # Create migrations after model changes
python manage.py migrate             # Apply migrations
python manage.py createsuperuser     # Create admin user
python manage.py shell               # Interactive Python shell with Django context
```

### Testing
```bash
python manage.py test                    # Run all tests
python manage.py test apps.operadores    # Test specific app
python manage.py test apps.operadores.tests.OperadorModelTest  # Test specific class
```

Note: Test files currently contain boilerplate only (`from django.test import TestCase`)

## Project Architecture

### Settings & Configuration
- Main settings: `config/settings.py`
- DJANGO_SETTINGS_MODULE: `config.settings`
- Static files: `static/` → collected to `staticfiles/`
- Media files: `media/`
- Templates: `templates/` (base directory)

### Apps Structure (`apps/` directory)

All Django apps use a modular structure under the `apps/` directory:

#### 1. **operadores** - Operator Management
- **Model**: `Operador` with types (LOCAL, FORANEO, ESPERANZA)
- **Key Fields**: nombre, tipo, unidad_asignada (FK), licencia, telefono, email, activo, fecha_ingreso/baja
- **Methods**: `viajes_completados()`, `horas_trabajadas_periodo()`, `rendimiento_promedio()`
- **Views**: CRUD operations + dashboard with statistics and search/filter
- **Forms**: `OperadorForm` with validations (phone format, active/inactive state logic)
- **URLs**: `/operadores/`, `/operadores/lista/`, `/operadores/crear/`, `/operadores/<id>/`, etc.

#### 2. **unidades** - Vehicle/Fleet Management
- **Model**: `Unidad` with vehicle specifications
- **Key Fields**: numero_economico (unique), placa, tipo, marca, modelo, año, capacidad_combustible, rendimiento_esperado, kilometraje_actual
- **Methods**: `rendimiento_promedio_real()`, `eficiencia_combustible()`, `requiere_mantenimiento()`
- **Views**: CRUD operations + dashboard with maintenance alerts
- **Forms**: `UnidadForm` with validations (uppercase enforcement, year range, maintenance dates)
- **URLs**: `/unidades/`, `/unidades/lista/`, `/unidades/crear/`, `/unidades/<id>/`, etc.

#### 3. **bitacoras** - Trip Logging & Tracking
- **Model**: `BitacoraViaje` - comprehensive trip records
- **Key Fields**: operador (FK), unidad (FK), modalidad (SENCILLO/FULL), contenedor, peso, diesel_cargado, kilometraje_salida/llegada, cp_origen/destino
- **Google Maps Fields**: distancia_calculada, duracion_estimada (auto-populated)
- **Computed Properties**: `kilometros_recorridos`, `rendimiento_combustible`, `horas_viaje`, `velocidad_promedio`, `eficiencia_vs_esperado`, `alerta_bajo_rendimiento`
- **Method**: `calcular_distancia_google()` - integrates with GoogleMapsService
- **Views**: CRUD + dashboard + `completar_viaje()` + AJAX endpoint for distance calculation
- **Forms**: `BitacoraViajeForm` (creation), `BitacoraViajeCompletarForm` (completion)
- **URLs**: `/bitacoras/`, `/bitacoras/lista/`, `/bitacoras/crear/`, `/bitacoras/<id>/completar/`, `/bitacoras/<id>/calcular-distancia/`, etc.

### Services Layer (`config/services/`)

#### GoogleMapsService (`config/services/google_maps.py`)
Handles Google Distance Matrix API integration.

**Methods:**
- `calcular_distancia(cp_origen, cp_destino)` → Returns dict with `distancia_km`, `duracion_min`, formatted addresses
- `batch_calcular_distancias(lista_destinos, cp_origen='40812')` → Multiple routes from single origin
- `validar_codigo_postal(cp, pais='Mexico')` → Validates postal code existence

**Usage:**
```python
from config.services.google_maps import GoogleMapsService
maps = GoogleMapsService()  # Reads GOOGLE_MAPS_API_KEY from environment
result = maps.calcular_distancia('40812', '06600')
# Or directly from BitacoraViaje instance:
bitacora.calcular_distancia_google()
```

**Important**: Service returns `{'success': False, 'error': '...'}` on failures. Always check `success` key.

### Cross-App Relationships

Models use string references for cross-app ForeignKeys to avoid circular imports:
```python
# In operadores/models.py
unidad_asignada = models.ForeignKey('unidades.Unidad', on_delete=models.SET_NULL, null=True, related_name='operadores')

# In bitacoras/models.py
operador = models.ForeignKey('operadores.Operador', on_delete=models.PROTECT, related_name='bitacoras')
unidad = models.ForeignKey('unidades.Unidad', on_delete=models.PROTECT, related_name='bitacoras')
```

**Related Names:**
- `Unidad.operadores` → QuerySet of all operators assigned to this vehicle
- `Unidad.bitacoras` → QuerySet of all trips for this vehicle
- `Operador.bitacoras` → QuerySet of all trips by this operator

**Delete Behaviors:**
- BitacoraViaje uses `PROTECT` to prevent deletion of Operador/Unidad with trips
- Operador uses `SET_NULL` for unidad_asignada (operators can exist without vehicles)

## Model Patterns & Business Logic

### Calculated Properties Pattern
Models use `@property` decorators for computed values rather than storing redundant data:
- **BitacoraViaje**: `kilometros_recorridos`, `rendimiento_combustible`, `horas_viaje`, `velocidad_promedio`, `eficiencia_vs_esperado`, `diferencia_distancias`, `alerta_bajo_rendimiento`
- **Unidad**: `rendimiento_promedio_real()`, `eficiencia_combustible()`
- **Important**: Never store these as database fields - they're computed on-the-fly

### Custom Save() Override
**`BitacoraViaje.save()`** includes critical business logic:
1. **Validation**: fecha_llegada > fecha_salida, kilometraje_llegada > kilometraje_salida
2. **Auto-completion**: Sets `completado=True` when `fecha_llegada` is provided
3. **Cascading updates**: Updates `Unidad.kilometraje_actual` to `kilometraje_llegada` when trip completes
4. Raises `ValidationError` on invalid data

**When modifying**: Always call `super().save()` and preserve validation logic

### Performance Monitoring Thresholds
- **Low fuel efficiency alert**: < 2.5 km/lt (see `alerta_bajo_rendimiento` property)
- **Default origin postal code**: 40812
- Maintenance alerts based on `proximo_mantenimiento` date

## Database Indexes

All models define strategic indexes:
```python
indexes = [
    models.Index(fields=['tipo', 'activo']),  # Common filtering
    models.Index(fields=['-fecha_salida']),   # Recent trips
    models.Index(fields=['operador', 'fecha_salida']),
    models.Index(fields=['completado']),
]
```

When adding new filtering patterns, add corresponding indexes.

## Views & URL Patterns

All apps use Class-Based Views (CBVs) with `LoginRequiredMixin` for authentication.

### View Architecture
- **List views**: Paginated (20 items), with search and filters using query parameters
- **Detail views**: Use `select_related()` for FK optimization, display related objects
- **Create/Update views**: Use custom Form classes with validation, success messages via Django messages framework
- **Delete views**: Confirmation pages with PROTECT enforcement from ForeignKey constraints
- **Dashboards**: Functional views with aggregated statistics using annotations

### URL Structure
```
/                                   → Index page
/admin/                             → Django Admin (models currently unregistered)
/operadores/                        → Dashboard
/operadores/lista/                  → List with ?search=, ?tipo=, ?activo= filters
/operadores/crear/                  → Create form
/operadores/<id>/                   → Detail view
/operadores/<id>/editar/            → Update form
/operadores/<id>/eliminar/          → Delete confirmation
# Same pattern for /unidades/ and /bitacoras/
/bitacoras/<id>/completar/          → Special form to complete trip (set fecha_llegada, kilometraje_llegada)
/bitacoras/<id>/calcular-distancia/ → AJAX POST endpoint for Google Maps integration
```

### Query Optimization Patterns
```python
# Always use select_related for ForeignKeys in list views
BitacoraViaje.objects.select_related('operador', 'unidad')
Operador.objects.select_related('unidad_asignada')

# Use annotate for aggregate counts
.annotate(total_viajes=Count('bitacoras'))
```

## Forms & Validation

All forms inherit from `forms.ModelForm` with custom `clean()` methods.

### Key Validation Rules
**OperadorForm**:
- Phone must have at least 10 digits
- Inactive operators require `fecha_baja`
- Active operators cannot have `fecha_baja`

**UnidadForm**:
- `numero_economico` and `placa` auto-uppercased
- `año` must be between 1990 and current year + 1
- `proximo_mantenimiento` must be after `ultimo_mantenimiento`
- Inactive units require `fecha_baja`

**BitacoraViajeForm**:
- `fecha_salida` must be after `fecha_carga`
- `kilometraje_salida` must be >= unit's current `kilometraje_actual`

**BitacoraViajeCompletarForm**:
- `fecha_llegada` must be after trip's `fecha_salida`
- `kilometraje_llegada` must be > `kilometraje_salida`
- Both fields required together

## External API Integration

### Google Maps Distance Matrix API
- **Required**: Set `GOOGLE_MAPS_API_KEY` in .env
- **Service class**: `config.services.google_maps.GoogleMapsService`
- **Auto-trigger**: BitacoraCreateView automatically calls `calcular_distancia_google()` if `cp_destino` is provided
- **Manual recalculation**: POST to `/bitacoras/<id>/calcular-distancia/` (AJAX endpoint)
- **Rate limits**: Google API quotas apply - consider implementing caching for production
- **Timeout**: Requests timeout after 10 seconds

## Common Development Patterns

### Creating New Apps
```bash
python manage.py startapp nombre_app apps/nombre_app
```
Then add `'apps.nombre_app'` to `INSTALLED_APPS` in `config/settings.py`

### Model Method Naming Conventions
- **Calculations**: `calcular_*()`, `rendimiento_*()`, `promedio_*()`
- **Boolean checks**: `requiere_*()`, `alerta_*()` (as `@property`)
- **Counters**: `*_completados()`, `viajes_*()`, `horas_*_periodo()`
- **Properties vs Methods**: Use `@property` for cheap computations without arguments, methods for expensive/parameterized ones

### Date/Time Fields
- Use `auto_now_add=True` for creation timestamps (`created_at`)
- Use `auto_now=True` for modification timestamps (`updated_at`)
- All datetimes are timezone-aware (`USE_TZ = True`)

### Model Validators
- `MinValueValidator(0)` - for kilometraje, peso, diesel_cargado
- `MinValueValidator(1990), MaxValueValidator(2030)` - for vehicle año
- Complex validation goes in `save()` method or Form's `clean()` method

## Working with Existing Code

### When Modifying Models
1. Update model class
2. Run `python manage.py makemigrations`
3. Review generated migration
4. Run `python manage.py migrate`
5. Update related forms if fields changed
6. Update admin.py if display fields changed

### When Adding Features
1. Models first (if needed)
2. Forms with validation
3. Views (prefer CBVs for CRUD, functions for complex logic)
4. URL patterns in app's `urls.py`
5. Templates (not yet implemented - see VIEWS_URLS_README.md for required templates)
6. Update tests

### Current State
- ✅ Models, migrations, business logic complete
- ✅ Views, forms, URL routing complete
- ✅ Google Maps service integration complete
- ⏳ Templates not yet implemented (see required list in VIEWS_URLS_README.md)
- ⏳ Admin interface not registered (empty admin.py files)
- ⏳ Tests files are boilerplate only
