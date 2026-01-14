# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BitacoraKasu is a Django-based fleet management system for a Mexican transport company. It tracks drivers (operadores), vehicles (unidades), trip logs (bitácoras), fuel consumption (combustible), workshop repairs (taller), purchases (compras), and warehouse inventory (almacén).

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
- `config/` - Django project settings, URLs, and services
- `modulos/` - Django apps organized by business domain
- `templates/` - HTML templates (base.html + module-specific directories)
- `static/` - CSS and JavaScript files

### Module Organization
Each module in `modulos/` follows standard Django app structure:
- `models.py` - Database models
- `views.py` - Views (mostly class-based with LoginRequiredMixin)
- `urls.py` - URL routing
- `forms.py` - Django forms with validation
- `admin.py` - Django admin configuration

### Core Modules
- **operadores**: Drivers (LOCAL, FORANEO, ESPERANZA types)
- **unidades**: Vehicles with fuel efficiency tracking and maintenance alerts
- **bitacoras**: Trip logs with Google Maps integration for distance calculation
- **combustible**: Fuel loading records with lock seal verification
- **taller**: Workshop orders with diagnosis and repair workflows
- **compras**: Purchase requisitions, orders, and supplier management
- **almacen**: Warehouse inventory with stock alerts and authorization flows

### Key Services
- `config/services/google_maps.py` - GoogleMapsService for distance calculation between postal codes using Distance Matrix API

### Database
Uses PostgreSQL in production (configured via `DBURL` in .env). Falls back to SQLite for development.

### File Storage
Media files use DigitalOcean Spaces (S3-compatible) when credentials are configured, otherwise local storage.

## Language and Localization

- All code comments and model verbose names are in Spanish
- Locale: es-mx
- Timezone: America/Mexico_City
- Default origin postal code: 40812

## Template System

Templates extend `base.html` which provides:
- Navigation with module links
- Message alerts (success, error, warning, info)
- CSS utility classes (.card, .grid, .btn-primary, etc.)
- JavaScript helpers (formatMXN, formatDate, showNotification)

Available blocks: `title`, `extra_css`, `breadcrumb`, `content`, `extra_js`

## Authentication

All views require login via `LoginRequiredMixin`. The admin panel is at `/admin/`.

## Key Patterns

### Model Save Overrides
BitacoraViaje.save() automatically:
- Validates dates and kilometraje consistency
- Sets completado=True when fecha_llegada is provided
- Updates the vehicle's kilometraje_actual

### Django Signals
The almacen module uses signals to:
- Update stock when items are added/removed
- Generate stock alerts automatically

### Folio Generation
Almacen models auto-generate folios: ENT-YYYYMMDD-XXX, SOL-YYYYMMDD-XXX, SAL-YYYYMMDD-XXX
