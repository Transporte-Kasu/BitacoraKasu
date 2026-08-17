# Notificación de extracción de contenedor (DODA / KASU) + envío a Modulación (BitacoraKasu)

## Contexto

Cuando LOGINCO genera un DODA (Documento de Operación para Despacho Aduanero) cuyo transportista asignado
es Transportes Kasu (`SAAIO_DODA.CVE_CAAT = '3B74'`, confirmado contra `SAAIC_CAAT` donde
`CVE_CAAT=KASU / COD_CAAT=3B74 / NOM_CAAT=TRANSPORTES KASU`), el capturista responsable
(`SAAIO_DODA.CVE_CAPT`) debe iniciar manualmente el trámite de solicitud de extracción del contenedor.
Hoy ese aviso no existe: nadie en HAL9MIL recibe una notificación automática cuando esto ocurre, y no hay
forma de avisar al equipo de **BitacoraKasu** (proyecto Django independiente en
`/home/tony/Developer/BitacoraKasu`, empresa Transportes Kasu) para que programe la recolección del
contenedor (módulo nuevo "Modulación" en ese sistema).

Este plan cubre **solo el lado de Proyecto_HAL9MIL**: sincronizar los DODA relevantes, vincular usuarios
de Django con la clave de capturista de CASA, disparar automáticamente el correo al capturista con el
Pedimento+DODA listos para imprimir, y enviar (push) los datos de modulación a BitacoraKasu vía API. El
diseño del lado receptor en BitacoraKasu (nuevo modelo "Modulación", su UI y su relación con
`BitacoraViaje`/Patio Esperanza) se deja para un plan separado en ese repositorio; aquí solo se fija el
contrato del payload que HAL9MIL enviará.

## Esquema CASA relevante (ya documentado en `bd_casa_pedimentos.md`)

- `SAAIO_DODA` (`ID_DODA` PK): `NUM_DODA`, `CVE_CAAT`, `CVE_CAPT`, `FEC_DODAE`, `FEC_BAJA`, `PAT_AGEN`.
- `SAAIO_DODADO` (`ID_DODA`+`CONS_ID` PK): liga el DODA con `NUM_REFE` (una DODA puede cubrir varias
  referencias/pedimentos).
- `SAAIO_IDEPED` (`NUM_REFE`+`NUM_IDE` PK): con `CVE_IDEN='CR'`, `COM_IDEN` contiene la clave del recinto
  fiscalizado (terminal portuaria) → se cruza con `SAAIC_REFIS.CVE_REFI` para obtener `NOM_REFI`.
- `SAAIC_REFIS` (`CVE_REFI` PK): catálogo de terminales/recintos, campo `NOM_REFI`.
- `SAAIO_CONTEN` (`NUM_REFE`+`NUM_CONT` PK): contenedor y su tipo (`CVE_CONT`) — **ya sincronizado** al
  modelo `Contenedor` existente vía `NUM_REFE`.
- `SAAIC_CAAT` (`CVE_CAAT` PK): catálogo transportista, `COD_CAAT='3B74'` = Transportes Kasu.

No se encontró una tabla `SAAIO_DODADVE` en el esquema documentado; lo más cercano es `SAAIO_DODADCO`
(campo `CAD_ORIG`, texto libre con contenedores/sellos separados por `|`, no estructurado). Para
contenedor+sello se usará la vía ya sincronizada `SAAIO_CONTEN → Contenedor` en vez de parsear ese blob.

## Estado actual del código (confirmado en exploración)

- No hay conexión ORM en vivo a Firebird/CASA. El patrón es **ETL batch**: `sync_agent/sync_agent.py`
  (agente externo en Windows, junto al `.GDB`) lee con `fdb` y hace `POST /api/sync/` a
  `referencias/sync_views.py`; alternativamente `referencias/management/commands/import_firebird.py`
  hace lo mismo localmente. Ambos hacen `update_or_create` sobre modelos Django normales
  (`Referencia`, `Contenedor`, `GuiaBL`).
