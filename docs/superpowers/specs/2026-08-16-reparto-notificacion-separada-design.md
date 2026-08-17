# Diseño: Notificación separada por contenedor en viajes con reparto

**Fecha:** 2026-08-16
**Estado:** Aprobado

---

## Objetivo

Hoy un viaje FULL con `reparto=True` (dos contenedores, hasta dos códigos postales de destino) se notifica al cliente con **un solo mensaje** que combina la información de ambos contenedores, dirigido a un único `cliente`. Esto no refleja la operación real:

- Los dos contenedores pueden ser para **clientes distintos** (necesitan notificación por separado, cada uno con su propio destino).
- Aunque sea el **mismo cliente**, por restricción de espacio solo se puede entregar un contenedor a la vez — son dos eventos de entrega distintos con horarios distintos, y el cliente debe recibir dos avisos, no uno mezclado.

El operador **no cambia**: sigue ejecutando el viaje completo (ambos contenedores) y sigue recibiendo un único WhatsApp combinado, igual que hoy — el reparto es una distinción de cara al cliente, no de la operación del viaje.

Todos los cambios son aditivos: no se borra ni renombra ningún campo existente.

---

## 1. Modelo

**`modulos/bitacoras/models.py`**, junto a `cliente` (líneas 44-51) y `fecha_hora_entrega` (líneas 115-119), dos campos nuevos, ambos opcionales:

```python
cliente_2 = models.ForeignKey(
    'Cliente',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='bitacoras_contenedor_2',
    verbose_name="Cliente (contenedor 2)",
)
```

```python
fecha_hora_entrega_2 = models.DateTimeField(
    null=True,
    blank=True,
    verbose_name="Fecha/hora de entrega (contenedor 2)",
)
```

- `cliente_2` vacío ⇒ el contenedor 2 se notifica al mismo `cliente` (dos avisos al mismo destinatario, uno por evento de entrega).
- `fecha_hora_entrega_2` vacío ⇒ el contenedor 2 usa `fecha_hora_entrega` (mismo horario que el contenedor 1).

`cp_destino_2` ya existe (`blank=True`) — se mantiene `blank=True` a nivel de modelo (la obligatoriedad condicional a `reparto` vive en `clean()`/`forms.py`, igual que las reglas de `contenedor_2` ya existentes).

Nueva migración `AddField` ×2, sin `RunPython`.

---

## 2. Validación

**`modulos/bitacoras/models.py`**, `clean()` (líneas 327-341), se agrega junto a las validaciones de reparto existentes:

```python
if self.reparto and not self.cp_destino_2:
    raise ValidationError({'cp_destino_2': 'El reparto requiere el CP del segundo destino.'})
```

**`modulos/bitacoras/forms.py`**, `BitacoraViajeForm.clean()` (líneas 162-180), misma regla en el formulario (igual patrón que las de `contenedor_2`):

```python
cp_destino_2 = cleaned_data.get('cp_destino_2')
if reparto and not cp_destino_2:
    self.add_error('cp_destino_2', 'El reparto requiere el CP del segundo destino.')
```

`cliente_2` y `fecha_hora_entrega_2` no llevan validación de obligatoriedad — quedan opcionales incluso con `reparto=True` (su ausencia significa "igual que el contenedor 1", no un error).

No se valida que `cp_destino_2 != cp_destino` — pueden coincidir (caso "mismo CP, distinto horario de entrega").

---

## 3. Formulario

**`modulos/bitacoras/forms.py`**, `BitacoraViajeForm.Meta.fields` (líneas 25-42): se agregan `'cliente_2'` y `'fecha_hora_entrega_2'`, junto a `'cliente'` y `'fecha_hora_entrega'`.

Widgets nuevos, mismo patrón que sus contrapartes del contenedor 1:

```python
'cliente_2': forms.Select(attrs={
    'class': 'form-control',
}),
'fecha_hora_entrega_2': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
    'class': 'form-control',
    'type': 'datetime-local',
}),
```

---

## 4. UI (`templates/bitacoras/bitacora_form.html`)

En la sección `#seccion-cp-destino-2` (líneas 507-531), que ya se muestra/oculta con el toggle JS de `reparto` (líneas 693-705):

- El texto de ayuda de `cp_destino_2` cambia de `"(reparto — opcional si igual)"` a `"(reparto — obligatorio)"`.
- Se agregan dos campos nuevos debajo del bloque de CP destino 2, dentro de la misma sección condicional:

