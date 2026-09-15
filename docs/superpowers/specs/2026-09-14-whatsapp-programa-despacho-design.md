# Envío por WhatsApp del "Programa de despacho" agrupado por cliente

Fecha: 2026-09-14

## Objetivo

El módulo `modulacion` ya genera un reporte xlsx "Programa de despacho"
(`modulos/modulacion/reportes.py`) con las modulaciones de una fecha,
agrupadas y ordenadas por el alias del cliente. Se necesita poder enviar esa
misma información por WhatsApp a un número interno fijo ("atención a
clientes"), **un mensaje de texto por cada grupo de cliente**, para que el
personal lo reenvíe manualmente al WhatsApp real de cada cliente.

## Decisión de tecnología: WAHA, no Twilio

El proyecto ya tiene dos integraciones de WhatsApp distintas
(`config/services/`):

- **`twilio_service.py`**: usa Twilio Content API con una plantilla
  aprobada de 3 variables fijas (`TWILIO_CONTENT_SID_BITACORA`), para
  notificar a clientes/operadores de una bitácora. Las variables de
  contenido **no admiten saltos de línea reales** (Twilio los rechaza con
  error 21656; el código existente los convierte a `" | "`). No es viable
  para una lista de N contenedores en formato de texto libre.
- **`whatsapp_service.py`**: WAHA (self-hosted), usado hoy para alertas
  internas de combustible y para reenviar reportes
  (`modulos/reportes/management/commands/reenviar_reporte_wa.py`). Envía
  texto libre multilínea a números fijos vía `enviar_mensaje(texto,
  numeros=[...])`, sin restricciones de plantilla.

Se usará **WAHA**, reutilizando `config/services/whatsapp_service.py` tal
cual. No se agrega ninguna dependencia nueva ni se toca `twilio_service.py`.

## Alcance

- Un botón manual en la página existente del reporte
  (`templates/modulacion/reporte_despacho.html`), junto al de descargar
  Excel, para la misma fecha seleccionada.
- Vista previa obligatoria antes de enviar (acción externa con costo/efecto
  en terceros): muestra el texto exacto de cada mensaje y cuántos se van a
  enviar, con botón de confirmación.
- Un mensaje de WhatsApp por grupo de cliente (mismo agrupamiento/orden que
  el xlsx). El grupo "sin cliente" (`—` en el xlsx) **no se envía** por WA.
- Todos los mensajes van al mismo número interno fijo, configurado en
  settings — no al celular de cada `Cliente`.
- Fuera de alcance: envío automático/programado, envío directo al celular
  del cliente, adjuntar el xlsx o una imagen (el usuario prefiere texto
  puro), plantillas Twilio.

## Diseño

### Refactor en `modulos/modulacion/reportes.py`

Se extrae la lógica de filtrar+ordenar+agrupar+numerar modulaciones (hoy
inline dentro de `construir_programa_despacho`) a una función compartida:

```python
def _agrupar_y_numerar(fecha):
    """Devuelve lista de (etiqueta, cliente_id, [(maniobra_num, Modulacion), ...])
    en el mismo orden y con la misma numeración de maniobra que el xlsx."""
```

`construir_programa_despacho` pasa a consumir esta función en vez de tener
el `sorted()`/`groupby()`/contador inline. Esto garantiza que el número de
maniobra que ve el cliente en WhatsApp coincide siempre con el del xlsx
(mismo reporte, misma fecha).

Las funciones puras ya existentes (`_fecha_es`, `_hora_es`, `_texto_hora`,
`_linea_unidad`, `_tipo`, `_etiqueta_grupo`, `_clave_grupo`, `_clave_orden`,
`_SIN_CLIENTE`) se mantienen sin cambios y se reutilizan.

### Nuevo módulo `modulos/modulacion/mensajes_whatsapp.py`

```python
def construir_mensajes_whatsapp(fecha) -> list[tuple[Cliente, str]]:
    """Un (cliente, texto) por cada grupo con cliente asignado.
    Los grupos sin cliente (alias '—') se omiten."""
```

Formato de cada mensaje (texto libre, multilínea — válido en WAHA):

```
*Programa de despacho — 11-sep-26*
*MAZAL TOV IMPORTACIONES, SA DE CV* — 3 maniobra(s)

Maniobra Nº 1
  Contenedor: CSNU6799471
  Terminal: L.C. Terminal Portuaria de Contenedores, S.A. de C.V.
  Agencia: LOGINCO
  Tipo: 40   Peso: 0.00 t
  Operador/Unidad: —
  Carril: NA
  Registro: 10:30 a. m. (HOY)
  Ingreso: 12:00 p. m. (HOY)
  Carga: —
  Sello: NO

Maniobra Nº 2
  Contenedor: CSLU6002657
  ...

Maniobra Nº 3
  Contenedor: CAAU6113805
  Operador/Unidad: OPERADOR DE PRUEBA ECO ECO L20 PLACAS 02BF9Z
  ...

_BitacoraKasu — Modulación_
```

Reglas de formato:
- Encabezado: fecha en español (`_fecha_es`) + etiqueta de cliente + conteo
  de maniobras, igual que el bloque de grupo del xlsx.
- Un bloque `Maniobra Nº {n}` por modulación, mismos campos que las columnas
  del xlsx (contenedor, terminal, agencia, tipo, peso, operador/unidad,
  carril, registro/ingreso/carga, sello). Campo vacío → `—`.
- Si ninguna de las 3 horas está presente: línea única `Horario: CITA
  PENDIENTE` en vez de las 3 líneas de registro/ingreso/carga (igual que el
  xlsx).
- Sin límite de longitud artificial: WAHA no tiene el tope de 1600
  caracteres de Twilio. No se trunca ni se divide el mensaje.

### Settings

```python
WA_PROGRAMA_DESPACHO_NUMERO = env.str('WA_PROGRAMA_DESPACHO_NUMERO', default='')
```

Nombre distinto de "atención a clientes" para no confundirse con
`AtencionClientesView` (tablero de seguimiento aduanal, concepto no
relacionado). Un solo número (no lista), formato compatible con
`_construir_chat_id` de `whatsapp_service.py` (con o sin `+`, se normaliza
solo).

### Vistas y URLs (`modulos/modulacion/`)

Dos endpoints nuevos, mismo estilo que `ReporteProgramaDespachoView` /
`descargar_programa_despacho`:

```python
# urls.py
path('reporte-despacho/whatsapp/preview/', views.previsualizar_whatsapp_despacho,
     name='reporte_despacho_whatsapp_preview'),
path('reporte-despacho/whatsapp/enviar/', views.enviar_whatsapp_despacho,
     name='reporte_despacho_whatsapp_enviar'),
```

- `previsualizar_whatsapp_despacho(request)` — `GET`, `@login_required`.
  Lee `fecha` de querystring (default hoy, mismo `_parse_fecha` ya
  existente). Llama `construir_mensajes_whatsapp(fecha)`. Renderiza
  `modulacion/whatsapp_preview.html`: un bloque `<pre>` por mensaje con el
  texto exacto a enviar, total de mensajes/grupos, y botón "Confirmar y
  enviar" (`POST` a `reporte_despacho_whatsapp_enviar` con `fecha` oculto).
  Si `settings.WA_PROGRAMA_DESPACHO_NUMERO` está vacío: aviso visible y
  botón deshabilitado. Si no hay grupos con cliente para esa fecha: aviso
  "nada que enviar", sin botón.

- `enviar_whatsapp_despacho(request)` — `POST` únicamente, `@login_required`.
  Lee `fecha` del POST. **Recalcula** los mensajes con
  `construir_mensajes_whatsapp(fecha)` (no confía en texto viajando por el
  formulario — evita staleness y manipulación). Por cada `(cliente, texto)`
  llama `whatsapp_service.enviar_mensaje(texto,
  numeros=[settings.WA_PROGRAMA_DESPACHO_NUMERO])`. Acumula OK/fallidos.
  `messages.success` con el conteo de enviados; si hay fallos,
  `messages.error` listando los alias de cliente que fallaron (para
  reenvío manual). Si `WA_PROGRAMA_DESPACHO_NUMERO` vacío: `messages.error`
  y no intenta enviar nada. Redirect a `reporte_despacho` con `?fecha=...`.

### Template

`templates/modulacion/reporte_despacho.html`: se agrega un segundo form
(`GET` a `reporte_despacho_whatsapp_preview`, mismo campo `fecha`) con
botón "Vista previa WhatsApp", mismo estilo visual que el botón "Descargar
Excel" existente.

Nuevo `templates/modulacion/whatsapp_preview.html`: extiende `base.html`,
lista los mensajes en tarjetas con `<pre>` monoespaciado (`white-space:
pre-wrap`), conteo arriba, form de confirmación abajo.

## Manejo de errores

- `whatsapp_service.enviar_mensaje` nunca lanza excepción (ya lo garantiza
  el servicio existente); devuelve `bool`. El envío por grupo es
  independiente — un fallo no detiene los siguientes.
- Sin número configurado: bloqueado en ambas vistas con mensaje claro, no
  se intenta contactar WAHA.
- Sin persistencia/log de auditoría de envíos en esta primera versión (no
  se pidió); los fallos se reportan en la respuesta HTTP vía Django
  messages para reenvío manual desde la misma vista previa.

## Testing

- `modulos/modulacion/tests_reporte.py` (o nuevo `tests_mensajes_whatsapp.py`
  con el mismo estilo): pruebas puras sobre `construir_mensajes_whatsapp`
  verificando agrupación, exclusión del grupo sin cliente, y presencia de
  los campos esperados en el texto (contenedor, etiqueta, número de
  maniobra coincidente con el que produciría el xlsx para la misma fecha).
- Test de vista para `enviar_whatsapp_despacho`: `unittest.mock.patch` sobre
  `modulos.modulacion.views.whatsapp_service.enviar_mensaje` (no pegarle a
  WAHA real), verificando que se llama una vez por grupo de cliente con
  `numeros=[settings.WA_PROGRAMA_DESPACHO_NUMERO]`, y que el resumen de
  éxito/fallo se refleja en los messages de la respuesta.
