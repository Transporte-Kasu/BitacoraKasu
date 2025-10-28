# ProyectoKasu - Sistema de Gestión de Transporte

Sistema de gestión para empresas de transporte que permite administrar operadores, unidades vehiculares y bitácoras de viaje con integración a Google Maps para cálculo automático de distancias y duraciones.

## 🚀 Características

- **Gestión de Operadores**: Administración de conductores (Local, Foráneo, Esperanza)
- **Control de Unidades**: Seguimiento de vehículos con monitoreo de combustible y mantenimiento
- **Bitácoras de Viaje**: Registro detallado de viajes con métricas de rendimiento
- **Integración Google Maps**: Cálculo automático de distancias y tiempos estimados
- **Análisis de Rendimiento**: Monitoreo de eficiencia de combustible y alertas
- **Panel de Administración**: Interface administrativa completa de Django

## 📋 Requisitos

- Python 3.12+
- Django 5.2.7
- PostgreSQL (configurado para producción)
- API Key de Google Maps Distance Matrix

## 🛠️ Instalación

### 1. Clonar el repositorio

```bash
git clone <repository-url>
cd ProyectoKasu/django
```

### 2. Crear y activar entorno virtual

```bash
python -m venv .venv_bitaKasu
source .venv_bitaKasu/bin/activate  # En Windows: .venv_bitaKasu\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Crear archivo `.env` en la raíz del proyecto:

```env
DEBUG=True
SECRET_KEY='tu-secret-key-aqui'
DATABASE_NAME=transportes_kasu_db
DATABASE_USER=postgres
DATABASE_PASSWORD=tu_password
DATABASE_HOST=localhost
DATABASE_PORT=5432
GOOGLE_MAPS_API_KEY='tu-api-key-de-google-maps'
```

### 5. Ejecutar migraciones

```bash
python manage.py migrate
```

### 6. Crear superusuario

```bash
python manage.py createsuperuser
```

### 7. Iniciar servidor de desarrollo

```bash
python manage.py runserver
```

El sistema estará disponible en `http://localhost:8000`

## 📁 Estructura del Proyecto

```
django/
├── apps/
│   ├── operadores/        # Gestión de conductores
│   ├── unidades/          # Gestión de vehículos
│   └── bitacoras/         # Registro de viajes
├── config/
│   ├── services/
│   │   └── google_maps.py # Integración con Google Maps API
│   ├── settings.py        # Configuración principal
│   └── urls.py           # Rutas URL
├── manage.py
├── requirements.txt
└── .env
```

## 🎯 Modelos Principales

### Operador
Gestiona información de conductores:
- Información personal (nombre, licencia, teléfono, email)
- Tipo de operador (Local, Foráneo, Esperanza)
- Asignación de unidad
- Métricas de desempeño

### Unidad
Control de vehículos:
- Identificación (número económico, placas)
- Especificaciones técnicas (marca, modelo, año)
- Capacidad y rendimiento de combustible
- Kilometraje y mantenimiento

### BitacoraViaje
Registro detallado de viajes:
- Información del viaje (operador, unidad, modalidad)
- Fechas y horarios (carga, salida, llegada)
- Combustible y kilometraje
- Ubicaciones (códigos postales origen/destino)
- Métricas calculadas automáticamente:
  - Kilómetros recorridos
  - Rendimiento de combustible
  - Horas de viaje
  - Velocidad promedio
  - Eficiencia vs. esperado

## 🗺️ Integración con Google Maps

El sistema utiliza Google Maps Distance Matrix API para:

```python
# Calcular distancia entre códigos postales
from config.services.google_maps import GoogleMapsService

maps = GoogleMapsService()
resultado = maps.calcular_distancia('40812', '06600')

# O directamente desde una bitácora
bitacora = BitacoraViaje.objects.get(id=1)
resultado = bitacora.calcular_distancia_google()
```

## 💡 Uso Común

### Crear un viaje

```python
from apps.operadores.models import Operador
from apps.unidades.models import Unidad
from apps.bitacoras.models import BitacoraViaje
from django.utils import timezone

# Crear bitácora de viaje
viaje = BitacoraViaje.objects.create(
    operador=operador,
    unidad=unidad,
    modalidad='SENCILLO',
    fecha_carga=timezone.now(),
    fecha_salida=timezone.now(),
    diesel_cargado=150.00,
    kilometraje_salida=45000,
    cp_origen='40812',
    cp_destino='06600',
    destino='Ciudad de México'
)

# Calcular distancia con Google Maps
viaje.calcular_distancia_google()
```

### Consultar métricas

```python
# Rendimiento promedio de una unidad
unidad = Unidad.objects.get(numero_economico='U001')
print(f"Rendimiento: {unidad.rendimiento_promedio_real()} km/lt")
print(f"Eficiencia: {unidad.eficiencia_combustible()}%")

# Viajes de un operador
operador = Operador.objects.get(id=1)
print(f"Viajes completados: {operador.viajes_completados()}")
print(f"Horas trabajadas: {operador.horas_trabajadas_periodo(fecha_inicio, fecha_fin)}")
```

## 🔧 Comandos de Desarrollo

```bash
# Ejecutar pruebas
python manage.py test

# Crear migraciones
python manage.py makemigrations

# Aplicar migraciones
python manage.py migrate

# Shell interactivo
python manage.py shell

# Crear app nueva
python manage.py startapp nombre_app apps/nombre_app
```

## 📊 Panel de Administración

Acceder a `http://localhost:8000/admin/` con las credenciales de superusuario para:
- Gestionar operadores, unidades y viajes
- Ver reportes y métricas
- Administrar usuarios del sistema

## ⚙️ Configuración

### Base de Datos

El proyecto está configurado para usar:
- **Desarrollo**: SQLite (por defecto)
- **Producción**: PostgreSQL (configurar en .env)

Para cambiar a PostgreSQL, modificar `config/settings.py`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DATABASE_NAME'),
        'USER': os.environ.get('DATABASE_USER'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD'),
        'HOST': os.environ.get('DATABASE_HOST'),
        'PORT': os.environ.get('DATABASE_PORT'),
    }
}
```

### Zona Horaria y Localización

- **Idioma**: Español (México)
- **Zona horaria**: America/Mexico_City
- **Formato de fechas**: Formato mexicano

## 🚨 Alertas y Monitoreo

El sistema incluye alertas automáticas:

- **Bajo rendimiento**: < 2.5 km/lt
- **Mantenimiento requerido**: Basado en fecha de próximo mantenimiento
- **Validación de kilometraje**: Detecta inconsistencias en registros

## 📝 Notas Importantes

- Código postal origen por defecto: **40812**
- Medidas en sistema métrico (km, litros, kg)
- Toda la interfaz y nomenclatura en español
- Validaciones automáticas en guardado de bitácoras
- Actualización automática de kilometraje de unidades

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto es privado y confidencial.

## 👥 Contacto

Para soporte o consultas sobre el proyecto, contactar al equipo de desarrollo.
