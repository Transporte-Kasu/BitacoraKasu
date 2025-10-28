# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

**ProyectoKasu** is a Django 5.2.7 transportation management system for tracking delivery trips, vehicles, and operators. The system integrates with Google Maps Distance Matrix API for route calculations and fuel efficiency monitoring.

### Core Domain

The application manages three primary entities:
- **Operadores** (Operators): Drivers with types LOCAL, FORANEO, ESPERANZA
- **Unidades** (Units/Vehicles): Fleet vehicles with fuel tracking and maintenance schedules
- **Bitácoras de Viaje** (Trip Logs): Detailed trip records with fuel consumption, distance, and performance metrics

## Development Environment

### Virtual Environment
```bash
source .venv_bitaKasu/bin/activate
```

### Database
- **Development**: SQLite (db.sqlite3)
- **Production ready**: PostgreSQL configured via .env (currently not active)
- Database settings in `config/settings.py`

### Environment Variables
Located in `.env` file:
- `DEBUG`: Development mode flag
- `SECRET_KEY`: Django secret key
- `DATABASE_*`: PostgreSQL credentials (not currently in use)
- `GOOGLE_MAPS_API_KEY`: Required for distance calculations

## Common Commands

### Run Development Server
```bash
python manage.py runserver
```

### Database Management
```bash
# Create migrations after model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser for admin access
python manage.py createsuperuser
```

### Django Shell
```bash
# Interactive Python shell with Django context
python manage.py shell
```

### Testing
```bash
# Run all tests
python manage.py test

# Run tests for specific app
python manage.py test apps.operadores
python manage.py test apps.unidades
python manage.py test apps.bitacoras
```

## Project Architecture

### Settings Module Location
- Main settings: `config/settings.py`
- DJANGO_SETTINGS_MODULE: `config.settings`
- Language: Spanish (es-mx)
- Timezone: America/Mexico_City

### Apps Structure (`apps/` directory)

All Django apps use a modular structure under the `apps/` directory:

#### 1. **operadores** - Operator Management
- Model: `Operador` with types (LOCAL, FORANEO, ESPERANZA)
- Tracks operator assignments to vehicles (ForeignKey to `unidades.Unidad`)
- Methods for calculating work hours, trip counts, and fuel efficiency
- Fields: nombre, tipo, unidad_asignada, licencia, telefono, email, activo, fecha_ingreso/baja

#### 2. **unidades** - Vehicle/Fleet Management  
- Model: `Unidad` with vehicle specifications
- Tracks capacity, fuel efficiency, maintenance schedules
- Fields: numero_economico (unique), placa, tipo, marca, modelo, año, capacidad_combustible, rendimiento_esperado, kilometraje_actual
- Methods: `rendimiento_promedio_real()`, `eficiencia_combustible()`, `requiere_mantenimiento()`

#### 3. **bitacoras** - Trip Logging & Tracking
- Model: `BitacoraViaje` - comprehensive trip records
- ForeignKeys to both `Operador` and `Unidad` (PROTECT on delete)
- Fields: modalidad (SENCILLO/FULL), contenedor, peso, diesel_cargado, kilometraje_salida/llegada, cp_origen/destino
- Google Maps integration fields: distancia_calculada, duracion_estimada
- Computed properties: `kilometros_recorridos`, `rendimiento_combustible`, `horas_viaje`, `velocidad_promedio`, `eficiencia_vs_esperado`
- Method: `calcular_distancia_google()` - integrates with GoogleMapsService

### Services Layer (`config/services/`)

#### GoogleMapsService (`config/services/google_maps.py`)
- Handles Google Distance Matrix API integration
- Methods:
  - `calcular_distancia(cp_origen, cp_destino)` - single route calculation
  - `batch_calcular_distancias(lista_destinos, cp_origen)` - multiple routes
  - `validar_codigo_postal(cp, pais)` - postal code validation
- Used by BitacoraViaje model for automatic distance calculation

### Cross-App Relationships

Models use string references for cross-app ForeignKeys:
```python
# In operadores/models.py
unidad_asignada = models.ForeignKey('unidades.Unidad', ...)

# In bitacoras/models.py  
operador = models.ForeignKey('operadores.Operador', ...)
unidad = models.ForeignKey('unidades.Unidad', ...)
```

### Related Names Convention
- `Unidad.operadores` → all operators assigned to this vehicle
- `Unidad.bitacoras` → all trips for this vehicle
- `Operador.bitacoras` → all trips by this operator

## Model Patterns & Business Logic

### Calculated Properties Pattern
Models use `@property` decorators for computed values rather than storing redundant data:
- BitacoraViaje: `kilometros_recorridos`, `rendimiento_combustible`, `horas_viaje`, `velocidad_promedio`
- Never store these as database fields

### Custom Save() Override
`BitacoraViaje.save()` includes:
- Validation: fecha_llegada > fecha_salida, kilometraje_llegada > kilometraje_salida
- Auto-completion: Sets `completado=True` when `fecha_llegada` is set
- Cascading updates: Updates `Unidad.kilometraje_actual` when trip completes

### Performance Monitoring
Key thresholds:
- Low fuel efficiency alert: < 2.5 km/lt (see `alerta_bajo_rendimiento` property)
- Default origin postal code: 40812

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

## Admin Interface

Admin models are currently unregistered (empty admin.py files). To register models:
```python
from django.contrib import admin
from .models import ModelName

@admin.register(ModelName)
class ModelNameAdmin(admin.ModelAdmin):
    list_display = ['field1', 'field2']
    list_filter = ['field3']
    search_fields = ['field4']
```

## External API Integration

### Google Maps API
- Required for distance/duration calculations
- Set `GOOGLE_MAPS_API_KEY` in .env
- Service class: `config.services.google_maps.GoogleMapsService`
- Usage: Call `bitacora.calcular_distancia_google()` after creating trip record
- Rate limits and quotas apply - implement caching for production

## Common Development Patterns

### Creating New Apps
```bash
python manage.py startapp nombre_app apps/nombre_app
```

Then add to `INSTALLED_APPS` in config/settings.py:
```python
INSTALLED_APPS = [
    # ...
    'apps.nombre_app',
]
```

### Model Method Naming Conventions
- Calculations returning single values: `calcular_*()`, `rendimiento_*()`, `promedio_*()`
- Boolean checks: `requiere_*()`, `alerta_*()` (as properties)
- Counters: `*_completados()`, `viajes_*()`, `horas_*_periodo()`

### Date/Time Fields
- Always use `auto_now_add=True` for `created_at`
- Always use `auto_now=True` for `updated_at`
- Use timezone-aware datetimes (settings has `USE_TZ = True`)

## Data Validation

### Validators in Use
- `MinValueValidator(0)` - for kilometraje, peso, diesel_cargado
- `MinValueValidator(1990), MaxValueValidator(2030)` - for vehicle año
- Email validation - via `EmailField`

### Custom Validation
Implement in model's `save()` method or use `clean()` method for form validation.

## Important Notes

- All apps follow Spanish naming conventions (operadores, unidades, bitácoras)
- UI language is Spanish (LANGUAGE_CODE = 'es-mx')
- Default postal code origin: 40812
- Currency/measurements: Mexican standards (km, liters, kg)
- Admin interface available at `/admin/`
- Currently no custom URL patterns beyond admin (see config/urls.py)