```html
<div class="grid grid-cols-2 gap-4 mt-4">
    <div>
        <label for="{{ form.cliente_2.id_for_label }}" class="block text-sm font-medium text-slate-700 mb-1.5">
            Cliente (contenedor 2)
            <span class="text-slate-400 font-normal text-xs">(vacío = mismo cliente)</span>
        </label>
        {{ form.cliente_2 }}
        {% if form.cliente_2.errors %}
        <p class="mt-1 text-xs text-red-600" role="alert">{{ form.cliente_2.errors|join:", " }}</p>
        {% endif %}
    </div>
    <div>
        <label for="{{ form.fecha_hora_entrega_2.id_for_label }}" class="block text-sm font-medium text-slate-700 mb-1.5">
            Fecha/hora de entrega (contenedor 2)
            <span class="text-slate-400 font-normal text-xs">(vacío = mismo horario)</span>
        </label>
        {{ form.fecha_hora_entrega_2 }}
        {% if form.fecha_hora_entrega_2.errors %}
        <p class="mt-1 text-xs text-red-600" role="alert">{{ form.fecha_hora_entrega_2.errors|join:", " }}</p>
        {% endif %}
    </div>
</div>
```

No se agregan botones nuevos: el botón "Notificar cliente" existente pasa a notificar 1 o 2 destinatarios según `reparto` (sección 6).

---

## 5. Notificación al cliente — contenido por contenedor

**`config/services/twilio_service.py`**

Nueva función, junto a `_var_info_carga` (línea 75), que arma `{{1}}` para un solo contenedor (usada solo cuando hay reparto):

```python
def _var_info_carga_contenedor(bitacora, numero) -> str:
    """{{1}} para un solo contenedor — usado en notificaciones de reparto."""
    if numero == 2:
        contenedor = bitacora.contenedor_2 or '-'
        peso = bitacora.peso_2 or '-'
        cp_destino = bitacora.cp_destino_2 or '-'
    else:
        contenedor = bitacora.contenedor or '-'
        peso = bitacora.peso or '-'
        cp_destino = bitacora.cp_destino or '-'

    tipo = bitacora.tipo_contenedor or '-'
    especificaciones = f"Tipo {tipo} con peso de {peso}t"

    return f"Contenedor: {contenedor} | Especificaciones: {especificaciones} | Destino Final: CP {cp_destino}"
```

`_var_info_carga` (la versión combinada existente) **no se modifica** — sigue usándose para viajes sin reparto (FULL sin reparto, SENCILLO, LOCAL, LOCAL_FULL).

`enviar_notificacion_bitacora(bitacora, cliente)` **no se modifica** — se sigue usando tal cual para el caso sin reparto.

---

## 6. Notificación al cliente — envío dividido

**`config/services/twilio_service.py`**, nueva función junto a `enviar_notificacion_bitacora`:

```python
def enviar_notificaciones_reparto(bitacora) -> dict:
    """
    Envía dos notificaciones de cliente independientes (una por contenedor)
    para viajes con reparto=True. Cada una usa los datos propios de su
    contenedor (destino, cliente, horario de entrega), con fallback al
    contenedor 1 cuando el campo _2 correspondiente está vacío.

    Returns dict: {'contenedor_1': {...}, 'contenedor_2': {...}}, mismo
    formato de resultado que enviar_notificacion_bitacora en cada entrada.
    """
    resultado = {'contenedor_1': None, 'contenedor_2': None}

    if bitacora.cliente:
        resultado['contenedor_1'] = _enviar_notificacion_contenedor(
            bitacora, numero=1,
            cliente=bitacora.cliente,
            cp_destino=bitacora.cp_destino,
            fecha_entrega=bitacora.fecha_hora_entrega,
        )

    cliente_2 = bitacora.cliente_2 or bitacora.cliente
    if cliente_2:
        resultado['contenedor_2'] = _enviar_notificacion_contenedor(
            bitacora, numero=2,
            cliente=cliente_2,
            cp_destino=bitacora.cp_destino_2,
            fecha_entrega=bitacora.fecha_hora_entrega_2 or bitacora.fecha_hora_entrega,
        )

    return resultado
```

`_enviar_notificacion_contenedor` factoriza el envío WA+email que hoy vive inline en `enviar_notificacion_bitacora` (líneas 119-156), parametrizado por `var1` (vía `_var_info_carga_contenedor`) y usando `cp_destino`/`fecha_entrega` recibidos en vez de leerlos directo de `bitacora`. `enviar_notificacion_bitacora` se refactoriza para llamar a este helper con `_var_info_carga(bitacora)` — sin cambiar su comportamiento observable.

---

## 7. Vista — botón "Notificar cliente"

**`modulos/bitacoras/views.py`**, `enviar_notificacion_cliente` (líneas 368-392):