- `django.contrib.auth.models.User` es el modelo de usuario (no hay `AUTH_USER_MODEL` custom). No existe
  ningún vínculo entre `User` y `CVE_CAPT`; hoy `Referencia.cve_capturista`/`nombre_capturista` son solo
  texto plano importado.
- Envío de correo con adjuntos ya resuelto en `finanzas/cuenta_gastos_envio.py` (SendGrid Web API,
  `render_to_string` + adjunto en base64, registro en modelo de bitácora de envío, manejo de bounces vía
  webhook). Generación de PDF ya usa `reportlab.pdfgen.canvas` + `pypdf` en ese mismo archivo.
- Llamadas HTTP salientes autenticadas a un servicio externo ya existen en `finanzas/pac_client.py`
  (patrón: `requests.post` con timeout `(10, 30)`, manejo de token, excepciones propias
  `PACError`/`PACConfigError`) — este es el patrón a replicar para el push a BitacoraKasu.
- `CVE_CONT_TIPO` (mapa de `CVE_CONT` → `'20DC'/'40HC'/...`) ya vive en `referencias/models.py` y se
  reutiliza tal cual.

## Diseño

### 1. Modelos nuevos en `referencias/models.py`

```python
class Doda(models.Model):
    id_doda        = models.IntegerField(unique=True, db_index=True)   # SAAIO_DODA.ID_DODA
    num_doda       = models.CharField(max_length=34, blank=True)
    patente        = models.CharField(max_length=10, db_index=True)
    cve_caat       = models.CharField(max_length=6, blank=True, db_index=True)
    cve_capt       = models.CharField(max_length=20, blank=True)
    terminal_cve   = models.CharField(max_length=4, blank=True)   # SAAIC_REFIS.CVE_REFI
    terminal_nombre = models.CharField(max_length=70, blank=True) # SAAIC_REFIS.NOM_REFI
    fecha_doda     = models.DateTimeField(null=True, blank=True)  # FEC_DODAE
    fecha_baja     = models.DateTimeField(null=True, blank=True)  # FEC_BAJA
    notificado_en  = models.DateTimeField(null=True, blank=True)
    modulacion_enviada_en = models.DateTimeField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['cve_caat', 'fecha_baja'])]


class DodaReferencia(models.Model):
    doda       = models.ForeignKey(Doda, on_delete=models.CASCADE, related_name='referencias_doda')
    referencia = models.ForeignKey(Referencia, on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='dodas')
    num_refe   = models.CharField(max_length=15)   # por si aún no existe la Referencia localmente
    cons_id    = models.IntegerField()

    class Meta:
        unique_together = [('doda', 'cons_id')]
```

Sólo se sincronizan/crean `Doda` cuyo `CVE_CAAT == '3B74'` y `FEC_BAJA` sea nulo (DODA vigente, no dado
de baja) — el filtro se aplica en la query origen (agente/import), no después.

### 2. Vincular `User` de Django con capturista (`core/models.py`, hoy vacío)

```python
class PerfilUsuario(models.Model):
    user             = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    cve_capturista   = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    email_alterno    = models.EmailField(blank=True)  # override opcional del email de User
```

Nuevo `core/capturistas.py`:

```python
def resolver_destinatario(cve_capt: str) -> tuple[str, str] | None:
    """Devuelve (email, nombre) del capturista, o None si no hay perfil vinculado."""
```

Fallback si no hay `PerfilUsuario` para ese `cve_capt`: usar `settings.MODULACION_FALLBACK_EMAILS` (lista,
mismo patrón que `IA_ALERTAS_COMBUSTIBLE_EMAILS` en BitacoraKasu) y loggear un warning para que alguien
capture la relación faltante en el admin.

