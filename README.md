# BitacoraKasu - Sistema de Gestión de Transporte

Sistema integral de gestión para empresas de transporte mexicanas. Administra operadores, vehículos, bitácoras de viaje, carga de combustible, taller mecánico, compras y almacén en una sola plataforma.

## Módulos del Sistema

| Módulo | URL | Descripción |
|--------|-----|-------------|
| Operadores | `/operadores/` | Gestión de conductores |
| Unidades | `/unidades/` | Control de vehículos |
| Bitácoras | `/bitacoras/` | Registro de viajes |
| Combustible | `/combustible/` | Control de cargas de diesel |
| Taller | `/taller/` | Órdenes de trabajo y mantenimiento |
| Compras | `/compras/` | Requisiciones y órdenes de compra |
| Almacén | `/almacen/` | Inventario y control de materiales |

## Requisitos

- Python 3.12+
- Django 5.2.7
- PostgreSQL (producción) / SQLite (desarrollo)
- API Key de Google Maps Distance Matrix

## Instalación

### 1. Clonar el repositorio

```bash
git clone <repository-url>
cd BitacoraKasu
```

### 2. Crear y activar entorno virtual

```bash
python -m venv .venvKasu
source .venvKasu/bin/activate  # Windows: .venvKasu\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Crear archivo `.env` en la raíz del proyecto:

```env
DEBUG=True
SECRET_KEY='tu-secret-key'

# Base de datos PostgreSQL (o dejar vacío para usar SQLite)
DBURL=postgres://usuario:password@localhost:5432/bitacorakasu

# Google Maps
GOOGLE_MAPS_API_KEY='tu-api-key'

# Almacenamiento DigitalOcean Spaces (opcional)
USE_SPACES=False
SPACES_ACCESS_KEY=
SPACES_SECRET_KEY=
SPACES_BUCKET_NAME=
SPACES_REGION=sfo3
SPACES_CDN_ENDPOINT=

# Email (SendGrid, opcional)
EMAIL_HOST_PASSWORD=
```

### 5. Aplicar migraciones

```bash
python manage.py migrate
```

### 6. Crear superusuario

```bash
python manage.py createsuperuser
```

### 7. Iniciar servidor

```bash
python manage.py runserver
```

Sistema disponible en `http://localhost:8000`

## Estructura del Proyecto

```
BitacoraKasu/
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── views.py                # Dashboard principal (IndexView)
│   ├── context_processors.py   # Alertas de combustible en contexto global
│   ├── storage_backends.py     # Almacenamiento S3 / local
│   └── services/
│       └── google_maps.py      # Integración Google Maps Distance Matrix
│
├── modulos/
│   ├── operadores/             # Gestión de conductores
│   ├── unidades/               # Control de vehículos
│   ├── bitacoras/              # Registro de viajes
│   ├── combustible/            # Cargas de combustible
│   ├── taller/                 # Taller mecánico
│   ├── compras/                # Compras y proveedores
│   └── almacen/                # Inventario y almacén
│
├── templates/                  # 79 templates HTML
├── static/                     # CSS, JS, imágenes
├── media/                      # Archivos subidos (desarrollo)
├── manage.py
├── requirements.txt
└── .env
```

## Descripción de Módulos

### Operadores
Gestión de conductores con tres tipos: **LOCAL**, **FORANEO**, **ESPERANZA**.
- Información personal: nombre, licencia, teléfono, email
- Asignación a unidad vehicular
- Métricas: horas trabajadas, viajes completados, rendimiento promedio

### Unidades
Control de la flota vehicular con seguimiento de combustible y mantenimiento.
- Identificación: número económico, placas, marca, modelo, año
- Capacidad de combustible y rendimiento esperado (km/lt)
- Alertas automáticas de mantenimiento por fecha
- Historial de kilometraje actualizado automáticamente

### Bitácoras
Registro detallado de viajes con integración a Google Maps.
- Modalidades: SENCILLO, FULL
- Cálculo automático de distancia y duración via API de Google Maps
- Métricas calculadas: km recorridos, rendimiento, velocidad promedio, eficiencia
- Estado automático: se marca como completado al registrar fecha de llegada
- Actualización automática del kilometraje de la unidad

