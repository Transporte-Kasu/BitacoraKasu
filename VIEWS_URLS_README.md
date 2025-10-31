# Vistas y URLs - Sistema de Gestión de Transporte

## 📋 Estructura Creada

Se han implementado vistas basadas en clases (CBV) y funcionales para las tres aplicaciones principales del sistema, con funcionalidad CRUD completa.

## 🗂️ Aplicaciones y Rutas

### 1. **Operadores** (`/operadores/`)

#### URLs Disponibles:
- `/operadores/` - Dashboard de operadores
- `/operadores/lista/` - Listado de operadores (con búsqueda y filtros)
- `/operadores/crear/` - Crear nuevo operador
- `/operadores/<id>/` - Detalle del operador
- `/operadores/<id>/editar/` - Editar operador
- `/operadores/<id>/eliminar/` - Eliminar operador

#### Vistas:
- **OperadorListView** - Lista paginada con filtros (tipo, estado, búsqueda)
- **OperadorDetailView** - Detalle con últimos viajes y estadísticas
- **OperadorCreateView** - Formulario de creación
- **OperadorUpdateView** - Formulario de edición
- **OperadorDeleteView** - Confirmación de eliminación
- **operador_dashboard()** - Dashboard con estadísticas generales

#### Características:
- Búsqueda por nombre, licencia, teléfono
- Filtrado por tipo (LOCAL, FORANEO, ESPERANZA)
- Filtrado por estado (activo/inactivo)
- Paginación de 20 elementos
- Select_related para optimizar queries
- Anotaciones con conteo de viajes

### 2. **Unidades** (`/unidades/`)

#### URLs Disponibles:
- `/unidades/` - Dashboard de unidades
- `/unidades/lista/` - Listado de unidades (con búsqueda y filtros)
- `/unidades/crear/` - Crear nueva unidad
- `/unidades/<id>/` - Detalle de la unidad
- `/unidades/<id>/editar/` - Editar unidad
- `/unidades/<id>/eliminar/` - Eliminar unidad

#### Vistas:
- **UnidadListView** - Lista paginada con filtros
- **UnidadDetailView** - Detalle con viajes, rendimiento y operadores asignados
- **UnidadCreateView** - Formulario de creación
- **UnidadUpdateView** - Formulario de edición
- **UnidadDeleteView** - Confirmación de eliminación
- **unidad_dashboard()** - Dashboard con alertas de mantenimiento

#### Características:
- Búsqueda por número económico, placa, marca, modelo
- Filtrado por tipo (LOCAL, FORANEA, ESPERANZA)
- Filtrado por estado (activa/inactiva)
- Cálculo de rendimiento promedio real
- Porcentaje de eficiencia vs esperado
- Alertas de mantenimiento requerido
- Operadores asignados a la unidad

### 3. **Bitácoras** (`/bitacoras/`)

#### URLs Disponibles:
- `/bitacoras/` - Dashboard de bitácoras
- `/bitacoras/lista/` - Listado de bitácoras (con búsqueda y filtros)
- `/bitacoras/crear/` - Crear nueva bitácora
- `/bitacoras/<id>/` - Detalle de la bitácora
- `/bitacoras/<id>/editar/` - Editar bitácora
- `/bitacoras/<id>/eliminar/` - Eliminar bitácora
- `/bitacoras/<id>/completar/` - Completar viaje
- `/bitacoras/<id>/calcular-distancia/` - Endpoint AJAX para Google Maps

#### Vistas:
- **BitacoraListView** - Lista paginada con múltiples filtros
- **BitacoraDetailView** - Detalle completo del viaje
- **BitacoraCreateView** - Formulario de creación con integración Google Maps
- **BitacoraUpdateView** - Formulario de edición
- **BitacoraDeleteView** - Confirmación de eliminación
- **completar_viaje()** - Formulario para cerrar un viaje
- **bitacora_dashboard()** - Dashboard con estadísticas de rendimiento
- **calcular_distancia_ajax()** - API para cálculo de distancias

#### Características:
- Búsqueda por contenedor, destino, operador, unidad
- Filtrado por modalidad (SENCILLO, FULL)
- Filtrado por estado (completado/en curso)
- Filtrado por operador y unidad específicos
- Integración automática con Google Maps Distance Matrix API
- Cálculo automático de:
  - Kilómetros recorridos
  - Rendimiento de combustible
  - Horas de viaje
  - Velocidad promedio
  - Eficiencia vs esperado
- Alertas de bajo rendimiento (< 2.5 km/lt)
- Actualización automática del kilometraje de unidades

## 📝 Formularios

### OperadorForm
**Campos:**
- nombre, tipo, unidad_asignada
- licencia, teléfono, email
- activo, fecha_baja, notas

**Validaciones:**
- Teléfono con al menos 10 dígitos
- Operadores inactivos deben tener fecha de baja
- Operadores activos no pueden tener fecha de baja

### UnidadForm
**Campos:**
- numero_economico, placa, tipo
- marca, modelo, año
- capacidad_combustible, rendimiento_esperado
- kilometraje_actual, activa, fecha_baja
- ultimo_mantenimiento, proximo_mantenimiento
- notas

**Validaciones:**
- Número económico y placa en mayúsculas
- Año entre 1990 y año actual + 1
- Próximo mantenimiento posterior al último
- Unidades inactivas deben tener fecha de baja

### BitacoraViajeForm
**Campos:**
- operador, unidad, modalidad
- contenedor, peso
- fecha_carga, fecha_salida
- diesel_cargado, kilometraje_salida
- cp_origen, cp_destino, destino
- sellos, reparto, observaciones

