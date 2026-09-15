# Envío por WhatsApp (Twilio) del "Programa de despacho" — Diseño

**Fecha:** 2026-09-14
**Módulos:** `modulos/modulacion/` (mensajes + vistas), `config/services/` (cliente Twilio), `config/settings.py`

## Objetivo

Desde la misma pantalla del reporte "Programa de despacho" (`modulacion:reporte_despacho`),
agregar la opción de enviar por WhatsApp (vía Twilio) las modulaciones de una fecha,
**agrupadas por alias de cliente igual que el `.xlsx`**, un mensaje de texto por
grupo, al número interno de **atención a clientes** (fijo, configurado en settings).
Ese número reenvía manualmente cada mensaje al WhatsApp real del cliente
correspondiente.

No es un envío directo al `Cliente.celular` de cada cliente — es un relevo interno.

## Alcance

- Botón "Enviar por WhatsApp" en `reporte_despacho.html`, mismo selector de fecha.
- Vista previa (GET): arma los mensajes, muestra cuántos grupos/mensajes se
  enviarán y el texto exacto de cada uno, con botón "Confirmar y enviar".
- Envío (POST): llama a Twilio una vez por mensaje, resume éxitos/fallos.
- Formato de mensaje: mismos campos que el `.xlsx`, en lista de texto por
  contenedor, con el mismo número de maniobra (trazabilidad entre xlsx y WA).
- Grupos sin cliente asignado (`—` en el xlsx) **no se envían**.
- Sin modelo de auditoría/log de envíos, sin protección de doble-envío (el paso
  de confirmación manual ya cubre eso), sin envío directo al celular del cliente.

---

## Parte 1 — Refactor: agrupación/numeración compartida

`modulos/modulacion/reportes.py` ya agrupa por alias con `sorted(..., key=_clave_orden)`
+ `groupby(key=_clave_grupo)`, numerando `maniobra` de forma corrida sobre las
filas de datos (`construir_programa_despacho`, líneas ~102–186). Se extrae esa
lógica a una función reutilizable para que xlsx y WhatsApp numeren idéntico:

```python
def _agrupar_y_numerar(fecha):
    """
    Devuelve una lista de (primera_modulacion_del_grupo, [(nro_maniobra, modulacion), ...]),
    en el mismo orden/agrupación que el reporte xlsx. `nro_maniobra` es corrido
    sobre TODOS los grupos (no se reinicia por grupo), igual que hoy la columna N.
    """
    modulaciones = sorted(
        Modulacion.objects
        .filter(fecha_modulacion_aduana=fecha)
        .select_related('cliente', 'operador', 'unidad', 'agencia', 'terminal_portuaria'),
        key=_clave_orden,
    )
    grupos = []
    maniobra = 0
    for _clave, grupo_iter in groupby(modulaciones, key=_clave_grupo):
        grupo = list(grupo_iter)
        items = []
        for m in grupo:
            maniobra += 1
            items.append((maniobra, m))
        grupos.append((grupo[0], items))
    return grupos
```

`construir_programa_despacho` se reescribe para iterar `_agrupar_y_numerar(fecha)`
en vez de su propio `sorted`+`groupby`+contador — **mismo comportamiento**, las
pruebas existentes en `tests_reporte.py` no deben cambiar.

Los helpers privados ya existentes se reutilizan (no se duplican):
`_fecha_es`, `_hora_es`, `_texto_hora`, `_linea_unidad`, `_tipo`,
`_etiqueta_grupo`, `_clave_grupo`, `_clave_orden`, `_SIN_CLIENTE`.

---

## Parte 2 — Builder de mensajes — `modulos/modulacion/mensajes_whatsapp.py` (nuevo)

Módulo puro (sin Twilio, sin request/response), igual espíritu que `reportes.py`.

```python
LIMITE_TEXTO = 1500  # margen bajo el límite de 1600 caracteres de WhatsApp/Twilio

def construir_mensajes_whatsapp(fecha) -> list[tuple[Cliente, str]]:
    """
    Un (cliente, texto) por grupo con cliente asignado. Si el texto de un grupo
    excede LIMITE_TEXTO, se parte en varios mensajes ("parte X/Y"), cortando
    siempre entre bloques de maniobra completos, nunca a la mitad de uno.
    Grupos sin cliente (cliente_id is None) se omiten.
    """
```

