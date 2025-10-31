# Templates - Sistema de Gestión de Transporte

## 📁 Estructura de Templates

```
templates/
├── base.html          # Template base con navegación, header y footer
├── index.html         # Página de inicio / dashboard
└── README.md          # Esta documentación
```

## 🎨 Paleta de Colores

Los colores están extraídos del logo de ProyectoKasu:

```css
--primary-color: #2C3E50;      /* Azul oscuro corporativo */
--secondary-color: #E74C3C;    /* Rojo/Naranja de acento */
--accent-color: #F39C12;       /* Amarillo/dorado */
--light-color: #ECF0F1;        /* Gris claro */
--dark-color: #2C3E50;         /* Texto oscuro */
--success-color: #27AE60;      /* Verde éxito */
--warning-color: #F39C12;      /* Amarillo advertencia */
--error-color: #E74C3C;        /* Rojo error */
--info-color: #3498DB;         /* Azul información */
```

## 🏗️ Template Base (base.html)

El template base incluye:

### Componentes Principales

1. **Header/Navbar**
   - Logo de la empresa
   - Navegación principal (Inicio, Operadores, Unidades, Bitácoras)
   - Información de usuario y botón de logout

2. **Sistema de Mensajes**
   - Alertas de success, error, warning, info
   - Auto-cierre después de 5 segundos

3. **Contenido Principal**
   - Área de breadcrumb (opcional)
   - Bloque de contenido dinámico

4. **Footer**
   - Información corporativa
   - Enlaces útiles
   - Copyright

### Bloques Disponibles

```django
{% block title %}        <!-- Título de la página -->
{% block extra_css %}    <!-- CSS adicional -->
{% block breadcrumb %}   <!-- Migas de pan -->
{% block content %}      <!-- Contenido principal -->
{% block extra_js %}     <!-- JavaScript adicional -->
```

## 📄 Crear Nuevos Templates

### Ejemplo básico:

```django
{% extends "base.html" %}
{% load static %}

{% block title %}Mi Página{% endblock %}

{% block content %}
<div class="card">
    <div class="card-header">
        <h2 class="card-title">Título de la Página</h2>
    </div>
    <div class="card-body">
        <!-- Tu contenido aquí -->
    </div>
</div>
{% endblock %}
```

## 🎯 Componentes CSS Disponibles

### Contenedores

```html
<div class="container">        <!-- Contenedor principal (max-width: 1200px) -->
<div class="card">            <!-- Tarjeta con sombra -->
<div class="card-header">     <!-- Encabezado de tarjeta -->
<div class="card-body">       <!-- Cuerpo de tarjeta -->
```

### Grid System

```html
<div class="grid grid-2">     <!-- 2 columnas responsivas -->
<div class="grid grid-3">     <!-- 3 columnas responsivas -->
<div class="grid grid-4">     <!-- 4 columnas responsivas -->
```

### Botones

```html
<button class="btn btn-primary">Primario</button>
<button class="btn btn-success">Éxito</button>
<button class="btn btn-logout">Salir</button>
```

### Alertas

```html
<div class="alert alert-success">Mensaje de éxito</div>
<div class="alert alert-error">Mensaje de error</div>
<div class="alert alert-warning">Mensaje de advertencia</div>
<div class="alert alert-info">Mensaje informativo</div>
```

### Tablas

```html
<div class="table-container">
    <table>
        <thead>
            <tr>
                <th>Columna 1</th>
                <th>Columna 2</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Dato 1</td>
                <td>Dato 2</td>
            </tr>
        </tbody>
    </table>
</div>
```

### Utilidades

```html
<!-- Márgenes -->
<div class="mt-1 mt-2 mt-3 mt-4">  <!-- margin-top -->
<div class="mb-1 mb-2 mb-3 mb-4">  <!-- margin-bottom -->

<!-- Padding -->
<div class="p-1 p-2 p-3 p-4">      <!-- padding -->

<!-- Alineación -->
<div class="text-center">           <!-- texto centrado -->
<div class="text-right">            <!-- texto a la derecha -->
```

## 🎨 Formularios

```html
<form method="post" data-validate>
    {% csrf_token %}
    
    <div class="form-group">
        <label class="form-label" for="campo">Nombre del Campo</label>
        <input type="text" class="form-control" id="campo" name="campo" required>
    </div>
    
    <button type="submit" class="btn btn-primary">Enviar</button>
</form>
```

## 🔧 JavaScript Disponible

### Funciones Globales

```javascript
// Formatear moneda mexicana
formatMXN(1234.56)  // "$1,234.56"

// Formatear fechas
formatDate('2024-01-15')  // "15 de enero de 2024"

// Mostrar notificación
showNotification('Mensaje', 'success')  // tipos: success, error, warning, info
```

### Atributos Data

```html
<!-- Confirmación de eliminación -->
<button data-confirm-delete="¿Eliminar este elemento?">Eliminar</button>

<!-- Tooltip -->
<span data-tooltip="Texto del tooltip">Hover aquí</span>

<!-- Toggle password -->
<button data-toggle-password="password-field-id">👁️</button>
```

## 📱 Responsive Design

El sistema es completamente responsivo con breakpoints:

- **Desktop**: > 992px
- **Tablet**: 768px - 992px
- **Mobile**: < 768px

## 🚀 Mejores Prácticas

1. **Siempre extender base.html**
   ```django
   {% extends "base.html" %}
   ```

2. **Usar load static al inicio**
   ```django
   {% load static %}
   ```

3. **Definir títulos descriptivos**
   ```django
   {% block title %}Descripción Clara{% endblock %}
   ```

4. **Usar clases CSS del sistema**
   - Preferir `.card`, `.grid`, `.btn` sobre estilos inline
   - Usar variables CSS para colores

5. **Incluir CSRF token en formularios**
   ```django
   {% csrf_token %}
   ```

## 🔗 Referencias

- Django Templates: https://docs.djangoproject.com/en/5.2/topics/templates/
- CSS Variables: Las variables están definidas en `static/css/base.css`
- JavaScript: Funciones globales en `static/js/base.js`

## 📝 Notas Importantes

- El logo se encuentra en `media/logoKasu.png`
- Los archivos estáticos se sirven desde `/static/`
- Los archivos media se sirven desde `/media/`
- El sistema usa español (es-mx) como idioma por defecto
- Todos los templates usan emojis para iconos (compatibilidad universal)