### Combustible
Control de cargas de diesel con proceso de verificación de candados (multi-paso).
- Flujo en 6 pasos con captura fotográfica
- Registro de: despachador, unidad, litros, kilometraje, nivel inicial
- Verificación de estado de candado (NORMAL, ALTERADO, VIOLADO, SIN_CANDADO)
- Alertas automáticas al detectar candado alterado o violado
- Gestión de alertas con resolución supervisada

### Taller
Gestión de órdenes de trabajo mecánico con flujo de estados completo.

**Flujo de estados:**
```
PENDIENTE → EN_DIAGNOSTICO → ESPERANDO_PIEZAS → EN_REPARACION → EN_PRUEBAS → COMPLETADA
```

- Tipos de mantenimiento: PREVENTIVO, CORRECTIVO, PREDICTIVO
- Categorías de falla con prioridad: BAJA, MEDIA, ALTA, CRITICA
- Seguimiento de piezas requeridas integrado con compras
- Generación automática de requisiciones de piezas
- Historial de mantenimiento por unidad
- Checklists configurables por tipo de mantenimiento
- Actualización automática de fechas de mantenimiento en la unidad

### Compras
Gestión del proceso de adquisiciones desde la requisición hasta la recepción.

**Flujo de requisición:**
```
PENDIENTE → APROBADA → EN_COMPRA → COMPLETADA
```

**Flujo de orden de compra:**
```
PENDIENTE → ENVIADA → CONFIRMADA → EN_TRANSITO → RECIBIDA
```

- Administración de proveedores con RFC y datos de contacto
- Catálogo de productos con unidades de medida
- Aprobación de requisiciones con control de permisos
- Recepción de material con control de cantidades aceptadas/rechazadas
- Integración con almacén para registro automático de entradas

### Almacén
Inventario completo con control de entradas, salidas, y alertas de stock.

**Tipos de entrada:** FACTURA, TALLER_REPARADO, TALLER_RECICLADO, AJUSTE

**Flujo de solicitud de salida:**
```
PENDIENTE → AUTORIZADA → PROCESADA
```

- Productos con SKU, código de barras, ubicación, lote y caducidad
- Control de stock mínimo/máximo con alertas automáticas
- Salida rápida de consumibles para unidades
- Trazabilidad completa: `MovimientoAlmacen` registra cada cambio
- Alertas de: stock mínimo, stock agotado, próximo a caducar, caducado
- Reportes: inventario general, stock crítico, productos por caducar

**Folios autogenerados:**
- Entradas: `ENT-YYYYMMDD-XXX`
- Solicitudes: `SOL-YYYYMMDD-XXX`
- Salidas: `SAL-YYYYMMDD-XXX`
- Consumibles rápidos: `CON-YYYYMMDD-XXX`

## Comandos de Desarrollo

```bash
# Servidor de desarrollo
python manage.py runserver

# Migraciones
python manage.py makemigrations
python manage.py migrate

# Pruebas (módulo específico)
python manage.py test modulos.almacen

# Shell interactivo
python manage.py shell
```

## Panel de Administración

Acceder a `http://localhost:8000/admin/` con credenciales de superusuario.

Permisos especiales disponibles:
- `aprobar_requisicion` / `procesar_compra` / `gestionar_almacen` (compras)
- `diagnosticar_orden` / `asignar_mecanico` / `aprobar_orden` / `cerrar_orden` (taller)
- `autorizar_salida_almacen` (almacén)

## Integraciones

### Google Maps Distance Matrix API
Calcula distancias y tiempos de viaje entre códigos postales automáticamente al crear bitácoras.

```python
from config.services.google_maps import GoogleMapsService

maps = GoogleMapsService()
resultado = maps.calcular_distancia('40812', '06600')
# {'success': True, 'distancia_km': 150.0, 'duracion_min': 90, ...}
```

### Almacenamiento en la Nube
DigitalOcean Spaces (S3-compatible) para archivos en producción. Activar con `USE_SPACES=True` en `.env`.

### Email
SendGrid SMTP para notificaciones del sistema.

## Producción

```
Procfile: web: gunicorn config.wsgi
```

- Static files: WhiteNoise con compresión
- Media: DigitalOcean Spaces (región SFO3)
- Base de datos: PostgreSQL via variable `DBURL`

## Notas Importantes

- Código postal origen por defecto: **40812**
- Todo el sistema en español (es-mx, America/Mexico_City)
- Sistema de medidas métrico (km, litros, kg)
- Todas las vistas requieren autenticación

## Licencia

Proyecto privado y confidencial.
