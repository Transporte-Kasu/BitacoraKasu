# Diseño: Sistema de Auditoría del Módulo de Almacén

**Fecha:** 2026-06-30  
**Estado:** Aprobado  

---

## Objetivo

Registrar todas las acciones que los usuarios realizan en el módulo de almacén (crear, editar, eliminar, autorizar, rechazar, entregar, cancelar), capturando los valores anteriores y nuevos de cada cambio. El log es visible únicamente para superusuarios desde el Django Admin, con opción de exportación a Excel.

---

## 1. Modelo de datos

### `AuditoriaAlmacen` — nuevo modelo en `modulos/almacen/models.py`

```python
class AuditoriaAlmacen(models.Model):
    ACCION_CHOICES = [
        ('CREAR',     'Crear'),
        ('EDITAR',    'Editar'),
        ('ELIMINAR',  'Eliminar'),
        ('AUTORIZAR', 'Autorizar'),
        ('RECHAZAR',  'Rechazar'),
        ('ENTREGAR',  'Entregar'),
        ('CANCELAR',  'Cancelar'),
    ]

    usuario             = ForeignKey(User, SET_NULL, null=True)
    accion              = CharField(max_length=20, choices=ACCION_CHOICES)
    modelo              = CharField(max_length=100)   # nombre del modelo afectado
    objeto_id           = CharField(max_length=100)   # PK del objeto
    objeto_str          = CharField(max_length=300)   # __str__ del objeto
    valores_anteriores  = JSONField(null=True)         # snapshot completo antes del cambio
    valores_nuevos      = JSONField(null=True)         # snapshot completo después del cambio
    ip_address          = GenericIPAddressField(null=True, blank=True)
    fecha               = DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        indexes: fecha, usuario, accion, modelo
```

### Modelos auditados

| Modelo | Acciones capturadas |
|--------|---------------------|
| `ProductoAlmacen` | CREAR, EDITAR, ELIMINAR |
| `EntradaAlmacen` | CREAR, EDITAR, ELIMINAR |
| `ItemEntradaAlmacen` | CREAR, EDITAR, ELIMINAR |
| `SolicitudSalida` | CREAR, EDITAR, ELIMINAR, AUTORIZAR, RECHAZAR, CANCELAR |
| `SalidaAlmacen` | CREAR, ENTREGAR |
| `SalidaRapidaConsumible` | CREAR, ELIMINAR |
| `AsignacionDirectaAlmacen` | CREAR, ELIMINAR |
| `AsignacionSalida` | CREAR, ELIMINAR |

`MovimientoAlmacen` y `AlertaStock` **no se auditan** — son generados automáticamente por signals del sistema, no por acciones directas del usuario.

---

## 2. Captura del usuario — Middleware de thread-local

### Archivo: `config/middleware.py` (nuevo)

```python
import threading
_thread_locals = threading.local()

def get_current_user():
    return getattr(_thread_locals, 'user', None)

def get_current_ip():
    return getattr(_thread_locals, 'ip', None)

class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        _thread_locals.ip = self._get_ip(request)
        return self.get_response(request)

    def _get_ip(self, request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
```

Registrar en `config/settings.py`:
```python
MIDDLEWARE = [
    ...
    'config.middleware.CurrentUserMiddleware',
]
```

---

## 3. Señales de auditoría

### Archivo: `modulos/almacen/signals.py` (ampliar el existente)

#### Flujo de captura

```
pre_save signal
  → si instance.pk existe: fetch objeto desde BD → serializar TODOS los campos → guardar en instance._auditoria_anterior
  → si instance.pk es None: instance._auditoria_anterior = None (es creación)

post_save signal
  → accion = 'CREAR' si created else 'EDITAR'
  → valores_anteriores = instance._auditoria_anterior
  → valores_nuevos = serializar_modelo(instance)
  → crear AuditoriaAlmacen(...)

post_delete signal
  → accion = 'ELIMINAR'
  → valores_anteriores = serializar_modelo(instance)
  → valores_nuevos = None
  → crear AuditoriaAlmacen(...)
```

