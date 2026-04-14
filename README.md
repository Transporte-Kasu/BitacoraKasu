# BitacoraKasu — Sistema de Gestión de Transporte

Sistema integral de gestión para empresas de transporte mexicanas. Administra operadores, vehículos, bitácoras de viaje, carga de combustible, taller mecánico, compras, almacén y reportes programados — con inteligencia artificial integrada para detección de anomalías.

## Módulos del Sistema

| Módulo | URL | Descripción |
|--------|-----|-------------|
| Operadores | `/operadores/` | Gestión de conductores |
| Unidades | `/unidades/` | Control de vehículos |
| Bitácoras | `/bitacoras/` | Registro de viajes con Google Maps |
| Combustible | `/combustible/` | Control de cargas de diesel + IAKasu |
| Taller | `/taller/` | Órdenes de trabajo, mantenimiento y reportes QR |
| Compras | `/compras/` | Requisiciones y órdenes de compra |
| Almacén | `/almacen/` | Inventario y control de materiales |
| Reportes | `/reportes/` | Reportes programados por email |

## Requisitos

- Python 3.12+
- Django 5.2.7
- PostgreSQL (producción) / SQLite (desarrollo)
- API Key de Google Maps Distance Matrix
- API Key de Anthropic Claude (para IAKasu — opcional)
- Google Cloud Vision API Key (para OCR de candados — opcional)

## Instalación

### 1. Clonar el repositorio

```bash
git clone <repository-url>
cd BitacoraKasu
```

### 2. Crear y activar entorno virtual

```bash
python -m venv .venvBitacoraKasu
source .venvBitacoraKasu/bin/activate  # Windows: .venvBitacoraKasu\Scripts\activate
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

# Email (SendGrid)
EMAIL_HOST_PASSWORD=

# IAKasu — Inteligencia Artificial (opcional)
ANTHROPIC_API_KEY=
IA_HABILITADA=True
IA_SCORE_MINIMO_CLAUDE=ALTO
IA_ALERTAS_COMBUSTIBLE_EMAILS=gerencia@empresa.com,responsable@empresa.com

# OCR de candados (Google Cloud Vision, opcional)
GOOGLE_VISION_API_KEY=
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
│       ├── google_maps.py      # Integración Google Maps Distance Matrix
│       ├── claude_service.py   # Cliente Anthropic Claude (IAKasu)
│       └── ocr_service.py      # OCR de candados (Google Cloud Vision)
│
├── modulos/
│   ├── operadores/             # Gestión de conductores
│   ├── unidades/               # Control de vehículos
│   ├── bitacoras/              # Registro de viajes
│   ├── combustible/            # Cargas de combustible + IAKasu
│   │   ├── ia_service.py       # AnalizadorCombustible (detección estadística)
│   │   └── notificaciones.py   # Emails de alertas IA
│   ├── taller/                 # Taller mecánico + reportes de falla QR
│   ├── compras/                # Compras y proveedores
│   ├── almacen/                # Inventario y almacén
│   └── reportes/               # Reportes programados por email
│       └── generadores/        # Generadores de almacen.py y combustible.py
│
├── templates/                  # 98 templates HTML
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
Control de cargas de diesel con proceso de verificación de candados y análisis de anomalías por IA.

**Flujo de carga:**
```
INICIADO → EN_PROCESO → COMPLETADO
```

- Wizard de 6 pasos con captura fotográfica
- Registro de: despachador, unidad, litros, kilometraje, nivel inicial/final
- Verificación de estado de candado (NORMAL, ALTERADO, VIOLADO, SIN_CANDADO)
- OCR automático de número de candado (Google Cloud Vision + pytesseract)
- Alertas de control automáticas al detectar candado alterado o violado
- **IAKasu**: detección estadística de anomalías en cada carga completada
- Gestión de alertas con resolución supervisada (superusuarios)

### IAKasu — Inteligencia Artificial para Combustible

Sistema de detección de anomalías en dos capas:

**Capa 1 — Análisis estadístico (siempre activo, sin costo):**
- Consumo atípico de litros (z-score vs. histórico de la unidad)
- Rendimiento anómalo km/lt fuera de rango esperado
- Tiempo de carga inusual respecto al promedio
- Nivel de combustible inconsistente (salto imposible)
- Patrón de concentración de alertas por despachador

**Capa 2 — Interpretación con Claude Sonnet (solo ALTO/CRÍTICO):**
- Generación de explicación en lenguaje natural del hallazgo
- Prompt caching para reducir costos de API
- Envío de email a responsables con análisis completo

**Score de riesgo:** BAJO → MEDIO → ALTO → CRÍTICO

**URLs IAKasu:**
- `/combustible/ia/` — Dashboard con gráficas (Chart.js), KPIs, tabla de unidades en riesgo
- `/combustible/alertas/?fuente=ia` — Listado filtrado de alertas IA

**Variables de entorno relevantes:**
```env
ANTHROPIC_API_KEY=sk-ant-...       # Claude API key
IA_HABILITADA=True                 # Activar/desactivar análisis IA
IA_SCORE_MINIMO_CLAUDE=ALTO        # Score mínimo para llamar a Claude
IA_ALERTAS_COMBUSTIBLE_EMAILS=...  # Destinatarios de alertas por email
```

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
- **Reportes de Falla vía QR**: los operadores escanean un código QR impreso en la unidad y reportan fallas desde su celular sin necesidad de cuenta
  - Folio autogenerado: `RF-YYYYMMDD-XXX`
  - Vista pública (sin login): `/taller/reportar/<unidad_pk>/`
  - QR imprimible por unidad: `/taller/unidades/<unidad_pk>/qr/`
  - Bandeja de taller: `/taller/reportes/`
  - Resolución directa o conversión a Orden de Trabajo

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
Inventario completo con control de entradas, salidas y alertas de stock.

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

### Reportes
Reportes programados enviados por email a destinatarios configurables.

- Tipos: reporte de almacén y reporte de combustible
- Frecuencias configurables (diario, semanal, mensual)
- Historial de reportes generados con resumen en JSONField
- Envío HTML por SendGrid con plantilla responsive

## Comandos de Gestión

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

# Generar reportes programados
python manage.py generar_reportes
python manage.py generar_reportes --forzar-id 1   # forzar un reporte específico
python manage.py generar_reportes --dry-run        # simular sin enviar

# Reprocesar OCR de candados
python manage.py reprocesar_ocr_candados

# Importar datos iniciales
python manage.py load_unidades
python manage.py load_operadores
python manage.py cargar_productos_csv
python manage.py generar_checklist_default
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

### Anthropic Claude API (IAKasu)
Interpreta anomalías estadísticas en lenguaje natural para alertas ALTO y CRÍTICO.

```python
from config.services.claude_service import ClaudeService, Modelo

