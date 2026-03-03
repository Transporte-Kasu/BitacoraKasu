# Memoria UX/UI Expert - BitacoraKasu

## Stack de diseño confirmado
- Tailwind CSS via CDN (sin build step) en templates publicos standalone
- `base.html` con sidebar para vistas con login; templates publicos son standalone
- Sin framework JS adicional (vanilla JS en todos los templates revisados)
- Idioma objetivo: `es-MX` (lang en html debe ser `es-MX`, no `es`)

## Patrones de accesibilidad criticos para este proyecto

### Radio buttons como botones visuales
Patron presente en `taller/reportar_falla.html`. El estandar correcto para ocultar
el input pero mantenerlo accesible es clip/position, NO `display:none`:
```css
input[type=radio] {
    position: absolute; opacity: 0; width: 1px; height: 1px;
    margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap;
}
```
Ver: `patterns.md` para la implementacion completa con focus-visible.

### Touch targets moviles
Minimo recomendado para operadores en campo: `min-height: 56px` (supera los 44px de WCAG).
Separacion entre botones de opcion: `space-y-3` (12px), no `space-y-2`.

## Contexto de usuarios por vista

| Vista | Usuario | Dispositivo | Contexto de uso |
|-------|---------|-------------|----------------|
| `/taller/reportar/<pk>/` | Operador de camion | Movil (campo) | Estresado, mala senal posible |
| `/taller/bandeja-reportes/` | Personal de taller | Desktop/tablet | Oficina |
| Dashboard general | Admin HR | Desktop | Oficina |

## Problemas sistemicos encontrados (revisar en futuros templates)
- `lang="es"` en lugar de `lang="es-MX"` - revisar todos los templates standalone
- `maximum-scale=1.0` en viewport - bloquea zoom de accesibilidad (WCAG 1.4.4)
- `text-gray-400` para texto secundario: ratio 2.5:1, incumple WCAG 1.4.3. Usar minimo `text-slate-600` (4.6:1)

## Archivos clave del modulo taller
- Vista publica QR: `modulos/taller/views.py` funciones `reportar_falla()` y `reporte_enviado()`
- Modelo: `modulos/taller/models.py` clase `ReporteFalla` y `CategoriaFalla`
- Templates publicos: `templates/taller/reportar_falla.html`, `reporte_enviado.html`

Ver `patterns.md` para ejemplos de codigo completos.
