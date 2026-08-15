# Diseño: Campo `fecha_hora_entrega` en `BitacoraViaje`

**Fecha:** 2026-08-15
**Estado:** Aprobado

---

## Objetivo

Agregar un campo real `fecha_hora_entrega` (DateTimeField opcional) al modelo `BitacoraViaje`, poblado desde dos fuentes: la carga masiva por Excel (columna A, "FECHA ENTREGA / HORARIO", ej. `"25/06/2026    08:00 HRS"`) y el formulario manual de crear/editar bitácora. Hoy esa fecha existe en el Excel pero el parser (`excel_parser.py`) descarta la hora y solo usa la fecha como insumo para calcular `fecha_salida`/`fecha_carga` ("un día antes"), sin persistirla nunca como dato propio.

Esto también resuelve una limitación conocida de la feature de notificación WhatsApp al operador (`docs/superpowers/specs/2026-08-14-notificacion-whatsapp-operador-design.md`): el "Horario de entrega" enviado al operador se calculaba como `fecha_salida + duracion_estimada` (aproximación vía Google Maps) por falta de un campo real. Con `fecha_hora_entrega` disponible, la notificación usa el dato real cuando existe.

No se borra ni renombra ningún campo existente — todos los cambios son aditivos.

---

## 1. Modelo

**`modulos/bitacoras/models.py`**, junto a `fecha_carga`/`fecha_salida`/`fecha_llegada` (líneas 103-114):

```python
fecha_hora_entrega = models.DateTimeField(
    null=True,
    blank=True,
    verbose_name="Fecha/hora de entrega",
)
```

Opcional (`null=True, blank=True`): no todos los viajes traen cita de entrega programada (ej. viajes LOCAL capturados manualmente sin ese dato). Nueva migración (`AddField`, sin `RunPython`).

---

## 2. Parser de Excel

**`modulos/bitacoras/excel_parser.py`**

`_parse_fecha_entrega()` (líneas 13-21) hoy:
```python
def _parse_fecha_entrega(raw):
    if not raw:
        return None
    s = str(raw).strip()
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if not m:
        return None
    day, month, year = m.groups()
    return datetime(int(year), int(month), int(day))
```

Se extiende para también capturar la hora (`"08:00 HRS"` → `08:00`), buscando un segundo patrón `HH:MM` en el mismo string, tras extraer la fecha:

```python
def _parse_fecha_entrega(raw):
    if not raw:
        return None
    s = str(raw).strip()
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if not m:
        return None
    day, month, year = m.groups()
    hora, minuto = 0, 0
    m_hora = re.search(r'(\d{1,2}):(\d{2})', s)
    if m_hora:
        hora, minuto = int(m_hora.group(1)), int(m_hora.group(2))
    return datetime(int(year), int(month), int(day), hora, minuto)
```

Si la celda no trae hora (formato inesperado), queda en `00:00` — mismo comportamiento que hoy (que siempre ignoraba la hora), así que no rompe nada para datos ya bien formados. El cálculo existente de `fecha_salida`/`fecha_carga` como "día anterior a la hora configurada por el usuario" (líneas 102-106) sigue exactamente igual — usa `fecha_entrega.replace(hour=..., minute=...)`, así que es indiferente a que `fecha_entrega` ahora traiga hora real en vez de medianoche.

**Nueva clave en el dict `current`** (líneas 108-123), junto a `fecha_salida`/`fecha_carga`:

```python
'fecha_entrega_display': fecha_entrega.strftime('%d/%m/%Y %H:%M') if fecha_entrega else '',
'fecha_hora_entrega':    fecha_entrega.strftime('%Y-%m-%dT%H:%M') if fecha_entrega else '',
```

`fecha_entrega_display` cambia de formato `'%d/%m/%Y'` a `'%d/%m/%Y %H:%M'` (ahora sí hay hora que mostrar). `fecha_hora_entrega` es nueva, en formato compatible con `<input type="datetime-local">`, igual que las claves `fecha_salida`/`fecha_carga` ya existentes.

---

## 3. Carga masiva

**`templates/bitacoras/carga_masiva_preview.html`**, sección "Fechas calculadas" (líneas 287-302), se agrega un tercer input junto a los de carga/salida — **sin `required`**, a diferencia de esos dos:

```html
<div>
    <label class="block text-[11px] text-slate-400 mb-0.5">Fecha y hora de entrega</label>
    <input type="datetime-local" name="v{{ idx }}_fecha_hora_entrega"
           value="{{ viaje.fecha_hora_entrega }}" class="form-control text-xs">
</div>
```

**`modulos/bitacoras/views.py`**, `carga_masiva_preview` POST (líneas 510-552): se lee el nuevo campo y se pasa opcionalmente al construir `BitacoraViaje`:

```python
fecha_entrega_str = request.POST.get(f'{p}fecha_hora_entrega', '').strip()
...
bitacora = BitacoraViaje(
    ...,
    fecha_hora_entrega = datetime.fromisoformat(fecha_entrega_str) if fecha_entrega_str else None,
    ...,
)
```

A diferencia de `fecha_salida`/`fecha_carga` (que son obligatorios y bloquean la fila con un error si faltan, líneas 531-533), un `fecha_hora_entrega` vacío **no** genera error — simplemente se guarda `None`.

