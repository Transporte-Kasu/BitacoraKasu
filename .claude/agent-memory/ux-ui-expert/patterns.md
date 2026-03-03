# Patrones de codigo UX/UI - BitacoraKasu

## Radio buttons accesibles con apariencia de boton

Usado en `templates/taller/reportar_falla.html`.

```css
/* Oculto visualmente pero presente para teclado y lectores de pantalla */
input[type=radio] {
    position: absolute;
    opacity: 0;
    width: 1px;
    height: 1px;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
}
.categoria-btn {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem;
    border: 2px solid #cbd5e1;
    border-radius: 0.75rem;
    background: white;
    cursor: pointer;
    min-height: 56px;
}
.categoria-btn.selected {
    border-color: #1d4ed8;
    background: #eff6ff;
}
/* Foco visible para navegacion por teclado */
input[type=radio]:focus-visible ~ .categoria-btn {
    outline: 3px solid #1d4ed8;
    outline-offset: 2px;
}
```

El checkmark SVG dentro del label cambia `opacity` via JS al seleccionar,
eliminando la dependencia exclusiva en color para indicar seleccion (WCAG 1.4.1).

## Validacion de categoria requerida con feedback accesible

```javascript
form.addEventListener('submit', function(e) {
    var hayOpciones = document.querySelectorAll('input[name="categoria_falla"]').length > 0;
    var seleccionada = document.querySelector('input[name="categoria_falla"]:checked');
    if (hayOpciones && !seleccionada) {
        e.preventDefault();
        var aviso = document.getElementById('aviso-categoria');
        aviso.classList.remove('hidden');
        aviso.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
});
```

El elemento `aviso-categoria` debe tener `role="alert"` y `aria-live="assertive"`.

## Indicadores de prioridad sin dependencia de color puro

Para `CategoriaFalla.prioridad_default`, usar forma + color en lugar de solo emoji de color:

```html
{% if cat.prioridad_default == 'CRITICA' %}
<span class="inline-flex items-center justify-center w-7 h-7 rounded-full bg-red-600 text-white text-xs font-black" aria-label="prioridad critica">!</span>
{% elif cat.prioridad_default == 'ALTA' %}
<span class="inline-flex items-center justify-center w-7 h-7 rounded-full bg-orange-500 text-white text-xs font-black" aria-label="prioridad alta">!</span>
{% elif cat.prioridad_default == 'MEDIA' %}
<span class="inline-flex items-center justify-center w-7 h-7 rounded-full bg-yellow-400 text-gray-800 text-xs font-black" aria-label="prioridad media">~</span>
{% else %}
<span class="inline-flex items-center justify-center w-7 h-7 rounded-full bg-green-500 text-white text-xs font-black" aria-label="prioridad baja">-</span>
{% endif %}
```

## Validacion de tamano de archivo en cliente

```javascript
fotoInput.addEventListener('change', function() {
    var file = this.files[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
        document.getElementById('aviso-foto-tamano').classList.remove('hidden');
        this.value = '';
        return;
    }
    // mostrar preview...
});
```

## Orden de campos optimo para formulario de campo movil

Regla general para formularios de reporte rapido desde movil:
1. Campo obligatorio principal (accion primaria)
2. Campo con alta motivacion contextual (foto, si aplica)
3. Campos de detalle opcionales (descripcion)
4. Campos de identidad opcionales (nombre)
5. Boton de envio

Reduce la distancia cognitiva al caso de uso mas frecuente.