#### Función de serialización

```python
from decimal import Decimal

def serializar_modelo(instance):
    """Serializa todos los campos del modelo a dict JSON-compatible."""
    data = {}
    for field in instance._meta.fields:
        value = getattr(instance, field.name)
        if hasattr(value, 'pk'):              # ForeignKey → guardar pk + str
            data[field.name] = {'pk': value.pk, 'str': str(value)}
        elif isinstance(value, Decimal):      # DecimalField → string para preservar precisión
            data[field.name] = str(value)
        elif hasattr(value, 'isoformat'):     # fecha/datetime → ISO string
            data[field.name] = value.isoformat()
        elif isinstance(value, (str, int, float, bool, type(None))):
            data[field.name] = value
        else:
            data[field.name] = str(value)
    return data
```

#### Decorador helper para registrar señales

```python
MODELOS_AUDITADOS = [
    ProductoAlmacen, EntradaAlmacen, ItemEntradaAlmacen,
    SolicitudSalida, SalidaAlmacen,
    SalidaRapidaConsumible, AsignacionDirectaAlmacen, AsignacionSalida,
]
```

Se conectan `pre_save`, `post_save` y `post_delete` a cada modelo de la lista usando `receiver` con `sender` explícito.

---

## 4. Django Admin

### Archivo: `modulos/almacen/admin.py` (ampliar el existente)

#### Vista de lista

```
Columnas: fecha | usuario | acción (badge color) | modelo | objeto_str | IP
Filtros:  accion, modelo, usuario, fecha (DateFieldListFilter)
Búsqueda: usuario__username, usuario__first_name, objeto_str, modelo
```

#### Restricciones

- `has_add_permission → False` — no se pueden crear registros manualmente
- `has_change_permission → False` — no se pueden editar
- `has_delete_permission → False` — no se pueden eliminar
- Solo visible para superusuarios (`def has_module_perms` / `def has_view_permission` check `request.user.is_superuser`)

#### Vista de detalle

Muestra los cambios en tabla comparativa:

```
Campo               Antes               Después
────────────────    ──────────────      ──────────────
cantidad            50.00               45.00
costo_unitario      150.00              150.00
estado              PENDIENTE           AUTORIZADA
```

Los campos `JSONField` se renderizan como tabla HTML, no como texto crudo.

#### Exportación a Excel

Botón "Exportar a Excel" en la lista del admin (usando `change_list_template` personalizado). Aplica los mismos filtros activos de la vista. Genera un `.xlsx` con `openpyxl` (ya disponible en el proyecto vía la exportación de bitácora) con las columnas:

```
Fecha | Usuario | Acción | Modelo | Objeto | Campo | Valor Anterior | Valor Nuevo | IP
```

Los cambios se expanden: una fila por campo modificado (no una fila por registro de auditoría), para facilitar la lectura.

URL: `/admin/almacen/auditoriaalmacen/exportar-excel/`

---

## 5. Archivos a crear o modificar

| Archivo | Cambio |
|---------|--------|
| `config/middleware.py` | **Crear** — `CurrentUserMiddleware` |
| `config/settings.py` | Agregar middleware a `MIDDLEWARE` |
| `modulos/almacen/models.py` | Agregar modelo `AuditoriaAlmacen` |
| `modulos/almacen/signals.py` | Agregar señales `pre_save`, `post_save`, `post_delete` para modelos auditados |
| `modulos/almacen/admin.py` | Registrar `AuditoriaAlmacen` con admin personalizado + export Excel |
| `templates/admin/almacen/auditoriaalmacen/change_list.html` | **Crear** — template con botón Excel |
| `modulos/almacen/migrations/` | Nueva migración para `AuditoriaAlmacen` |

---

## 6. Lo que NO incluye este diseño

- No registra acciones de login/logout (fuera del alcance del módulo de almacén)
- No audita vistas de solo lectura (listados, reportes) — solo escrituras
- No envía notificaciones cuando ocurre una acción auditada
- No expone el log fuera del Django Admin (no hay vista pública)