**`templates/bitacoras/carga_masiva.html`** (líneas 180-193): se actualiza el texto "Formato esperado" para indicar que la columna A también aporta la hora de entrega (hoy solo dice "Col A = Fecha de entrega DD/MM/YYYY").

---

## 4. Formulario manual

**`modulos/bitacoras/forms.py`**, `BitacoraViajeForm`:

- Se agrega `'fecha_hora_entrega'` a `Meta.fields` (líneas 25-41), junto a `'fecha_carga'`/`'fecha_salida'`.
- Se agrega el widget correspondiente (líneas 61-68), mismo patrón que los otros dos:

```python
'fecha_hora_entrega': forms.DateTimeInput(attrs={
    'class': 'form-control',
    'type': 'datetime-local',
}),
```

**`templates/bitacoras/bitacora_form.html`**, card "Fecha" (líneas 317-346): el grid pasa de `sm:grid-cols-2` a `sm:grid-cols-3`, y se agrega el tercer campo **sin** el asterisco rojo de obligatorio que sí tienen carga/salida:

```html
<div>
    <label for="{{ form.fecha_hora_entrega.id_for_label }}" class="block text-sm font-medium text-slate-700 mb-1.5">
        Fecha/hora de entrega
    </label>
    {{ form.fecha_hora_entrega }}
    {% if form.fecha_hora_entrega.errors %}
    <p class="mt-1 text-xs text-red-600" role="alert">{{ form.fecha_hora_entrega.errors|join:", " }}</p>
    {% endif %}
</div>
```

---

## 5. Admin

**`modulos/bitacoras/admin.py`**, fieldset `'Fechas'` (línea 48-50):

```python
('Fechas', {
    'fields': ('fecha_carga', 'fecha_salida', 'fecha_hora_entrega', 'fecha_llegada', 'completado')
}),
```

---

## 6. Detalle de bitácora

**`templates/bitacoras/bitacora_detail.html`**, tarjeta "Fechas y Combustible" (líneas 204-234), nuevo `dato-group` condicional entre "Fecha de Salida" y "Fecha de Llegada":

```html
{% if bitacora.fecha_hora_entrega %}
<div class="dato-group">
    <div class="dato-label">Fecha/Hora de Entrega</div>
    <div class="dato-valor">{{ bitacora.fecha_hora_entrega|date:"d/m/Y H:i" }}</div>
</div>
{% endif %}
```

---

## 7. Notificación WhatsApp al operador

**`config/services/twilio_service.py`**, `enviar_notificacion_operador()` (líneas 155-159), cambia la prioridad de cálculo de `{{2}}`:

```python
if bitacora.fecha_hora_entrega:
    hora_entrega = bitacora.fecha_hora_entrega
elif bitacora.duracion_estimada:
    hora_entrega = bitacora.fecha_salida + timedelta(minutes=bitacora.duracion_estimada)
else:
    hora_entrega = bitacora.fecha_salida
```

Usa el dato real capturado (Excel o formulario manual) cuando existe; si no, cae al cálculo aproximado (`fecha_salida + duracion_estimada` de Google Maps) que ya existía, y si tampoco hay duración estimada, usa `fecha_salida` sola — mismo fallback en cascada que ya había, solo con un nuevo primer escalón de mayor prioridad. `_fecha_es()` (que ya convierte a hora local desde el fix del final-review anterior) se sigue aplicando sobre el resultado sin cambios.

---

## 8. Testing (TDD)

- **Parser** (`modulos/bitacoras/excel_parser.py` no tiene tests hoy — no existe ningún archivo que lo pruebe; se agregan a `modulos/bitacoras/tests.py`, probando `_parse_fecha_entrega` directamente): extrae correctamente fecha + hora de `"25/06/2026    08:00 HRS"`; cuando la celda no trae hora, cae a `00:00` sin romper; queda bien formada como `datetime`.
- **Carga masiva (vista)**: POST con `v0_fecha_hora_entrega` presente persiste el campo en el `BitacoraViaje` creado; POST sin ese campo (vacío) no genera error y guarda `None`.
- **Formulario manual**: `BitacoraViajeForm` acepta `fecha_hora_entrega` vacío (válido, campo opcional) y con valor.
- **Notificación WhatsApp**: nuevo caso en `EnviarNotificacionOperadorTests` — con `fecha_hora_entrega` presente, `{{2}}` usa ese valor exacto (no el cálculo por duración), incluso si `duracion_estimada` también está presente (prioridad correcta). Los tests existentes (fallback por duración, fallback a `fecha_salida` sola) siguen pasando sin cambios ya que construyen bitácoras sin `fecha_hora_entrega`.

---

## Fuera de alcance

- No se modifica el cálculo existente de `fecha_salida`/`fecha_carga` como "día anterior a la hora configurada" en la carga masiva.
- No se agrega validación cruzada (ej. que `fecha_hora_entrega` sea posterior a `fecha_salida`) — el campo es informativo/opcional, sin reglas de negocio adicionales por ahora.
- No se actualiza el reporte de balanza de utilidad ni ningún otro reporte — este campo no participa en cálculos financieros.
- No se toca `carga_masiva_upload` (la vista de subida inicial) — el cambio vive en el parser y en `carga_masiva_preview`.