```python
@login_required
@require_POST
def enviar_notificacion_cliente(request, pk):
    bitacora = get_object_or_404(BitacoraViaje, pk=pk)

    if bitacora.reparto:
        from config.services.twilio_service import enviar_notificaciones_reparto
        resultados = enviar_notificaciones_reparto(bitacora)

        partes = []
        for numero, cliente in ((1, bitacora.cliente), (2, bitacora.cliente_2 or bitacora.cliente)):
            r = resultados[f'contenedor_{numero}']
            if not cliente:
                continue
            if not r:
                partes.append(f"Contenedor {numero} sin cliente asignado.")
                continue
            envios = []
            if r['wa_ok']:
                envios.append('WhatsApp')
            if r['email_ok']:
                envios.append('correo')
            estado = ', '.join(envios) if envios else 'no se pudo enviar'
            partes.append(f"Contenedor {numero} → {cliente.nombre}: {estado}.")

        if partes:
            messages.success(request, ' '.join(partes))
        else:
            messages.error(request, 'No hay clientes asignados para notificar.')
        return redirect('bitacoras:detail', pk=pk)

    # Camino existente, sin reparto — sin cambios
    if not bitacora.cliente:
        messages.error(request, 'Esta bitácora no tiene cliente asignado.')
        return redirect('bitacoras:detail', pk=pk)

    from config.services.twilio_service import enviar_notificacion_bitacora
    resultado = enviar_notificacion_bitacora(bitacora, bitacora.cliente)
    ...  # resto igual a hoy
```

---

## 8. Notificación al operador — sin cambios

`enviar_notificacion_operador` (`twilio_service.py`, líneas 161-210) y la vista `enviar_notificacion_operador` (`views.py`, líneas 395-409) **no se tocan**. El operador sigue recibiendo un único WhatsApp con `_var_info_carga(bitacora)` (info combinada de ambos contenedores) — el reparto no cambia cómo el operador ejecuta ni cómo se le notifica.

---

## 9. Admin

**`modulos/bitacoras/admin.py`**, fieldset de reparto (línea 45):

```python
'fields': ('contenedor_2', 'peso_2', 'sellos_2', 'reparto', 'cliente_2', 'fecha_hora_entrega_2'),
```

---

## 10. Detalle de bitácora

**`templates/bitacoras/bitacora_detail.html`**, junto al bloque condicional de "CP Destino 2 (reparto)" (líneas 320-324) y al de `reparto` (líneas 252-253), se agregan dos `dato-group` condicionales:

```html
{% if bitacora.reparto and bitacora.cliente_2 %}
<div class="dato-group">
    <div class="dato-label">Cliente (contenedor 2)</div>
    <div class="dato-valor">{{ bitacora.cliente_2.nombre }}</div>
</div>
{% endif %}
{% if bitacora.reparto and bitacora.fecha_hora_entrega_2 %}
<div class="dato-group">
    <div class="dato-label">Fecha/Hora de Entrega (contenedor 2)</div>
    <div class="dato-valor">{{ bitacora.fecha_hora_entrega_2|date:"d/m/Y H:i" }}</div>
</div>
{% endif %}
```

---

## 11. Testing (TDD)

- **Modelo/formulario**: `reparto=True` sin `cp_destino_2` falla validación (modelo y formulario); con `cp_destino_2` presente pasa aunque coincida con `cp_destino`; `cliente_2`/`fecha_hora_entrega_2` vacíos no generan error.
- **`_var_info_carga_contenedor`**: contenedor 1 usa `contenedor`/`peso`/`cp_destino`; contenedor 2 usa `contenedor_2`/`peso_2`/`cp_destino_2`.
- **`enviar_notificaciones_reparto`**:
  - `cliente_2` vacío ⇒ ambas notificaciones van al mismo `cliente` (dos envíos independientes, mismo destinatario).
  - `cliente_2` distinto ⇒ cada notificación va a su propio cliente.
  - `fecha_hora_entrega_2` vacío ⇒ el contenedor 2 usa `fecha_hora_entrega`.
  - `bitacora.cliente` vacío ⇒ `resultado['contenedor_1']` es `None`, no lanza excepción.
- **`enviar_notificacion_bitacora`** (refactor): tests existentes siguen pasando sin modificación — mismo comportamiento observable para el caso sin reparto.
- **Vista `enviar_notificacion_cliente`**: con `reparto=True`, arma el mensaje flash reportando ambos contenedores; sin `reparto`, camino existente sin cambios.
- **`enviar_notificacion_operador`**: tests existentes siguen pasando sin modificación (ningún cambio de comportamiento).

---

## Fuera de alcance

- No se modifica `carga_masiva_upload`/`carga_masiva_preview` (Excel) — no captura `cliente_2`/`fecha_hora_entrega_2` por fila; si una bitácora importada necesita reparto con datos distintos por contenedor, se completa después editando la bitácora.
- No se valida que `cp_destino_2` sea diferente de `cp_destino` — coincidir es un caso válido (mismo destino, distinto horario de entrega por espacio).
- No se cambia la notificación al operador ni su plantilla.
- No se agrega un tercer/cuarto contenedor — el modelo sigue limitado a 2 contenedores (contenedor/contenedor_2), como hoy.
- No se toca el reporte de utilidad ni la exportación a Excel (`views.py` líneas ~629-718) — quedan usando `bitacora.reparto` tal como hoy, sin desglosar por cliente.