**Formato de un bloque de maniobra** (mismos campos que las columnas del xlsx):

```
1) Contenedor: CSNU6799471
Terminal: L.C. Terminal Portuaria de Contenedores, S.A. de C.V.
Agencia: LOGINCO | Tipo: 40 | Peso: 0.00
Operador/Unidad: —
Carril: NA
Registro: 10:30 a. m. (HOY) | Ingreso: 12:00 p. m. (HOY)
Sello: NO | Maniobra Nº: 1
```

- `Operador/Unidad`: mismo valor que la columna G del xlsx
  (`f"{operador.nombre}\n{linea_unidad}"` o solo `linea_unidad`, o `'—'` si no
  hay ni operador ni unidad), pero en una sola línea separada por `' — '` en
  vez de salto de línea (WhatsApp respeta `\n` pero se evita romper el bloque).
- `Registro` / `Ingreso`: se listan las horas presentes (`hora_registro`,
  `hora_ingreso`, `hora_carga`) usando `_texto_hora`; las ausentes se omiten de
  la línea; si no hay ninguna, la línea dice `Cita pendiente`.
- `Peso`: `f'{float(m.peso_toneladas):.2f}'` o `'—'` si es `None`.

**Encabezado de mensaje** (una vez por mensaje; se repite si hay "parte X/Y"):

```
*Programa de despacho — 11-sep-26*
*MAZAL TOV IMPORTACIONES, SA DE CV* — 3 maniobra(s)
```

Con partición:

```
*Programa de despacho — 11-sep-26 (parte 1/2)*
*MAZAL TOV IMPORTACIONES, SA DE CV* — 3 maniobra(s)
```

Los bloques de maniobra van separados por una línea en blanco. `*texto*` es la
sintaxis de negritas de WhatsApp (sin HTML/Markdown real).

---

## Parte 3 — Servicio Twilio — `config/services/twilio_whatsapp.py` (nuevo)

Mismo patrón que `config/services/google_maps.py` (`requests` directo, sin
dependencia nueva):

```python
import requests
from django.conf import settings


class TwilioWhatsAppService:
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_ = settings.TWILIO_WHATSAPP_FROM
        self.to_atencion = settings.TWILIO_WHATSAPP_TO_ATENCION
        self.base_url = f'https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json'

    def enviar_mensaje(self, texto):
        if not (self.account_sid and self.auth_token and self.from_ and self.to_atencion):
            return {'success': False, 'error': 'Twilio no configurado (faltan variables de entorno).'}
        try:
            resp = requests.post(
                self.base_url,
                data={'From': self.from_, 'To': self.to_atencion, 'Body': texto},
                auth=(self.account_sid, self.auth_token),
                timeout=10,
            )
            data = resp.json()
            if resp.status_code in (200, 201):
                return {'success': True, 'sid': data.get('sid')}
            return {'success': False, 'error': data.get('message', f'HTTP {resp.status_code}')}
        except requests.RequestException as exc:
            return {'success': False, 'error': str(exc)}
```

`From`/`To` ya llevan el prefijo `whatsapp:` dentro del valor de settings
(ej. `whatsapp:+14155238886`), no se arma en el servicio.

---

## Parte 4 — Settings y `.env`

`config/settings.py`, junto a las variables `GRAPH_*`:

```python
TWILIO_ACCOUNT_SID = env.str('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = env.str('TWILIO_AUTH_TOKEN', default='')
TWILIO_WHATSAPP_FROM = env.str('TWILIO_WHATSAPP_FROM', default='')          # 'whatsapp:+14155238886'
TWILIO_WHATSAPP_TO_ATENCION = env.str('TWILIO_WHATSAPP_TO_ATENCION', default='')  # 'whatsapp:+521XXXXXXXXXX'
```

`.env` (documentado en `CLAUDE.md`, sección "Environment Variables"):

```
# Twilio WhatsApp — envío del Programa de despacho a atención a clientes
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_WHATSAPP_TO_ATENCION=whatsapp:+521XXXXXXXXXX
```

---

## Parte 5 — Vistas y URLs

`modulos/modulacion/views.py`, junto a `ReporteProgramaDespachoView`:

```python
class WhatsAppPreviewView(LoginRequiredMixin, TemplateView):
    """Muestra los mensajes que se enviarían para una fecha, antes de confirmar."""
    template_name = 'modulacion/whatsapp_preview.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        fecha = _parse_fecha(self.request.GET.get('fecha')) or timezone.localdate()
        ctx['fecha'] = fecha.isoformat()
        ctx['mensajes'] = construir_mensajes_whatsapp(fecha)  # [(cliente, texto), ...]
        return ctx


@login_required
@require_POST
def enviar_whatsapp_despacho(request):
    fecha = _parse_fecha(request.POST.get('fecha')) or timezone.localdate()
    mensajes = construir_mensajes_whatsapp(fecha)
    servicio = TwilioWhatsAppService()
    ok, fallos = 0, []
    for cliente, texto in mensajes:
        resultado = servicio.enviar_mensaje(texto)
        if resultado['success']:
            ok += 1
        else:
            fallos.append((cliente.etiqueta, resultado['error']))
    if ok:
        messages.success(request, f'{ok} mensaje(s) de WhatsApp enviado(s).')
    for etiqueta, error in fallos:
        messages.error(request, f'{etiqueta}: {error}')
    if not mensajes:
        messages.warning(request, 'No hay modulaciones con cliente para esa fecha.')
    return redirect(f"{reverse('modulacion:reporte_despacho')}?fecha={fecha.isoformat()}")
```

`urls.py`, junto a las rutas de `reporte-despacho`:

```python
path('reporte-despacho/whatsapp/', views.WhatsAppPreviewView.as_view(), name='reporte_despacho_whatsapp_preview'),
path('reporte-despacho/whatsapp/enviar/', views.enviar_whatsapp_despacho, name='reporte_despacho_whatsapp_enviar'),
```

---

## Parte 6 — Templates

`templates/modulacion/reporte_despacho.html`: agregar un segundo botón junto al
de "Descargar Excel", que enlaza (GET, no submit) a la vista previa:

```html
<a href="{% url 'modulacion:reporte_despacho_whatsapp_preview' %}?fecha={{ fecha }}"
   class="px-4 py-2 text-sm font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg hover:bg-emerald-100 transition min-h-[44px] inline-flex items-center">
    Enviar por WhatsApp
</a>
```

`templates/modulacion/whatsapp_preview.html` (nuevo): extiende `base.html`.
Título "Programa de despacho — WhatsApp", fecha mostrada, y por cada
`(cliente, texto)` de `mensajes` una caja con `<pre>` (fuente monoespaciada,
`whitespace-pre-wrap`) mostrando el texto exacto que se enviará. Al final,
conteo "`{{ mensajes|length }}` mensaje(s) a `{{ TWILIO_WHATSAPP_TO_ATENCION }}`"
(nota: el número de destino no se expone en el contexto por defecto — si se
quiere mostrar, agregar `ctx['numero_destino'] = settings.TWILIO_WHATSAPP_TO_ATENCION`
en la vista) y un `<form method="post" action="{% url 'modulacion:reporte_despacho_whatsapp_enviar' %}">`
con `{% csrf_token %}`, `<input type="hidden" name="fecha" value="{{ fecha }}">`
y botón "Confirmar y enviar". Si `mensajes` está vacío, mensaje
"No hay modulaciones con cliente para esta fecha" sin el formulario de envío.

---

## Estructura de archivos

| Archivo | Acción |
|---|---|
| `modulos/modulacion/reportes.py` | Modificar — extraer `_agrupar_y_numerar(fecha)`, usarla en `construir_programa_despacho` |
| `modulos/modulacion/mensajes_whatsapp.py` | Crear — `construir_mensajes_whatsapp()` + formateo |
| `config/services/twilio_whatsapp.py` | Crear — `TwilioWhatsAppService` |
| `config/settings.py` | Modificar — 4 variables `TWILIO_*` |
| `modulos/modulacion/views.py` | Modificar — `WhatsAppPreviewView`, `enviar_whatsapp_despacho` |
| `modulos/modulacion/urls.py` | Modificar — 2 rutas |
| `templates/modulacion/reporte_despacho.html` | Modificar — botón "Enviar por WhatsApp" |
| `templates/modulacion/whatsapp_preview.html` | Crear |
| `CLAUDE.md` | Modificar — documentar variables `TWILIO_*` en `.env` |
| `modulos/modulacion/tests_mensajes_whatsapp.py` | Crear — pruebas del builder |
| `modulos/modulacion/tests_reporte.py` | Sin cambios de comportamiento esperados (regresión) |