Registrar `PerfilUsuario` en `core/admin.py` (o inline en `UserAdmin`) para que un administrador asigne
`cve_capturista` a cada usuario ("ANGELICA", "ISAAC", "SUJEY", etc., tal como aparecen en los datos de
muestra de CASA).

### 3. Extender el pipeline de sync para traer DODA

Replicar el patrón ya usado para agregar campos al pipeline (p. ej. `fir_elec`, `num_partidas`): tres
puntos a tocar en paralelo.

- **`sync_agent/sync_agent.py`**: nueva query que hace `JOIN` de `SAAIO_DODA` + `SAAIO_DODADO` +
  `SAAIO_IDEPED` (`CVE_IDEN='CR'`) + `SAAIC_REFIS`, con `WHERE CVE_CAAT = '3B74' AND FEC_BAJA IS NULL`.
  Agrega un bloque `"dodas": [...]` al payload existente del `POST /api/sync/` (mismo nivel que
  `"referencias"`/`"contenedores"`/`"guias"`).
- **`referencias/sync_views.py`**: nueva función `_upsert_dodas(dodas, stats, error_msgs)`, análoga a
  `_upsert_contenedores` — `update_or_create(id_doda=..., defaults=...)`, crea/actualiza
  `DodaReferencia` por `cons_id`, e intenta enlazar `referencia` si ya existe una `Referencia` con ese
  `num_refe`. Devuelve la lista de `Doda` recién creadas (`created=True`) para pasarlas al paso 4.
- **`referencias/management/commands/import_firebird.py`**: mismo query/columnas para el path de import
  batch, por paridad con el agente.

Nota aparte: si `peso_bruto` (toneladas) no está ya en `Referencia`/`Contenedor` — verificar durante la
implementación — agregarlo siguiendo el mismo patrón (`CTRAO_EMBAR.PES_BRUT` o
`SAAIO_PEDIME.PES_BRUT`), porque el payload de Modulación hacia BitacoraKasu lo requiere.

### 4. Disparo automático: correo al capturista + push a BitacoraKasu

Nuevo módulo `referencias/modulacion.py` (mismo espíritu que `finanzas/cuenta_gastos_envio.py` +
`finanzas/pac_client.py`), con una función `procesar_dodas_nuevas(dodas_creadas)` invocada desde
`sync_views.sync_endpoint` justo después de `_upsert_dodas`, dentro del mismo `transaction.atomic()` pero
con los efectos de red (email/HTTP) ejecutados **después** del commit (o en un `transaction.on_commit`)
para no bloquear ni corromper el sync si Firebird tiene más lotes.

Por cada `Doda` nueva:

1. `core.capturistas.resolver_destinatario(doda.cve_capt)`.
2. Generar PDF "Pedimento + DODA para imprimir" con `reportlab.pdfgen.canvas` (mismo import que ya usa
   `finanzas/cuenta_gastos_envio.py`), usando: `num_doda`, `terminal_nombre`, y por cada
   `DodaReferencia.referencia` — `num_pedimento`, `nombre_cliente`, contenedores (`Referencia.contenedores`).
3. Enviar correo (reusar patrón SendGrid Web API de `enviar_cuenta_gastos`: `Mail`/`Attachment`/
   `CustomArg`, adjuntando el PDF en base64) pidiendo iniciar la solicitud de extracción del contenedor.
   Registrar el envío en un nuevo modelo ligero `EnvioModulacion` (estado `ENVIADO`/`ERROR`, `sg_message_id`
   opcional, `doda` FK) — mismo espíritu que `LogSync`/`NotificacionCuentaGastos`.