claude = ClaudeService()
respuesta = claude.completar(
    prompt='Analiza esta anomalía...',
    sistema='Eres un analista de combustible...',
    modelo=Modelo.SONNET,
)
```

- Usa prompt caching (`cache_control: ephemeral`) para reducir costos
- Se desactiva automáticamente si `IA_HABILITADA=False` o sin API key

### OCR de Candados
Lectura automática del número de candado en fotografías usando Google Cloud Vision API con fallback a pytesseract.

```python
from config.services.ocr_service import OCRService

ocr = OCRService()
numero = ocr.leer_numero_candado(imagen_path)
```

### Almacenamiento en la Nube
DigitalOcean Spaces (S3-compatible) para archivos en producción. Activar con `USE_SPACES=True` en `.env`.
- URLs firmadas con expiración de 1 hora para archivos privados
- Organización por fecha: `/YYYY/MM/`
- CDN habilitado para archivos estáticos

### Email
SendGrid SMTP para notificaciones del sistema:
- Alertas de candado alterado/violado
- Alertas IAKasu (ALTO/CRÍTICO) con análisis de Claude
- Reportes programados de almacén y combustible

## Producción

```
Procfile: web: gunicorn config.wsgi
```

- Static files: WhiteNoise con compresión
- Media: DigitalOcean Spaces (región SFO3)
- Base de datos: PostgreSQL via variable `DBURL`
- Reportes programados: cron via GitHub Actions o DigitalOcean Scheduler

## Dependencias Principales

```
Django==5.2.7
psycopg2-binary==2.9.11      # PostgreSQL
anthropic==0.94.1            # Claude API (IAKasu)
google-cloud-vision          # OCR de candados
pytesseract                  # OCR fallback
django-storages==1.14.6      # DigitalOcean Spaces
pillow==12.0.0               # Procesamiento de imágenes
requests==2.32.5             # HTTP (Google Maps)
whitenoise                   # Static files producción
gunicorn                     # WSGI server
```

## Notas Importantes

- Código postal origen por defecto: **40812**
- Todo el sistema en español (es-mx, America/Mexico_City)
- Sistema de medidas métrico (km, litros, kg)
- Todas las vistas requieren autenticación (excepto reporte de falla QR)
- El análisis IAKasu es **no bloqueante**: nunca interrumpe el guardado de una carga
- Para el módulo de reportes programados, ejecutar el management command desde cron con el virtualenv correcto: `.venvBitacoraKasu/bin/python manage.py generar_reportes`

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Transporte-Kasu/BitacoraKasu)

## Licencia

Proyecto privado y confidencial.