---

## Testing

### `_agrupar_y_numerar` / regresión de `construir_programa_despacho`
- Suite existente `tests_reporte.py` sigue en verde sin modificar sus asserts
  (mismo orden, mismos números de maniobra, mismas filas-encabezado de grupo).

### `construir_mensajes_whatsapp(fecha)`
- Modulaciones de 2 clientes con alias + 1 grupo sin cliente en la misma fecha
  → 2 tuplas `(cliente, texto)`, el grupo sin cliente no aparece.
- El texto de un grupo trae el encabezado `*Programa de despacho — <fecha_es>*`
  y `*<etiqueta>* — N maniobra(s)`.
- Cada bloque de maniobra usa el mismo `nro_maniobra` que produciría
  `construir_programa_despacho` para esa misma modulación (columna N del xlsx).
- Modulación sin operador/unidad → línea `Operador/Unidad` no revienta
  (usa `'—'` o el valor disponible).
- Ninguna hora presente → línea `Cita pendiente`.
- Un grupo con texto que excede `LIMITE_TEXTO` (construir un cliente con
  suficientes maniobras) → se parte en ≥2 mensajes, cada uno `<= 1600` chars,
  encabezados con `(parte 1/N)`, `(parte 2/N)`, ningún bloque de maniobra
  partido a la mitad.
- Fecha sin modulaciones → lista vacía.

### `TwilioWhatsAppService.enviar_mensaje`
- Con `requests.post` mockeado devolviendo 201 → `{'success': True, 'sid': ...}`.
- Con `requests.post` mockeado devolviendo 400 → `{'success': False, 'error': ...}` (no lanza excepción).
- `requests.RequestException` (timeout/conexión) → `{'success': False, 'error': ...}`.
- Settings vacíos (sin configurar) → `{'success': False, 'error': ...}` sin llamar a `requests.post`.

### Vistas
- `GET reporte_despacho_whatsapp_preview` sin login → 302.
- Con login y modulaciones con cliente → 200, el HTML trae el texto de cada
  mensaje.
- Sin modulaciones para la fecha → 200, sin formulario de envío.
- `POST reporte_despacho_whatsapp_enviar` (con `requests.post` mockeado
  éxito) → redirect a `reporte_despacho?fecha=...`, mensaje de éxito con la
  cuenta correcta.
- Mismo POST con un mensaje fallando (mock devuelve error en una llamada) →
  redirect, mensaje de éxito parcial + mensaje de error con la etiqueta del
  cliente.
- `POST` sin `fecha` → usa hoy, no 500.
- `GET` a `enviar_whatsapp_despacho` → 405 (`require_POST`).

### Regresión
- Suite completa de `modulos.modulacion` en verde.
- `manage.py check` sin errores; `makemigrations --check --dry-run` sin cambios
  pendientes (esta feature no toca modelos, no hay migración nueva).

---

## Fuera de alcance

- Envío directo al `Cliente.celular` (salta el paso humano de atención a
  clientes) — fase futura si se decide.
- Disparo automático (p. ej. tras la importación LCTPC) — solo botón manual
  por ahora.
- Modelo de auditoría/log de mensajes enviados (folio, timestamp, resultado).
- Protección de doble-envío / idempotencia — el paso de confirmación manual
  cubre el caso de uso actual.
- Plantillas de WhatsApp pre-aprobadas (Message Templates) — se asume que el
  número de atención a clientes mantiene la ventana de conversación de 24h
  abierta con el número de Twilio, o que se usa el sandbox de Twilio en
  desarrollo. Si Twilio rechaza el envío por falta de plantilla aprobada
  (`error 63016` u similar), es un problema operativo de configuración de
  Twilio, no de este código — el mensaje de error se muestra tal cual llega
  de la API vía `messages.error`.
- Envío de imagen/tabla — se confirmó texto plano (WhatsApp free-form solo
  soporta texto en este flujo).