4. Push a BitacoraKasu: nuevo `referencias/bitacorakasu_client.py`, mismo patrón que `finanzas/pac_client.py`
   (`requests.post`, timeout `(10, 30)`, excepción propia `BitacoraKasuError`). Un `POST` por cada
   contenedor asociado a las referencias del DODA:

   ```json
   {
     "agencia": "LOGINCO",
     "terminal_portuaria": "<Doda.terminal_nombre>",
     "tipo_contenedor": "<CVE_CONT_TIPO[Contenedor.tipo]>",
     "peso_toneladas": "<peso de la referencia>",
     "contenedor": "<Contenedor.num_cont>",
     "cliente": "<Referencia.nombre_cliente>",
     "num_pedimento": "<Referencia.num_pedimento>",
     "num_doda": "<Doda.num_doda>"
   }
   ```

   Autenticación con header `Authorization: Token <BITACORAKASU_API_TOKEN>` (mismo esquema que ya usa
   `SYNC_SECRET_KEY` en `sync_views.py`, pero aquí HAL9MIL es el cliente). Actualiza
   `EnvioModulacion.push_estado` con el resultado.

   Fallas de email o de push **no** deben interrumpir el sync ni marcarse como error fatal: se registran en
   `EnvioModulacion` con estado `ERROR` para reintento manual vía un management command
   `reintentar_modulacion` (recorre `EnvioModulacion` con estado `ERROR` y reintenta).

### 5. Configuración nueva (`hal9mil/settings.py` + `.env`)

```python
CVE_CAAT_KASU = '3B74'
BITACORAKASU_MODULACION_URL = os.getenv('BITACORAKASU_MODULACION_URL', '')
BITACORAKASU_API_TOKEN      = os.getenv('BITACORAKASU_API_TOKEN', '')
MODULACION_FALLBACK_EMAILS  = os.getenv('MODULACION_FALLBACK_EMAILS', '').split(',')
```

### 6. Admin mínimo

Registrar `Doda`, `DodaReferencia`, `PerfilUsuario`, `EnvioModulacion` en sus respectivos `admin.py`
(`list_display`, filtros por `cve_caat`, `notificado_en`, `push_estado`) para poder auditar y reintentar
manualmente sin entrar a la shell.

### 7. Fuera de alcance (a planear después, en el repo BitacoraKasu)

El endpoint receptor (`POST /api/modulacion/` o similar) y el nuevo modelo `Modulacion` en
`/home/tony/Developer/BitacoraKasu`: campo `agencia` (select dinámico que arranca con "LOGINCO" y crece
conforme se capturan agencias nuevas), `terminal_portuaria`, `tipo_contenedor`, `peso_toneladas`,
`contenedor`, `cliente`, y su flujo posterior — pasar a `BitacoraViaje` (ya existe en
`modulos/bitacoras/models.py`) o marcar llegada a "Patio Esperanza" para recolección por Transportes Kasu
u otro transporte. El contrato de payload de la sección 4 debe respetarse desde ese lado.

## Pruebas (TDD)

- `referencias/tests.py`: tests para `_upsert_dodas` (creación/actualización, filtro `CVE_CAAT`, ligado a
  `DodaReferencia`), siguiendo el estilo de los tests existentes de sync.
- `core/tests.py` (crear si no existe): tests de `resolver_destinatario` (con/sin `PerfilUsuario`,
  fallback a `MODULACION_FALLBACK_EMAILS`).
- `referencias/test_modulacion.py`: mock de `requests.post` (para `bitacorakasu_client`) y mock del cliente
  SendGrid (mismo patrón que `finanzas/test_cuenta_gastos_envio.py`) — sin llamadas reales de red en tests.
- `python manage.py makemigrations --check` y `python manage.py test` deben pasar antes de cerrar la rama.

## Verificación end-to-end

- Con el servidor de desarrollo corriendo y `EMAIL_BACKEND` en modo consola, simular un `POST /api/sync/`
  con un DODA nuevo `cve_caat='3B74'` (payload de prueba) y confirmar: se crea `Doda`+`DodaReferencia`, se
  imprime el correo en consola con el PDF adjunto, y se ve el intento de push a BitacoraKasu (mockeado o
  apuntando a `BITACORAKASU_MODULACION_URL` de prueba) reflejado en `EnvioModulacion`.
