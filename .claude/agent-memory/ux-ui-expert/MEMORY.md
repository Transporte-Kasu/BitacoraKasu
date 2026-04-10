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

## Patron tabla→cards para listas responsivas (implementado en taller)
Usar CSS display toggle con breakpoint md (768px):
```css
.cards-vista  { display: block; }
.tabla-vista  { display: none; }
@media (min-width: 768px) {
    .cards-vista { display: none; }
    .tabla-vista { display: block; }
}
```
Ambas vistas comparten los mismos datos Django — sin JS. Implementado en:
- `taller/lista_ordenes.html` (.cards-ordenes / .tabla-ordenes)
- `taller/bandeja_reportes.html` (.cards-reportes / .tabla-reportes)
- `taller/dashboard.html` (.ultimas-cards / .ultimas-tabla)

## Patron modal accesible (bottom-sheet en movil, centrado en desktop)
Reemplaza el patron de `display:none/block` con `display:flex` via clase `.activo`.
Incluye: cierre con Escape, foco al primer elemento interactivo, cierre al click backdrop.
```css
.modal-backdrop { display: none; position: fixed; inset: 0; ... align-items: flex-end; }
.modal-backdrop.activo { display: flex; }
@media (min-width: 640px) {
    .modal-backdrop { align-items: center; }
    .modal-panel { border-radius: 1rem; }
}
```
Atributos ARIA obligatorios: `role="dialog"`, `aria-modal="true"`, `aria-labelledby`.
Implementado en: `taller/detalle_orden.html`, `taller/detalle_reporte.html`.

## Contexto de usuarios por vista (actualizado)

| Vista | Usuario | Dispositivo | Contexto de uso |
|-------|---------|-------------|----------------|
| `/taller/reportar/<pk>/` | Operador de camion | Movil (campo) | Estresado, mala senal |
| `/taller/bandeja-reportes/` | Personal de taller | Desktop/tablet | Oficina |
| `/taller/dashboard/` | Jefe de taller | Desktop/tablet | Oficina |
| `/taller/lista-ordenes/` | Personal de taller | Desktop (primario) | Oficina |
| `/taller/detalle/<folio>/` | Mecanico/supervisor | Desktop o tablet | Taller |

Ver `patterns.md` para ejemplos de codigo completos.

## Entorno virtual correcto
`.venvBitacoraKasu/` (no `.venvKasu` como dice CLAUDE.md — ese nombre esta desactualizado).
Comando: `source .venvBitacoraKasu/bin/activate && python manage.py ...`

## Patron galeria de tarjetas (fleet-card) — modulos que lo usan
El patron `.fleet-card` con grupos por tipo, tooltip hover y JS de navegacion esta implementado en:
- `unidades/unidad_list.html` + `unidades/_fleet_card.html` (referencia original)
- `operadores/operador_list.html` + `operadores/_operador_card.html` (implementado)

Diferencias operadores vs unidades:
- Tipo `FORANEO` (no `FORANEA` como en unidades) — respetar el valor exacto del modelo
- Solo 2 badges: `badge-unidad` (verde palido) y `badge-viajes` (verde oscuro)
- Sin paginacion (`paginate_by = None`): grupos_operadores se construye en Python filtrando el QS ya anotado
- SVG de persona con casco y volante (viewBox 100x80) en lugar de camion (viewBox 100x60)