**Validaciones:**
- Fecha de salida posterior a fecha de carga
- Kilometraje de salida >= kilometraje actual de la unidad

### BitacoraViajeCompletarForm
**Campos:**
- fecha_llegada, kilometraje_llegada, observaciones

**Validaciones:**
- Fecha de llegada posterior a fecha de salida
- Kilometraje de llegada mayor al de salida
- Ambos campos requeridos juntos

## 🔐 Seguridad

Todas las vistas de clase (CBV) usan **LoginRequiredMixin** para requerir autenticación.

## 🎯 Mensajes del Sistema

Todas las vistas implementan mensajes de Django para feedback del usuario:
- **Success**: Operaciones exitosas (crear, actualizar, eliminar)
- **Error**: Errores de validación o procesamiento
- **Warning**: Avisos sobre Google Maps API

## 📊 Optimizaciones

### Select Related
Se usa `select_related()` para reducir queries:
```python
Operador.objects.select_related('unidad_asignada')
BitacoraViaje.objects.select_related('operador', 'unidad')
```

### Annotations
Se usan anotaciones para calcular datos en la base de datos:
```python
.annotate(total_viajes=Count('bitacoras'))
```

### Paginación
Todas las listas usan paginación de 20 elementos por página.

## 🗺️ Integración Google Maps

### Cálculo Automático en Creación
Al crear una bitácora, si se proporciona `cp_destino`, el sistema intenta calcular automáticamente la distancia y duración estimada usando Google Maps Distance Matrix API.

### Endpoint AJAX
`/bitacoras/<id>/calcular-distancia/` permite recalcular la distancia de una bitácora existente vía AJAX.

### Requisitos
- Variable de entorno `GOOGLE_MAPS_API_KEY` configurada
- Servicio GoogleMapsService en `config/services/google_maps.py`

## 📈 Propiedades Calculadas

Las bitácoras calculan automáticamente:
- `kilometros_recorridos` - Diferencia entre kilometraje llegada y salida
- `rendimiento_combustible` - km/litro
- `horas_viaje` - Horas totales del viaje
- `velocidad_promedio` - km/h
- `eficiencia_vs_esperado` - Porcentaje vs rendimiento esperado de la unidad
- `diferencia_distancias` - Diferencia entre Google Maps y odómetro
- `alerta_bajo_rendimiento` - Boolean si < 2.5 km/lt

## 🔄 URLs Principales del Sistema

```
/                          → Página de inicio (IndexView)
/admin/                    → Django Admin
/operadores/               → Dashboard operadores
/unidades/                 → Dashboard unidades
/bitacoras/                → Dashboard bitácoras
```

## 💾 Guardado Automático

El modelo `BitacoraViaje` tiene un `save()` override que:
1. Valida que fecha_llegada > fecha_salida
2. Valida que kilometraje_llegada > kilometraje_salida
3. Marca `completado=True` automáticamente si tiene fecha_llegada
4. Actualiza el `kilometraje_actual` de la unidad al completarse

## 🚀 Uso Rápido

### Crear Operador
```bash
GET /operadores/crear/
POST /operadores/crear/ → Formulario con datos
```

### Listar con Filtros
```bash
GET /operadores/lista/?search=Juan&tipo=LOCAL&activo=true
GET /unidades/lista/?tipo=FORANEA&activa=true
GET /bitacoras/lista/?completado=false&operador=1
```

### Completar Viaje
```bash
GET /bitacoras/<id>/completar/
POST /bitacoras/<id>/completar/ → fecha_llegada + kilometraje_llegada
```

### Calcular Distancia (AJAX)
```javascript
fetch('/bitacoras/<id>/calcular-distancia/', {
    method: 'POST',
    headers: {
        'X-CSRFToken': csrfToken
    }
})
.then(response => response.json())
.then(data => {
    console.log(data.distancia_km, data.duracion_min);
});
```

## ⚙️ Configuración Requerida

1. **Migrar modelos:**
```bash
python manage.py makemigrations
python manage.py migrate
```

2. **Crear superusuario:**
```bash
python manage.py createsuperuser
```

3. **Configurar Google Maps API Key:**
```bash
# En .env
GOOGLE_MAPS_API_KEY='tu_api_key_aqui'
```

4. **Correr servidor:**
```bash
python manage.py runserver
```

## 📝 Próximos Pasos

Para usar el sistema completo, se necesitan:
1. ✅ Vistas y URLs (COMPLETO)
2. ✅ Formularios (COMPLETO)
3. ⏳ Templates HTML para cada vista
4. ⏳ Registrar modelos en Django Admin

## 🎨 Templates Requeridos

### Operadores
- `operadores/operador_list.html`
- `operadores/operador_detail.html`
- `operadores/operador_form.html`
- `operadores/operador_confirm_delete.html`
- `operadores/operador_dashboard.html`

### Unidades
- `unidades/unidad_list.html`
- `unidades/unidad_detail.html`
- `unidades/unidad_form.html`
- `unidades/unidad_confirm_delete.html`
- `unidades/unidad_dashboard.html`

### Bitácoras
- `bitacoras/bitacora_list.html`
- `bitacoras/bitacora_detail.html`
- `bitacoras/bitacora_form.html`
- `bitacoras/bitacora_confirm_delete.html`
- `bitacoras/bitacora_dashboard.html`
- `bitacoras/completar_viaje.html`
