# App Vacíos — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nuevo módulo `modulos/vacios` que rastrea el retorno de contenedores vacíos a la naviera: se crea solo al registrarse la entrega de un contenedor al cliente, se mueve por 4 estados hasta la entrega a la naviera, registra retrasos con aviso automático por correo a la agencia aduanal, permite reasignar unidad/operador con causa, y alimenta un reporte semanal.

**Architecture:** App Django estándar con la misma estructura que `modulos/modulacion`. Un `post_save` sobre `bitacoras.BitacoraViaje` crea un `Vacio` por contenedor entregado. Las transiciones de estado son acciones manuales (`@require_POST`). Los reportes viven en `modulos/reportes/generadores/vacios.py` y se enganchan al comando `generar_reportes` y a `ConfiguracionReporte`, igual que los de modulación.

**Tech Stack:** Django 5.2.7, Python 3.14, PostgreSQL (prod) / SQLite in-memory para tests (`test_settings.py`), plantillas con clases Tailwind (mismo estilo que `templates/modulacion/`), correo vía backend SendGrid ya configurado (`django.core.mail`).

## Global Constraints

- Django **5.2.7**, Python **3.14**. No agregar dependencias nuevas.
- Todo en **español** (`verbose_name`, choices display, comentarios, UI, mensajes). `LANGUAGE_CODE='es-mx'`, `TIME_ZONE='America/Mexico_City'`.
- Folio del vacío: **`VAC-YYYYMMDD-XXX`** (consecutivo por día, 3 dígitos), agrupado por la fecha de `fecha_entrega_cliente`, con el mismo patrón de reintento anti-colisión de `Modulacion.save()`.
- Signals registrados en `apps.py` → `ready()` (patrón de `modulos/combustible/apps.py`).
- Tests se corren con: `python manage.py test modulos.vacios --settings=test_settings -v 2` (SQLite en memoria; la BD por defecto es PostgreSQL remoto y no sirve para tests).
- Estados del `Vacio`: `POR_VACIAR` → `EN_PATIO_ESPERANZA` → `ASIGNADO` → `ENTREGADO_NAVIERA`.
- El tramo Patio Esperanza → naviera **NO** genera `BitacoraViaje`; se registra en campos del propio `Vacio`.
- Aviso a la agencia: **solo correo**. Nunca lanzar excepción que tumbe la request; registrar fallos con `logging`.
- Un `Vacio` por **contenedor** (viaje FULL con dos entregas → dos `Vacio`).
- El signal **solo crea**, nunca borra ni revierte.

## Estructura de archivos

**Nuevos:**

| Archivo | Responsabilidad |
|---------|-----------------|
| `modulos/vacios/__init__.py` | Paquete. |
| `modulos/vacios/apps.py` | `VaciosConfig`, `ready()` importa signals. |
| `modulos/vacios/models.py` | `Naviera`, `Vacio`, `RetrasoVacio`, `CambioOperadorVacio`. |
| `modulos/vacios/signals.py` | `post_save` sobre `BitacoraViaje` → crea `Vacio`. |
| `modulos/vacios/services.py` | `operadores_libres()`. |
| `modulos/vacios/notificaciones.py` | `notificar_retraso_agencia(retraso)`. |
| `modulos/vacios/forms.py` | Forms de asignación, reasignación, retraso, edición, `Naviera`. |
| `modulos/vacios/views.py` | Dashboard, list, detail, update, delete, acciones de estado, CRUD `Naviera`. |
| `modulos/vacios/urls.py` | `app_name='vacios'`. |
| `modulos/vacios/admin.py` | Admin de los 4 modelos. |
| `modulos/vacios/tests.py` | Suite completa. |
| `modulos/vacios/migrations/__init__.py` + migraciones | Esquema. |
| `modulos/reportes/generadores/vacios.py` | `generar_entregas_por_operador`, `generar_retrasos`, `GENERADORES`. |
| `templates/vacios/dashboard.html` | Dashboard. |
| `templates/vacios/vacio_list.html` | Lista con filtro mes/año. |
| `templates/vacios/vacio_detail.html` | Detalle + acciones. |
| `templates/vacios/vacio_form.html` | Edición (naviera, agencia, fechas). |
| `templates/vacios/vacio_confirm_delete.html` | Confirmación de borrado. |
| `templates/vacios/asignar_unidad_operador.html` | Asignar/reasignar. |
| `templates/vacios/registrar_retraso.html` | Form de retraso. |
| `templates/vacios/naviera_list.html` / `naviera_form.html` / `naviera_confirm_delete.html` | CRUD catálogo. |
| `templates/vacios/email/retraso_agencia.html` / `retraso_agencia.txt` | Cuerpo del correo. |
| `templates/reportes/entregas_vacios_por_operador.html` | Vista en pantalla del reporte. |

**Modificados:**

| Archivo | Cambio |
|---------|--------|
| `config/settings.py` | `'modulos.vacios'` en `INSTALLED_APPS`. |
| `config/urls.py` | `path('vacios/', include('modulos.vacios.urls'))`. |
| `config/views.py` | Conteos de vacíos en `IndexView`. |
| `templates/base.html` | Enlace de navegación a Vacíos. |
| `templates/index.html` | Tarjeta de vacíos. |
| `modulos/modulacion/models.py` | `Agencia.email_contacto` + migración. |
| `modulos/modulacion/forms.py` | `email_contacto` en `AgenciaForm`. |
| `modulos/reportes/models.py` | `MODULO_CHOICES` + `TIPO_CHOICES` + migración. |
| `modulos/reportes/generadores/narrativa.py` | `_NOMBRES_REPORTE` de los 2 tipos. |
| `modulos/reportes/management/commands/generar_reportes.py` | `**gen_vacios.GENERADORES`. |
| `modulos/reportes/views.py` | `EntregasVaciosPorOperadorView`. |
| `modulos/reportes/urls.py` | Ruta de la vista. |
| `templates/reportes/historial.html` | Enlace a la vista. |
| `CLAUDE.md` | Documentar la app, su signal y sus reportes. |

---

## Task 1: Scaffold de la app, modelos y migraciones

**Files:**
- Create: `modulos/vacios/__init__.py`, `modulos/vacios/apps.py`, `modulos/vacios/models.py`, `modulos/vacios/admin.py`, `modulos/vacios/migrations/__init__.py`
- Create: `modulos/vacios/tests.py`
- Modify: `config/settings.py` (INSTALLED_APPS)
- Modify: `modulos/modulacion/models.py` (campo `email_contacto`)
- Modify: `modulos/modulacion/forms.py` (`AgenciaForm.Meta.fields`)

**Interfaces:**
- Produces:
  - `modulos.vacios.models.Naviera(nombre, direccion_retorno, activo, created_at)`
  - `modulos.vacios.models.Vacio` con campos y `ESTADO_CHOICES` (ver abajo); `save()` autogenera `folio` `VAC-YYYYMMDD-XXX`.
  - `modulos.vacios.models.RetrasoVacio(vacio, tipo, motivo, fecha_estimada_nueva, notificado_agencia, fecha_notificacion, creado_por, created_at)` con `TIPO_CHOICES = [('MANIOBRA', ...), ('RETORNO', ...)]`
  - `modulos.vacios.models.CambioOperadorVacio(vacio, unidad_saliente, unidad_entrante, operador_saliente, operador_entrante, causa, motivo, creado_por, created_at)` con `CAUSA_CHOICES = [('NO_CONFIRMA', ...), ('SE_NIEGA', ...), ('ULTIMA_HORA', ...)]`
  - `modulos.modulacion.models.Agencia.email_contacto` (`EmailField`, `blank=True`)

- [ ] **Step 1: Crear el paquete de la app**

Create `modulos/vacios/__init__.py` (vacío) y `modulos/vacios/migrations/__init__.py` (vacío).

Create `modulos/vacios/apps.py`:

```python
from django.apps import AppConfig


class VaciosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modulos.vacios'
    verbose_name = 'Vacíos'

    def ready(self):
        import modulos.vacios.signals  # noqa: F401
```

Create `modulos/vacios/signals.py` con un stub (se implementa en Task 2), para que `ready()` no falle:

```python
"""Señales del módulo Vacíos. La lógica de creación automática se implementa en Task 2."""
```

- [ ] **Step 2: Registrar la app en settings**

Modify `config/settings.py` — en `INSTALLED_APPS`, después de `'modulos.modulacion',`:

```python
    'modulos.modulacion',
    'modulos.vacios',
```

- [ ] **Step 3: Agregar `email_contacto` a `Agencia`**

Modify `modulos/modulacion/models.py` — en la clase `Agencia`, después del campo `activo`:

```python
    activo = models.BooleanField(default=True, verbose_name="Activo")
    email_contacto = models.EmailField(
        blank=True,
        verbose_name="Correo de contacto",
        help_text="Destino de los avisos automáticos de retraso de vacíos.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
```

Modify `modulos/modulacion/forms.py` — en `AgenciaForm.Meta`:

```python
    class Meta:
        model = Agencia
        fields = ['nombre', 'email_contacto', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la agencia'}),
            'email_contacto': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'avisos@agencia.com'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
```

- [ ] **Step 4: Escribir `modulos/vacios/models.py`**

```python
from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone


class Naviera(models.Model):
    """Línea naviera a la que se retorna el contenedor vacío."""
    nombre = models.CharField(max_length=120, unique=True, verbose_name="Nombre")
    direccion_retorno = models.TextField(
        blank=True,
        verbose_name="Dirección / patio de retorno",
    )
    activo = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Naviera"
        verbose_name_plural = "Navieras"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Vacio(models.Model):
    """
    Un contenedor entregado a un cliente que debe vaciarse y retornar a la
    naviera. Se crea automáticamente al registrarse la fecha de entrega del
    contenedor en su BitacoraViaje (ver signals.py). Un registro = un
    contenedor (un viaje FULL con dos entregas produce dos Vacio).
    """
    NUMERO_CONTENEDOR_CHOICES = [('1', 'Contenedor 1'), ('2', 'Contenedor 2')]
    TIPO_CONTENEDOR_CHOICES = [('20', '20 pies'), ('40', '40 pies')]

    ESTADO_CHOICES = [
        ('POR_VACIAR', 'Por vaciar (entregado al cliente)'),
        ('EN_PATIO_ESPERANZA', 'En Patio Esperanza (vacío disponible)'),
        ('ASIGNADO', 'Operador asignado'),
        ('ENTREGADO_NAVIERA', 'Entregado a la naviera'),
    ]

    folio = models.CharField(max_length=20, unique=True, editable=False)

    bitacora_viaje = models.ForeignKey(
        'bitacoras.BitacoraViaje',
        on_delete=models.PROTECT,
        related_name='vacios',
        verbose_name="Bitácora de viaje",
    )
    numero_contenedor = models.CharField(
        max_length=1,
        choices=NUMERO_CONTENEDOR_CHOICES,
        default='1',
        verbose_name="Contenedor del viaje",
    )
    contenedor = models.CharField(max_length=50, verbose_name="Contenedor")
    cliente = models.ForeignKey(
        'bitacoras.Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vacios',
        verbose_name="Cliente",
    )
    tipo_contenedor = models.CharField(
        max_length=2,
        choices=TIPO_CONTENEDOR_CHOICES,
        default='40',
        verbose_name="Tipo de contenedor",
    )
    agencia = models.ForeignKey(
        'modulacion.Agencia',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vacios',
        verbose_name="Agencia aduanal",
        help_text="Destino del aviso de retraso. Se auto-llena si el viaje vino de Modulación.",
    )
    naviera = models.ForeignKey(
        Naviera,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vacios',
        verbose_name="Naviera",
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='POR_VACIAR',
        verbose_name="Estado",
    )

    fecha_entrega_cliente = models.DateTimeField(
        verbose_name="Fecha de entrega al cliente",
        help_text="Copiada de la bitácora; arranque del ciclo del vacío.",
    )
    fecha_retorno_patio = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de retorno a Patio Esperanza",
    )

    unidad = models.ForeignKey(
        'unidades.Unidad',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vacios',
        verbose_name="Unidad asignada",
    )
    operador = models.ForeignKey(
        'operadores.Operador',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vacios',
        verbose_name="Operador asignado",
    )
    fecha_asignacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de asignación",
        help_text="Se sella la primera vez que se asigna unidad y operador.",
    )

    fecha_compromiso_naviera = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha compromiso de entrega a naviera",
    )
    fecha_salida_naviera = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de salida rumbo a la naviera",
    )
    fecha_entrega_naviera = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de entrega a la naviera",
    )

    tiene_retraso = models.BooleanField(default=False, verbose_name="Tiene retraso")
    observaciones = models.TextField(blank=True, verbose_name="Observaciones")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vacío"
        verbose_name_plural = "Vacíos"
        ordering = ['-fecha_entrega_cliente']
        constraints = [
            models.UniqueConstraint(
                fields=['bitacora_viaje', 'numero_contenedor'],
                name='uniq_vacio_bitacora_contenedor',
            )
        ]

    def __str__(self):
        return f"{self.folio} - {self.contenedor}"

    def save(self, *args, **kwargs):
        if self.folio:
            super().save(*args, **kwargs)
            return

        # Folio VAC-YYYYMMDD-XXX con reintento anti-colisión (mismo patrón que
        # Modulacion.save()): select_for_update() serializa contra el último
        # folio del día; el reintento cubre el primer folio del día.
        fecha = timezone.localtime(self.fecha_entrega_cliente).strftime('%Y%m%d')
        ultimo_error = None
        for _intento in range(5):
            with transaction.atomic():
                ultimo = (
                    Vacio.objects
                    .select_for_update()
                    .filter(folio__startswith=f'VAC-{fecha}')
                    .order_by('-folio')
                    .first()
                )
                numero = int(ultimo.folio.split('-')[-1]) + 1 if ultimo else 1
                self.folio = f'VAC-{fecha}-{numero:03d}'
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError as exc:
                    ultimo_error = exc
                    self.folio = ''

        raise IntegrityError(
            f'No se pudo generar un folio único para {fecha} después de varios intentos'
        ) from ultimo_error


class RetrasoVacio(models.Model):
    """Evento de retraso en el ciclo de un vacío; dispara aviso a la agencia."""
    TIPO_CHOICES = [
        ('MANIOBRA', 'Cambio por maniobra (retraso en la entrega)'),
        ('RETORNO', 'Retraso de retorno (viaje de regreso)'),
    ]

    vacio = models.ForeignKey(
        Vacio,
        on_delete=models.CASCADE,
        related_name='retrasos',
        verbose_name="Vacío",
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, verbose_name="Tipo de retraso")
    motivo = models.TextField(verbose_name="Motivo")
    fecha_estimada_nueva = models.DateField(verbose_name="Nueva fecha estimada de entrega")
    notificado_agencia = models.BooleanField(default=False, verbose_name="Notificado a la agencia")
    fecha_notificacion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de notificación")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name="Creado por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Retraso de vacío"
        verbose_name_plural = "Retrasos de vacíos"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.vacio.folio}"


class CambioOperadorVacio(models.Model):
    """Historial de reasignación de unidad/operador de un vacío, con la causa."""
    CAUSA_CHOICES = [
        ('NO_CONFIRMA', 'Operador no confirma'),
        ('SE_NIEGA', 'Operador se niega a hacer la entrega'),
        ('ULTIMA_HORA', 'Cambio de última hora'),
    ]

    vacio = models.ForeignKey(
        Vacio,
        on_delete=models.CASCADE,
        related_name='cambios_operador',
        verbose_name="Vacío",
    )
    unidad_saliente = models.ForeignKey(
        'unidades.Unidad', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Unidad saliente",
    )
    unidad_entrante = models.ForeignKey(
        'unidades.Unidad', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Unidad entrante",
    )
    operador_saliente = models.ForeignKey(
        'operadores.Operador', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Operador saliente",
    )
    operador_entrante = models.ForeignKey(
        'operadores.Operador', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Operador entrante",
    )
    causa = models.CharField(max_length=15, choices=CAUSA_CHOICES, verbose_name="Causa")
    motivo = models.TextField(blank=True, verbose_name="Motivo / detalle")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Creado por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cambio de operador de vacío"
        verbose_name_plural = "Cambios de operador de vacíos"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.vacio.folio}: {self.get_causa_display()}"
```

- [ ] **Step 5: Escribir un `admin.py` mínimo**

```python
from django.contrib import admin

from .models import CambioOperadorVacio, Naviera, RetrasoVacio, Vacio


class RetrasoVacioInline(admin.TabularInline):
    model = RetrasoVacio
    extra = 0
    readonly_fields = ('notificado_agencia', 'fecha_notificacion', 'created_at')


class CambioOperadorVacioInline(admin.TabularInline):
    model = CambioOperadorVacio
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Naviera)
class NavieraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'created_at')
    list_filter = ('activo',)
    search_fields = ('nombre',)


@admin.register(Vacio)
class VacioAdmin(admin.ModelAdmin):
    list_display = (
        'folio', 'contenedor', 'cliente', 'estado', 'operador', 'unidad',
        'naviera', 'tiene_retraso', 'fecha_entrega_cliente',
    )
    list_filter = ('estado', 'naviera', 'tiene_retraso', 'tipo_contenedor')
    search_fields = ('folio', 'contenedor')
    readonly_fields = (
        'folio', 'fecha_entrega_cliente', 'fecha_retorno_patio',
        'fecha_asignacion', 'fecha_salida_naviera', 'fecha_entrega_naviera',
        'created_at', 'updated_at',
    )
    autocomplete_fields = ('bitacora_viaje', 'cliente', 'operador', 'unidad', 'naviera', 'agencia')
    inlines = (RetrasoVacioInline, CambioOperadorVacioInline)


@admin.register(RetrasoVacio)
class RetrasoVacioAdmin(admin.ModelAdmin):
    list_display = ('vacio', 'tipo', 'fecha_estimada_nueva', 'notificado_agencia', 'created_at')
    list_filter = ('tipo', 'notificado_agencia')


@admin.register(CambioOperadorVacio)
class CambioOperadorVacioAdmin(admin.ModelAdmin):
    list_display = ('vacio', 'causa', 'operador_saliente', 'operador_entrante', 'created_at')
    list_filter = ('causa',)
```

> Nota: `VacioAdmin.autocomplete_fields` incluye `agencia`; `modulacion.AgenciaAdmin` ya define `search_fields`. Si al correr fallara por falta de `search_fields` en algún admin referenciado, quitar ese campo del `autocomplete_fields`.

- [ ] **Step 6: Escribir los tests de modelo**

Create `modulos/vacios/tests.py`:

```python
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from modulos.bitacoras.models import BitacoraViaje, Cliente
from modulos.modulacion.models import Agencia, Modulacion, TerminalPortuaria
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad
from modulos.vacios.models import CambioOperadorVacio, Naviera, RetrasoVacio, Vacio


def _cliente(nombre='ACME'):
    return Cliente.objects.get_or_create(nombre=nombre)[0]


def _unidad(numero_economico='ECO-001', tipo='LOCAL'):
    return Unidad.objects.create(
        numero_economico=numero_economico,
        placa=f'P-{numero_economico}',
        tipo=tipo,
        año=2020,
        capacidad_combustible=Decimal('200.00'),
        rendimiento_esperado=Decimal('3.00'),
    )


def _operador(nombre='Juan Pérez', tipo='LOCAL', unidad=None):
    return Operador.objects.create(nombre=nombre, tipo=tipo, unidad_asignada=unidad)


def _bitacora(**kwargs):
    """BitacoraViaje mínima y válida. Sin fechas de entrega por defecto."""
    ahora = timezone.now()
    datos = dict(
        cliente=_cliente(),
        operador=kwargs.pop('operador', None) or _operador('Op Bitacora', unidad=_unidad('ECO-BIT')),
        unidad=kwargs.pop('unidad', None) or _unidad('ECO-BIT2'),
        modalidad='SENCILLO',
        contenedor='MSCU1111111',
        fecha_carga=ahora,
        fecha_salida=ahora,
        destino='Bodega 5, Zona Industrial',
    )
    datos.update(kwargs)
    return BitacoraViaje.objects.create(**datos)


class VacioModelTests(TestCase):
    def test_folio_autogenerado(self):
        v = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='MSCU1111111',
            fecha_entrega_cliente=timezone.now(),
        )
        fecha = timezone.localtime(v.fecha_entrega_cliente).strftime('%Y%m%d')
        self.assertEqual(v.folio, f'VAC-{fecha}-001')

    def test_folio_consecutivo_mismo_dia(self):
        ahora = timezone.now()
        v1 = Vacio.objects.create(bitacora_viaje=_bitacora(), contenedor='A', fecha_entrega_cliente=ahora)
        v2 = Vacio.objects.create(bitacora_viaje=_bitacora(), contenedor='B', fecha_entrega_cliente=ahora)
        self.assertTrue(v1.folio.endswith('-001'))
        self.assertTrue(v2.folio.endswith('-002'))

    def test_unique_constraint_bitacora_contenedor(self):
        b = _bitacora()
        Vacio.objects.create(bitacora_viaje=b, numero_contenedor='1', contenedor='A', fecha_entrega_cliente=timezone.now())
        with self.assertRaises(Exception):
            Vacio.objects.create(bitacora_viaje=b, numero_contenedor='1', contenedor='A', fecha_entrega_cliente=timezone.now())

    def test_agencia_email_contacto(self):
        a = Agencia.objects.create(nombre='LOGINCO', email_contacto='avisos@loginco.mx')
        self.assertEqual(Agencia.objects.get(pk=a.pk).email_contacto, 'avisos@loginco.mx')
```

- [ ] **Step 7: Generar migraciones y verificar que los tests fallan por falta de tablas**

Run:
```bash
python manage.py makemigrations vacios modulacion --settings=test_settings
python manage.py test modulos.vacios --settings=test_settings -v 2
```
Expected: las migraciones se crean (`modulos/vacios/migrations/0001_initial.py`, `modulos/modulacion/migrations/000X_agencia_email_contacto.py`); los tests **PASAN** una vez creadas las migraciones (SQLite construye el esquema desde ellas). Si `makemigrations` no se hubiera corrido, fallarían con `no such table`.

- [ ] **Step 8: Commit**

```bash
git add modulos/vacios modulos/modulacion config/settings.py
git commit -m "Vacíos: scaffold de app, modelos base y campo email_contacto en Agencia"
```

---

## Task 2: Creación automática del vacío (signal `post_save`)

**Files:**
- Modify: `modulos/vacios/signals.py`
- Modify: `modulos/vacios/tests.py` (nueva clase `SignalCreacionTests`)

**Interfaces:**
- Consumes: `Vacio`, `BitacoraViaje` (`fecha_hora_entrega`, `fecha_hora_entrega_2`, `contenedor`, `contenedor_2`, `cliente`, `cliente_2`, `tipo_contenedor`), reverse `bitacora.modulacion.agencia`.
- Produces: al guardar una `BitacoraViaje`, `Vacio` con `numero_contenedor='1'` por `fecha_hora_entrega` y `Vacio` con `numero_contenedor='2'` por `fecha_hora_entrega_2`. Idempotente.

- [ ] **Step 1: Escribir los tests del signal**

Add to `modulos/vacios/tests.py`:

```python
class SignalCreacionTests(TestCase):
    def test_crea_un_vacio_al_registrar_entrega(self):
        b = _bitacora()
        self.assertEqual(Vacio.objects.count(), 0)
        b.fecha_hora_entrega = timezone.now()
        b.save()
        self.assertEqual(Vacio.objects.count(), 1)
        v = Vacio.objects.get()
        self.assertEqual(v.numero_contenedor, '1')
        self.assertEqual(v.contenedor, b.contenedor)
        self.assertEqual(v.cliente, b.cliente)
        self.assertEqual(v.estado, 'POR_VACIAR')

    def test_full_con_dos_entregas_crea_dos_vacios(self):
        b = _bitacora(
            modalidad='FULL',
            contenedor='AAAA1111111',
            contenedor_2='BBBB2222222',
            peso_2=Decimal('10.00'),
        )
        b.fecha_hora_entrega = timezone.now()
        b.fecha_hora_entrega_2 = timezone.now()
        b.save()
        self.assertEqual(Vacio.objects.count(), 2)
        self.assertEqual(
            set(Vacio.objects.values_list('numero_contenedor', flat=True)),
            {'1', '2'},
        )
        v2 = Vacio.objects.get(numero_contenedor='2')
        self.assertEqual(v2.contenedor, 'BBBB2222222')

    def test_es_idempotente(self):
        b = _bitacora()
        b.fecha_hora_entrega = timezone.now()
        b.save()
        b.save()
        b.observaciones = 'otra edición'
        b.save()
        self.assertEqual(Vacio.objects.count(), 1)

    def test_sin_fecha_entrega_no_crea_vacio(self):
        _bitacora()
        self.assertEqual(Vacio.objects.count(), 0)

    def test_autollena_agencia_desde_modulacion(self):
        agencia = Agencia.objects.create(nombre='LOGINCO', email_contacto='a@b.mx')
        terminal = TerminalPortuaria.objects.create(nombre='TIMSA')
        b = _bitacora()
        Modulacion.objects.create(
            agencia=agencia,
            terminal_portuaria=terminal,
            tipo_contenedor='40HC',
            peso_toneladas=Decimal('18.00'),
            contenedor='MSCU1111111',
            bitacora_viaje=b,
        )
        b.fecha_hora_entrega = timezone.now()
        b.save()
        self.assertEqual(Vacio.objects.get().agencia, agencia)
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `python manage.py test modulos.vacios.tests.SignalCreacionTests --settings=test_settings -v 2`
Expected: FAIL (`Vacio.objects.count()` == 0, no existe el signal).

- [ ] **Step 3: Implementar el signal**

Replace `modulos/vacios/signals.py`:

```python
"""Creación automática de Vacío al registrarse la entrega de un contenedor."""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from modulos.bitacoras.models import BitacoraViaje

from .models import Vacio

logger = logging.getLogger(__name__)


def _agencia_de(bitacora):
    """Agencia ligada vía Modulación (OneToOne inverso), o None."""
    try:
        return bitacora.modulacion.agencia
    except Exception:
        return None


@receiver(post_save, sender=BitacoraViaje)
def crear_vacios_por_entrega(sender, instance, **kwargs):
    """
    Por cada contenedor del viaje con fecha de entrega registrada y sin Vacío
    aún, crea el Vacío. Solo crea: nunca borra ni revierte.
    """
    agencia = _agencia_de(instance)

    contenedores = [
        ('1', instance.fecha_hora_entrega, instance.contenedor, instance.cliente),
        ('2', instance.fecha_hora_entrega_2, instance.contenedor_2,
         instance.cliente_2 or instance.cliente),
    ]

    for numero, fecha_entrega, contenedor, cliente in contenedores:
        if not fecha_entrega:
            continue
        vacio, creado = Vacio.objects.get_or_create(
            bitacora_viaje=instance,
            numero_contenedor=numero,
            defaults={
                'contenedor': contenedor or '',
                'cliente': cliente,
                'tipo_contenedor': instance.tipo_contenedor or '40',
                'agencia': agencia,
                'fecha_entrega_cliente': fecha_entrega,
                'estado': 'POR_VACIAR',
            },
        )
        if creado:
            logger.info('Vacío %s creado desde bitácora #%s (contenedor %s)',
                        vacio.folio, instance.pk, numero)
```

- [ ] **Step 4: Correr los tests hasta verde**

Run: `python manage.py test modulos.vacios.tests.SignalCreacionTests --settings=test_settings -v 2`
Expected: PASS (5 tests).

- [ ] **Step 5: Correr la suite completa de la app**

Run: `python manage.py test modulos.vacios --settings=test_settings -v 2`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add modulos/vacios/signals.py modulos/vacios/tests.py
git commit -m "Vacíos: creación automática del vacío al registrar la entrega del contenedor"
```

---

## Task 3: Servicio `operadores_libres()`

**Files:**
- Create: `modulos/vacios/services.py`
- Modify: `modulos/vacios/tests.py` (clase `OperadoresLibresTests`)

**Interfaces:**
- Consumes: `Operador`, `Modulacion`, `Vacio`, `BitacoraViaje`.
- Produces: `modulos.vacios.services.operadores_libres() -> QuerySet[Operador]` — operadores `tipo='LOCAL'`, `activo=True`, que no estén ocupados en una Modulación activa (`MODULADO`/`EN_PATIO_ESPERANZA`), ni en un `Vacio` en estado `ASIGNADO`, ni en una `BitacoraViaje` con `completado=False`.

- [ ] **Step 1: Escribir los tests**

Add to `modulos/vacios/tests.py`:

```python
from modulos.vacios.services import operadores_libres


class OperadoresLibresTests(TestCase):
    def test_incluye_local_activo_sin_ocupacion(self):
        op = _operador('Libre')
        self.assertIn(op, list(operadores_libres()))

    def test_excluye_no_local_y_inactivo(self):
        foraneo = _operador('Foráneo', tipo='FORANEO')
        inactivo = _operador('Inactivo')
        inactivo.activo = False
        inactivo.save()
        libres = list(operadores_libres())
        self.assertNotIn(foraneo, libres)
        self.assertNotIn(inactivo, libres)

    def test_excluye_ocupado_en_modulacion_activa(self):
        op = _operador('EnModulacion')
        Modulacion.objects.create(
            agencia=Agencia.objects.create(nombre='LOGINCO'),
            terminal_portuaria=TerminalPortuaria.objects.create(nombre='TIMSA'),
            tipo_contenedor='40HC',
            peso_toneladas=Decimal('18.00'),
            contenedor='X',
            operador=op,
            estado='EN_PATIO_ESPERANZA',
        )
        self.assertNotIn(op, list(operadores_libres()))

    def test_excluye_ocupado_en_vacio_asignado(self):
        op = _operador('EnVacio')
        Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='A',
            fecha_entrega_cliente=timezone.now(),
            estado='ASIGNADO',
            operador=op,
        )
        self.assertNotIn(op, list(operadores_libres()))

    def test_excluye_ocupado_en_bitacora_en_curso(self):
        op = _operador('EnBitacora', unidad=_unidad('ECO-X'))
        _bitacora(operador=op, unidad=op.unidad_asignada)  # completado=False por defecto
        self.assertNotIn(op, list(operadores_libres()))
```

- [ ] **Step 2: Correr para verlos fallar**

Run: `python manage.py test modulos.vacios.tests.OperadoresLibresTests --settings=test_settings -v 2`
Expected: FAIL (`ModuleNotFoundError: modulos.vacios.services`).

- [ ] **Step 3: Implementar el servicio**

Create `modulos/vacios/services.py`:

```python
"""Lógica de negocio reutilizable del módulo Vacíos."""

from modulos.bitacoras.models import BitacoraViaje
from modulos.modulacion.models import Modulacion
from modulos.operadores.models import Operador

from .models import Vacio


def operadores_libres():
    """
    Operadores LOCAL activos que no están ocupados:
    - sin Modulación asignada en estado MODULADO o EN_PATIO_ESPERANZA,
    - sin Vacío en estado ASIGNADO,
    - sin BitacoraViaje en curso (completado=False).
    """
    ocupados_modulacion = (
        Modulacion.objects
        .filter(estado__in=['MODULADO', 'EN_PATIO_ESPERANZA'], operador__isnull=False)
        .values_list('operador_id', flat=True)
    )
    ocupados_vacio = (
        Vacio.objects
        .filter(estado='ASIGNADO', operador__isnull=False)
        .values_list('operador_id', flat=True)
    )
    ocupados_bitacora = (
        BitacoraViaje.objects
        .filter(completado=False, operador__isnull=False)
        .values_list('operador_id', flat=True)
    )
    ocupados = set(ocupados_modulacion) | set(ocupados_vacio) | set(ocupados_bitacora)

    return (
        Operador.objects
        .filter(tipo='LOCAL', activo=True)
        .exclude(id__in=ocupados)
        .order_by('nombre')
    )
```

- [ ] **Step 4: Correr hasta verde**

Run: `python manage.py test modulos.vacios.tests.OperadoresLibresTests --settings=test_settings -v 2`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add modulos/vacios/services.py modulos/vacios/tests.py
git commit -m "Vacíos: servicio operadores_libres()"
```

---

## Task 4: Vistas de lectura (dashboard, lista, detalle) + plantillas + URLs

**Files:**
- Create: `modulos/vacios/views.py`, `modulos/vacios/urls.py`
- Create: `templates/vacios/dashboard.html`, `templates/vacios/vacio_list.html`, `templates/vacios/vacio_detail.html`
- Modify: `config/urls.py`
- Modify: `modulos/vacios/tests.py` (clase `VistasLecturaTests`)

**Interfaces:**
- Consumes: `Vacio`, `Naviera`.
- Produces (nombres de URL bajo `app_name='vacios'`): `vacios:dashboard` (`''`), `vacios:list` (`'lista/'`), `vacios:detail` (`'<int:pk>/'`). Todas requieren login.

- [ ] **Step 1: Escribir los tests**

Add to `modulos/vacios/tests.py`:

```python
class VistasLecturaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('tester', password='x')
        self.client.force_login(self.user)
        self.vacio = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='MSCU1111111',
            fecha_entrega_cliente=timezone.now(),
        )

    def test_dashboard_200(self):
        resp = self.client.get(reverse('vacios:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Vacíos')

    def test_lista_200_y_muestra_folio(self):
        resp = self.client.get(reverse('vacios:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.vacio.folio)

    def test_lista_filtra_por_mes_de_entrega(self):
        viejo = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='OLD',
            fecha_entrega_cliente=timezone.now() - timedelta(days=90),
        )
        resp = self.client.get(reverse('vacios:list'))  # mes/año actual por defecto
        self.assertContains(resp, self.vacio.folio)
        self.assertNotContains(resp, viejo.folio)

    def test_detalle_200(self):
        resp = self.client.get(reverse('vacios:detail', kwargs={'pk': self.vacio.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.vacio.contenedor)

    def test_requiere_login(self):
        self.client.logout()
        resp = self.client.get(reverse('vacios:list'))
        self.assertEqual(resp.status_code, 302)
```

- [ ] **Step 2: Correr para verlos fallar**

Run: `python manage.py test modulos.vacios.tests.VistasLecturaTests --settings=test_settings -v 2`
Expected: FAIL (`NoReverseMatch: 'vacios'`).

- [ ] **Step 3: Implementar `views.py` (parte de lectura)**

Create `modulos/vacios/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import DetailView, ListView

from .models import Naviera, Vacio

_MESES = [
    (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
    (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
    (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre'),
]


@login_required
def vacios_dashboard(request):
    qs = Vacio.objects.all()
    context = {
        'total': qs.count(),
        'por_vaciar': qs.filter(estado='POR_VACIAR').count(),
        'en_patio_esperanza': qs.filter(estado='EN_PATIO_ESPERANZA').count(),
        'asignados': qs.filter(estado='ASIGNADO').count(),
        'entregados_naviera': qs.filter(estado='ENTREGADO_NAVIERA').count(),
        'retrasos_abiertos': qs.filter(tiene_retraso=True).exclude(estado='ENTREGADO_NAVIERA').count(),
        'recientes': qs.select_related('cliente', 'naviera', 'operador')[:10],
    }
    return render(request, 'vacios/dashboard.html', context)


class VacioListView(LoginRequiredMixin, ListView):
    """Lista de vacíos filtrada por mes/año de fecha_entrega_cliente."""
    model = Vacio
    template_name = 'vacios/vacio_list.html'
    context_object_name = 'vacios'
    paginate_by = 25

    def get_queryset(self):
        qs = Vacio.objects.select_related('cliente', 'naviera', 'operador', 'unidad', 'bitacora_viaje')

        hoy = timezone.localdate()
        anio = int(self.request.GET.get('anio') or hoy.year)
        mes = int(self.request.GET.get('mes') or hoy.month)
        qs = qs.filter(fecha_entrega_cliente__year=anio, fecha_entrega_cliente__month=mes)

        estado = self.request.GET.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        naviera_id = self.request.GET.get('naviera')
        if naviera_id:
            qs = qs.filter(naviera_id=naviera_id)

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(folio__icontains=search) |
                Q(contenedor__icontains=search) |
                Q(cliente__nombre__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        context['estado_choices'] = Vacio.ESTADO_CHOICES
        context['navieras_list'] = Naviera.objects.filter(activo=True)
        context['anio_actual'] = int(self.request.GET.get('anio') or hoy.year)
        context['mes_actual'] = int(self.request.GET.get('mes') or hoy.month)
        context['anios_disponibles'] = range(hoy.year - 3, hoy.year + 1)
        context['meses_disponibles'] = _MESES
        return context


class VacioDetailView(LoginRequiredMixin, DetailView):
    model = Vacio
    template_name = 'vacios/vacio_detail.html'
    context_object_name = 'vacio'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['retrasos'] = self.object.retrasos.all()
        context['cambios_operador'] = self.object.cambios_operador.select_related(
            'operador_saliente', 'operador_entrante', 'unidad_saliente', 'unidad_entrante'
        )
        return context
```

- [ ] **Step 4: Implementar `urls.py`**

Create `modulos/vacios/urls.py`:

```python
from django.urls import path

from . import views

app_name = 'vacios'

urlpatterns = [
    path('', views.vacios_dashboard, name='dashboard'),
    path('lista/', views.VacioListView.as_view(), name='list'),
    path('<int:pk>/', views.VacioDetailView.as_view(), name='detail'),
]
```

Modify `config/urls.py` — agregar junto a las demás rutas de módulos:

```python
    path('vacios/', include('modulos.vacios.urls')),
```

- [ ] **Step 5: Crear las plantillas**

Create `templates/vacios/dashboard.html`:

```html
{% extends "base.html" %}
{% block title %}Vacíos{% endblock %}

{% block content %}
<div class="mb-6">
  <h1 class="text-2xl font-bold text-gray-900">Vacíos</h1>
  <p class="text-sm text-gray-500">Retorno de contenedores vacíos a la naviera.</p>
</div>

<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
  <div class="bg-white rounded-xl border border-gray-100 p-4">
    <div class="text-2xl font-bold text-gray-900">{{ por_vaciar }}</div>
    <div class="text-xs text-gray-500 mt-1">Por vaciar</div>
  </div>
  <div class="bg-white rounded-xl border border-gray-100 p-4">
    <div class="text-2xl font-bold text-gray-900">{{ en_patio_esperanza }}</div>
    <div class="text-xs text-gray-500 mt-1">En Patio Esperanza</div>
  </div>
  <div class="bg-white rounded-xl border border-gray-100 p-4">
    <div class="text-2xl font-bold text-gray-900">{{ asignados }}</div>
    <div class="text-xs text-gray-500 mt-1">Asignados</div>
  </div>
  <div class="bg-white rounded-xl border border-gray-100 p-4">
    <div class="text-2xl font-bold text-gray-900">{{ entregados_naviera }}</div>
    <div class="text-xs text-gray-500 mt-1">Entregados a naviera</div>
  </div>
  <div class="bg-white rounded-xl border border-red-100 p-4">
    <div class="text-2xl font-bold text-red-600">{{ retrasos_abiertos }}</div>
    <div class="text-xs text-gray-500 mt-1">Retrasos abiertos</div>
  </div>
</div>

<div class="flex justify-between items-center mb-3">
  <h2 class="text-lg font-semibold text-gray-800">Recientes</h2>
  <a href="{% url 'vacios:list' %}" class="text-sm text-blue-600 hover:underline">Ver lista completa</a>
</div>
<div class="bg-white rounded-xl border border-gray-100 overflow-hidden">
  <table class="w-full text-sm">
    <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
      <tr>
        <th class="text-left px-4 py-2">Folio</th>
        <th class="text-left px-4 py-2">Contenedor</th>
        <th class="text-left px-4 py-2">Cliente</th>
        <th class="text-left px-4 py-2">Estado</th>
        <th class="text-left px-4 py-2">Entrega cliente</th>
      </tr>
    </thead>
    <tbody>
      {% for v in recientes %}
      <tr class="border-t border-gray-100">
        <td class="px-4 py-2"><a href="{% url 'vacios:detail' v.pk %}" class="text-blue-600 hover:underline">{{ v.folio }}</a></td>
        <td class="px-4 py-2">{{ v.contenedor }}</td>
        <td class="px-4 py-2">{{ v.cliente.nombre|default:"—" }}</td>
        <td class="px-4 py-2">{{ v.get_estado_display }}</td>
        <td class="px-4 py-2">{{ v.fecha_entrega_cliente|date:"d/m/Y H:i" }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="5" class="px-4 py-6 text-center text-gray-400">Sin vacíos registrados.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

Create `templates/vacios/vacio_list.html`:

```html
{% extends "base.html" %}
{% block title %}Vacíos — Lista{% endblock %}

{% block content %}
<div class="flex justify-between items-center mb-4">
  <h1 class="text-2xl font-bold text-gray-900">Vacíos</h1>
  <a href="{% url 'vacios:naviera_list' %}" class="text-sm text-blue-600 hover:underline">Catálogo de navieras</a>
</div>

<form method="get" class="bg-white rounded-xl border border-gray-100 p-4 mb-4 flex flex-wrap gap-3 items-end">
  <div>
    <label class="block text-xs text-gray-500 mb-1">Mes</label>
    <select name="mes" class="border border-gray-300 rounded-lg px-2 py-1 text-sm">
      {% for num, nombre in meses_disponibles %}
      <option value="{{ num }}" {% if num == mes_actual %}selected{% endif %}>{{ nombre }}</option>
      {% endfor %}
    </select>
  </div>
  <div>
    <label class="block text-xs text-gray-500 mb-1">Año</label>
    <select name="anio" class="border border-gray-300 rounded-lg px-2 py-1 text-sm">
      {% for a in anios_disponibles %}
      <option value="{{ a }}" {% if a == anio_actual %}selected{% endif %}>{{ a }}</option>
      {% endfor %}
    </select>
  </div>
  <div>
    <label class="block text-xs text-gray-500 mb-1">Estado</label>
    <select name="estado" class="border border-gray-300 rounded-lg px-2 py-1 text-sm">
      <option value="">Todos</option>
      {% for val, label in estado_choices %}
      <option value="{{ val }}" {% if request.GET.estado == val %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
  </div>
  <div>
    <label class="block text-xs text-gray-500 mb-1">Naviera</label>
    <select name="naviera" class="border border-gray-300 rounded-lg px-2 py-1 text-sm">
      <option value="">Todas</option>
      {% for n in navieras_list %}
      <option value="{{ n.id }}" {% if request.GET.naviera == n.id|stringformat:'s' %}selected{% endif %}>{{ n.nombre }}</option>
      {% endfor %}
    </select>
  </div>
  <div>
    <label class="block text-xs text-gray-500 mb-1">Buscar</label>
    <input type="text" name="search" value="{{ request.GET.search }}" placeholder="Folio, contenedor, cliente"
           class="border border-gray-300 rounded-lg px-2 py-1 text-sm">
  </div>
  <button type="submit" class="px-4 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700">Filtrar</button>
</form>

<div class="bg-white rounded-xl border border-gray-100 overflow-x-auto">
  <table class="w-full text-sm">
    <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
      <tr>
        <th class="text-left px-4 py-2">Folio</th>
        <th class="text-left px-4 py-2">Contenedor</th>
        <th class="text-left px-4 py-2">Cliente</th>
        <th class="text-left px-4 py-2">Estado</th>
        <th class="text-left px-4 py-2">Naviera</th>
        <th class="text-left px-4 py-2">Operador</th>
        <th class="text-left px-4 py-2">Entrega cliente</th>
        <th class="px-4 py-2"></th>
      </tr>
    </thead>
    <tbody>
      {% for v in vacios %}
      <tr class="border-t border-gray-100">
        <td class="px-4 py-2">
          <a href="{% url 'vacios:detail' v.pk %}" class="text-blue-600 hover:underline">{{ v.folio }}</a>
          {% if v.tiene_retraso %}<span class="ml-1 text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full">retraso</span>{% endif %}
        </td>
        <td class="px-4 py-2">{{ v.contenedor }}</td>
        <td class="px-4 py-2">{{ v.cliente.nombre|default:"—" }}</td>
        <td class="px-4 py-2">{{ v.get_estado_display }}</td>
        <td class="px-4 py-2">{{ v.naviera.nombre|default:"—" }}</td>
        <td class="px-4 py-2">{{ v.operador.nombre|default:"—" }}</td>
        <td class="px-4 py-2">{{ v.fecha_entrega_cliente|date:"d/m/Y H:i" }}</td>
        <td class="px-4 py-2 text-right"><a href="{% url 'vacios:detail' v.pk %}" class="text-xs text-blue-600 hover:underline">Ver</a></td>
      </tr>
      {% empty %}
      <tr><td colspan="8" class="px-4 py-6 text-center text-gray-400">Sin vacíos en el periodo seleccionado.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% if is_paginated %}
<div class="mt-4 flex gap-2 text-sm">
  {% if page_obj.has_previous %}<a href="?page={{ page_obj.previous_page_number }}" class="px-3 py-1 border rounded-lg">Anterior</a>{% endif %}
  <span class="px-3 py-1">Página {{ page_obj.number }} de {{ page_obj.paginator.num_pages }}</span>
  {% if page_obj.has_next %}<a href="?page={{ page_obj.next_page_number }}" class="px-3 py-1 border rounded-lg">Siguiente</a>{% endif %}
</div>
{% endif %}
{% endblock %}
```

Create `templates/vacios/vacio_detail.html`:

```html
{% extends "base.html" %}
{% block title %}{{ vacio.folio }}{% endblock %}

{% block content %}
<nav class="text-sm text-gray-500 mb-4">
  <a href="{% url 'vacios:dashboard' %}" class="hover:text-blue-600">Vacíos</a>
  <span class="mx-2">/</span>
  <a href="{% url 'vacios:list' %}" class="hover:text-blue-600">Lista</a>
  <span class="mx-2">/</span>
  <span class="text-gray-800 font-medium">{{ vacio.folio }}</span>
</nav>

{% if messages %}
  {% for m in messages %}
  <div class="mb-3 px-4 py-2 rounded-lg text-sm
      {% if m.tags == 'error' %}bg-red-50 text-red-700 border border-red-200
      {% elif m.tags == 'warning' %}bg-yellow-50 text-yellow-800 border border-yellow-200
      {% else %}bg-green-50 text-green-700 border border-green-200{% endif %}">{{ m }}</div>
  {% endfor %}
{% endif %}

<div class="bg-white rounded-xl border border-gray-100 p-6 mb-6">
  <div class="flex justify-between items-start">
    <div>
      <h1 class="text-xl font-bold text-gray-900">{{ vacio.folio }} — {{ vacio.contenedor }}</h1>
      <span class="inline-block mt-2 px-3 py-1 bg-gray-100 text-gray-700 text-xs font-semibold rounded-full">{{ vacio.get_estado_display }}</span>
      {% if vacio.tiene_retraso %}<span class="ml-1 px-2 py-1 text-xs bg-red-100 text-red-700 rounded-full">Con retraso</span>{% endif %}
    </div>
    <div class="flex gap-2">
      <a href="{% url 'vacios:update' vacio.pk %}" class="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Editar datos</a>
      <a href="{% url 'vacios:delete' vacio.pk %}" class="px-3 py-1.5 text-sm text-red-600 border border-red-200 rounded-lg hover:bg-red-50">Eliminar</a>
    </div>
  </div>

  <dl class="grid grid-cols-2 md:grid-cols-3 gap-4 mt-6 text-sm">
    <div><dt class="text-gray-500">Cliente</dt><dd>{{ vacio.cliente.nombre|default:"—" }}</dd></div>
    <div><dt class="text-gray-500">Tipo</dt><dd>{{ vacio.get_tipo_contenedor_display }}</dd></div>
    <div><dt class="text-gray-500">Naviera</dt><dd>{{ vacio.naviera.nombre|default:"—" }}</dd></div>
    <div><dt class="text-gray-500">Agencia</dt><dd>{{ vacio.agencia.nombre|default:"—" }}</dd></div>
    <div><dt class="text-gray-500">Bitácora origen</dt><dd><a href="{% url 'bitacoras:detail' vacio.bitacora_viaje.pk %}" class="text-blue-600 hover:underline">Viaje #{{ vacio.bitacora_viaje.pk }}</a></dd></div>
    <div><dt class="text-gray-500">Entrega al cliente</dt><dd>{{ vacio.fecha_entrega_cliente|date:"d/m/Y H:i" }}</dd></div>
    <div><dt class="text-gray-500">Retorno a patio</dt><dd>{{ vacio.fecha_retorno_patio|date:"d/m/Y H:i"|default:"—" }}</dd></div>
    <div><dt class="text-gray-500">Operador</dt><dd>{{ vacio.operador.nombre|default:"—" }}</dd></div>
    <div><dt class="text-gray-500">Unidad</dt><dd>{{ vacio.unidad.numero_economico|default:"—" }}</dd></div>
    <div><dt class="text-gray-500">Compromiso naviera</dt><dd>{{ vacio.fecha_compromiso_naviera|date:"d/m/Y H:i"|default:"—" }}</dd></div>
    <div><dt class="text-gray-500">Salida a naviera</dt><dd>{{ vacio.fecha_salida_naviera|date:"d/m/Y H:i"|default:"—" }}</dd></div>
    <div><dt class="text-gray-500">Entrega a naviera</dt><dd>{{ vacio.fecha_entrega_naviera|date:"d/m/Y H:i"|default:"—" }}</dd></div>
  </dl>
  {% if vacio.observaciones %}<p class="mt-4 text-sm text-gray-600">{{ vacio.observaciones }}</p>{% endif %}
</div>

<!-- Bloque de acciones: se completa en Task 5 y Task 6 -->
{% block acciones_vacio %}{% endblock %}

<div class="grid md:grid-cols-2 gap-6">
  <div class="bg-white rounded-xl border border-gray-100 p-4">
    <h2 class="text-sm font-semibold text-gray-800 mb-3">Retrasos</h2>
    {% for r in retrasos %}
    <div class="border-t border-gray-100 py-2 text-sm">
      <div class="font-medium">{{ r.get_tipo_display }}</div>
      <div class="text-gray-500">Nueva fecha: {{ r.fecha_estimada_nueva|date:"d/m/Y" }} ·
        {% if r.notificado_agencia %}Agencia notificada {{ r.fecha_notificacion|date:"d/m/Y H:i" }}{% else %}<span class="text-red-600">Agencia sin notificar</span>{% endif %}
      </div>
      <div class="text-gray-600">{{ r.motivo }}</div>
    </div>
    {% empty %}
    <p class="text-sm text-gray-400">Sin retrasos.</p>
    {% endfor %}
  </div>
  <div class="bg-white rounded-xl border border-gray-100 p-4">
    <h2 class="text-sm font-semibold text-gray-800 mb-3">Cambios de operador</h2>
    {% for c in cambios_operador %}
    <div class="border-t border-gray-100 py-2 text-sm">
      <div class="font-medium">{{ c.get_causa_display }}</div>
      <div class="text-gray-500">
        {{ c.operador_saliente.nombre|default:"—" }} → {{ c.operador_entrante.nombre|default:"—" }}
        · {{ c.created_at|date:"d/m/Y H:i" }}
      </div>
      {% if c.motivo %}<div class="text-gray-600">{{ c.motivo }}</div>{% endif %}
    </div>
    {% empty %}
    <p class="text-sm text-gray-400">Sin cambios.</p>
    {% endfor %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Correr los tests hasta verde**

Run: `python manage.py test modulos.vacios.tests.VistasLecturaTests --settings=test_settings -v 2`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add modulos/vacios/views.py modulos/vacios/urls.py config/urls.py templates/vacios/ modulos/vacios/tests.py
git commit -m "Vacíos: dashboard, lista con filtro mes/año y detalle"
```

---

## Task 5: Acciones de transición de estado (retorno a patio, asignar, reasignar, salida y entrega a naviera)

**Files:**
- Create: `modulos/vacios/forms.py`
- Modify: `modulos/vacios/views.py`, `modulos/vacios/urls.py`
- Create: `templates/vacios/asignar_unidad_operador.html`, `templates/vacios/vacio_form.html`, `templates/vacios/vacio_confirm_delete.html`
- Modify: `templates/vacios/vacio_detail.html` (bloque `acciones_vacio`)
- Modify: `modulos/vacios/tests.py` (clase `TransicionesTests`)

**Interfaces:**
- Consumes: `Vacio`, `operadores_libres()`, `CambioOperadorVacio`.
- Produces (URLs): `vacios:update`, `vacios:delete`, `vacios:asignar`, `vacios:registrar_retorno_patio`, `vacios:reasignar_operador`, `vacios:registrar_salida_naviera`, `vacios:registrar_entrega_naviera`.
  - Reglas de estado: `registrar_retorno_patio` exige `estado='POR_VACIAR'` → `EN_PATIO_ESPERANZA` + sella `fecha_retorno_patio`. `asignar` exige `estado='EN_PATIO_ESPERANZA'` → `ASIGNADO` + sella `fecha_asignacion` (solo la 1ª vez). `reasignar_operador` exige `estado='ASIGNADO'`, crea `CambioOperadorVacio`, actualiza `unidad`/`operador`. `registrar_salida_naviera` exige `estado='ASIGNADO'` → sella `fecha_salida_naviera`. `registrar_entrega_naviera` exige `estado='ASIGNADO'` → `ENTREGADO_NAVIERA` + sella `fecha_entrega_naviera`.

- [ ] **Step 1: Escribir los tests**

Add to `modulos/vacios/tests.py`:

```python
class TransicionesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('t', password='x')
        self.client.force_login(self.user)
        self.unidad = _unidad('ECO-100')
        self.operador = _operador('Op Libre', unidad=self.unidad)
        self.vacio = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='C1',
            fecha_entrega_cliente=timezone.now(),
        )

    def _post(self, name, **data):
        return self.client.post(reverse(name, kwargs={'pk': self.vacio.pk}), data)

    def test_retorno_a_patio(self):
        resp = self._post('vacios:registrar_retorno_patio')
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.estado, 'EN_PATIO_ESPERANZA')
        self.assertIsNotNone(self.vacio.fecha_retorno_patio)
        self.assertEqual(resp.status_code, 302)

    def test_retorno_a_patio_rechazado_si_no_por_vaciar(self):
        self.vacio.estado = 'ASIGNADO'
        self.vacio.save()
        self._post('vacios:registrar_retorno_patio')
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.estado, 'ASIGNADO')

    def test_asignar_unidad_operador(self):
        self.vacio.estado = 'EN_PATIO_ESPERANZA'
        self.vacio.save()
        self._post('vacios:asignar', unidad=self.unidad.pk, operador=self.operador.pk)
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.estado, 'ASIGNADO')
        self.assertEqual(self.vacio.operador, self.operador)
        self.assertIsNotNone(self.vacio.fecha_asignacion)

    def test_fecha_asignacion_no_se_resella(self):
        self.vacio.estado = 'EN_PATIO_ESPERANZA'
        self.vacio.save()
        self._post('vacios:asignar', unidad=self.unidad.pk, operador=self.operador.pk)
        self.vacio.refresh_from_db()
        primera = self.vacio.fecha_asignacion
        otra = _operador('Op 2', unidad=_unidad('ECO-200'))
        self.client.post(
            reverse('vacios:reasignar_operador', kwargs={'pk': self.vacio.pk}),
            {'unidad_entrante': otra.unidad_asignada.pk, 'operador_entrante': otra.pk, 'causa': 'NO_CONFIRMA'},
        )
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.fecha_asignacion, primera)

    def test_reasignar_crea_historial(self):
        self.vacio.estado = 'ASIGNADO'
        self.vacio.unidad = self.unidad
        self.vacio.operador = self.operador
        self.vacio.save()
        nueva_unidad = _unidad('ECO-300')
        nuevo_operador = _operador('Op Nuevo', unidad=nueva_unidad)
        self.client.post(
            reverse('vacios:reasignar_operador', kwargs={'pk': self.vacio.pk}),
            {'unidad_entrante': nueva_unidad.pk, 'operador_entrante': nuevo_operador.pk,
             'causa': 'SE_NIEGA', 'motivo': 'no quiso'},
        )
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.operador, nuevo_operador)
        self.assertEqual(self.vacio.unidad, nueva_unidad)
        cambio = CambioOperadorVacio.objects.get()
        self.assertEqual(cambio.operador_saliente, self.operador)
        self.assertEqual(cambio.operador_entrante, nuevo_operador)
        self.assertEqual(cambio.causa, 'SE_NIEGA')

    def test_salida_y_entrega_a_naviera(self):
        self.vacio.estado = 'ASIGNADO'
        self.vacio.save()
        self._post('vacios:registrar_salida_naviera')
        self.vacio.refresh_from_db()
        self.assertIsNotNone(self.vacio.fecha_salida_naviera)
        self.assertEqual(self.vacio.estado, 'ASIGNADO')
        self._post('vacios:registrar_entrega_naviera')
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.estado, 'ENTREGADO_NAVIERA')
        self.assertIsNotNone(self.vacio.fecha_entrega_naviera)

    def test_editar_datos_naviera_y_compromiso(self):
        naviera = Naviera.objects.create(nombre='MSC')
        resp = self.client.post(
            reverse('vacios:update', kwargs={'pk': self.vacio.pk}),
            {'naviera': naviera.pk, 'fecha_compromiso_naviera': '2026-09-15T10:00', 'observaciones': 'ok'},
        )
        self.assertEqual(resp.status_code, 302)
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.naviera, naviera)
```

- [ ] **Step 2: Correr para verlos fallar**

Run: `python manage.py test modulos.vacios.tests.TransicionesTests --settings=test_settings -v 2`
Expected: FAIL (`NoReverseMatch`).

- [ ] **Step 3: Implementar `forms.py`**

Create `modulos/vacios/forms.py`:

```python
from django import forms

from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad

from .models import CambioOperadorVacio, Naviera, RetrasoVacio, Vacio
from .services import operadores_libres

_INPUT = 'form-control border border-gray-300 rounded-lg px-3 py-2 w-full text-sm'


class NavieraForm(forms.ModelForm):
    class Meta:
        model = Naviera
        fields = ['nombre', 'direccion_retorno', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': _INPUT}),
            'direccion_retorno': forms.Textarea(attrs={'class': _INPUT, 'rows': 2}),
            'activo': forms.CheckboxInput(),
        }


class VacioUpdateForm(forms.ModelForm):
    class Meta:
        model = Vacio
        fields = ['naviera', 'agencia', 'fecha_compromiso_naviera', 'observaciones']
        widgets = {
            'naviera': forms.Select(attrs={'class': _INPUT}),
            'agencia': forms.Select(attrs={'class': _INPUT}),
            'fecha_compromiso_naviera': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'class': _INPUT, 'type': 'datetime-local'},
            ),
            'observaciones': forms.Textarea(attrs={'class': _INPUT, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['naviera'].queryset = Naviera.objects.filter(activo=True)
        self.fields['naviera'].required = False
        self.fields['agencia'].required = False
        self.fields['fecha_compromiso_naviera'].required = False


class AsignarUnidadOperadorVacioForm(forms.ModelForm):
    """Asigna unidad + operador libre. El operador se auto-llena en el navegador."""

    class Meta:
        model = Vacio
        fields = ['unidad', 'operador']
        widgets = {
            'unidad': forms.Select(attrs={'class': _INPUT, 'id': 'id_unidad'}),
            'operador': forms.Select(attrs={'class': _INPUT, 'id': 'id_operador'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unidad'].queryset = Unidad.objects.filter(tipo='LOCAL', activa=True)
        self.fields['unidad'].required = True
        self.fields['operador'].queryset = operadores_libres()
        self.fields['operador'].required = True


class ReasignarOperadorVacioForm(forms.Form):
    unidad_entrante = forms.ModelChoiceField(
        queryset=Unidad.objects.filter(tipo='LOCAL', activa=True),
        widget=forms.Select(attrs={'class': _INPUT, 'id': 'id_unidad'}),
    )
    operador_entrante = forms.ModelChoiceField(
        queryset=Operador.objects.none(),
        widget=forms.Select(attrs={'class': _INPUT, 'id': 'id_operador'}),
    )
    causa = forms.ChoiceField(
        choices=CambioOperadorVacio.CAUSA_CHOICES,
        widget=forms.Select(attrs={'class': _INPUT}),
    )
    motivo = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': _INPUT, 'rows': 2}),
    )

    def __init__(self, *args, vacio=None, **kwargs):
        super().__init__(*args, **kwargs)
        # El operador saliente debe seguir siendo seleccionable si aplica; para
        # el entrante ofrecemos los libres + (por si acaso) todos los LOCAL activos.
        libres_ids = list(operadores_libres().values_list('id', flat=True))
        self.fields['operador_entrante'].queryset = Operador.objects.filter(
            tipo='LOCAL', activo=True
        ).filter(id__in=libres_ids) or Operador.objects.filter(tipo='LOCAL', activo=True)


class RetrasoVacioForm(forms.ModelForm):
    class Meta:
        model = RetrasoVacio
        fields = ['tipo', 'motivo', 'fecha_estimada_nueva']
        widgets = {
            'tipo': forms.Select(attrs={'class': _INPUT}),
            'motivo': forms.Textarea(attrs={'class': _INPUT, 'rows': 3}),
            'fecha_estimada_nueva': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'class': _INPUT, 'type': 'date'},
            ),
        }
```

> Nota: el `or` en el queryset de `operador_entrante` aprovecha que un `QuerySet` vacío es falsy; si hay libres usa esos, si no, todos los LOCAL activos. Es intencional y suficiente para este flujo.

- [ ] **Step 4: Implementar las vistas de transición**

Append to `modulos/vacios/views.py`:

```python
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView, UpdateView

from .forms import (
    AsignarUnidadOperadorVacioForm,
    ReasignarOperadorVacioForm,
    VacioUpdateForm,
)
from .models import CambioOperadorVacio
from .services import operadores_libres

import json


def _map_unidad_operador():
    """JSON {unidad_id: operador_id} para auto-llenar el operador en el navegador."""
    from modulos.operadores.models import Operador
    pares = (
        Operador.objects
        .filter(tipo='LOCAL', activo=True, unidad_asignada__isnull=False)
        .values_list('unidad_asignada_id', 'id')
    )
    return json.dumps({str(u): o for u, o in pares})


class VacioUpdateView(LoginRequiredMixin, UpdateView):
    model = Vacio
    form_class = VacioUpdateForm
    template_name = 'vacios/vacio_form.html'

    def get_success_url(self):
        messages.success(self.request, 'Datos del vacío actualizados.')
        return reverse('vacios:detail', kwargs={'pk': self.object.pk})


class VacioDeleteView(LoginRequiredMixin, DeleteView):
    model = Vacio
    template_name = 'vacios/vacio_confirm_delete.html'
    success_url = reverse_lazy('vacios:list')

    def post(self, request, *args, **kwargs):
        messages.success(request, 'Vacío eliminado.')
        return super().post(request, *args, **kwargs)


class AsignarUnidadOperadorVacioView(LoginRequiredMixin, UpdateView):
    model = Vacio
    form_class = AsignarUnidadOperadorVacioForm
    template_name = 'vacios/asignar_unidad_operador.html'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.estado != 'EN_PATIO_ESPERANZA':
            messages.warning(request, 'El vacío debe estar en Patio Esperanza para asignarse.')
            return redirect(reverse('vacios:detail', kwargs={'pk': self.object.pk}))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unidad_operador_map'] = _map_unidad_operador()
        return context

    def form_valid(self, form):
        vacio = form.save(commit=False)
        vacio.estado = 'ASIGNADO'
        if vacio.fecha_asignacion is None:
            vacio.fecha_asignacion = timezone.now()
        vacio.save()
        messages.success(self.request, f'Unidad y operador asignados a {vacio.folio}.')
        return redirect(reverse('vacios:detail', kwargs={'pk': vacio.pk}))


@login_required
@require_POST
def registrar_retorno_patio(request, pk):
    vacio = get_object_or_404(Vacio, pk=pk)
    if vacio.estado != 'POR_VACIAR':
        messages.warning(request, 'Solo un vacío "por vaciar" puede registrar retorno a patio.')
        return redirect(reverse('vacios:detail', kwargs={'pk': pk}))
    vacio.estado = 'EN_PATIO_ESPERANZA'
    if vacio.fecha_retorno_patio is None:
        vacio.fecha_retorno_patio = timezone.now()
    vacio.save()
    messages.success(request, f'{vacio.folio} en Patio Esperanza.')
    return redirect(reverse('vacios:detail', kwargs={'pk': pk}))


@login_required
@require_POST
def reasignar_operador(request, pk):
    vacio = get_object_or_404(Vacio, pk=pk)
    if vacio.estado != 'ASIGNADO':
        messages.warning(request, 'Solo un vacío asignado puede reasignarse.')
        return redirect(reverse('vacios:detail', kwargs={'pk': pk}))

    form = ReasignarOperadorVacioForm(request.POST, vacio=vacio)
    if not form.is_valid():
        messages.error(request, 'Revisa los datos de la reasignación.')
        return redirect(reverse('vacios:detail', kwargs={'pk': pk}))

    CambioOperadorVacio.objects.create(
        vacio=vacio,
        unidad_saliente=vacio.unidad,
        unidad_entrante=form.cleaned_data['unidad_entrante'],
        operador_saliente=vacio.operador,
        operador_entrante=form.cleaned_data['operador_entrante'],
        causa=form.cleaned_data['causa'],
        motivo=form.cleaned_data.get('motivo', ''),
        creado_por=request.user,
    )
    vacio.unidad = form.cleaned_data['unidad_entrante']
    vacio.operador = form.cleaned_data['operador_entrante']
    vacio.save()
    messages.success(request, f'Operador reasignado en {vacio.folio}.')
    return redirect(reverse('vacios:detail', kwargs={'pk': pk}))


@login_required
@require_POST
def registrar_salida_naviera(request, pk):
    vacio = get_object_or_404(Vacio, pk=pk)
    if vacio.estado != 'ASIGNADO':
        messages.warning(request, 'El vacío debe estar asignado para registrar la salida.')
        return redirect(reverse('vacios:detail', kwargs={'pk': pk}))
    if vacio.fecha_salida_naviera is None:
        vacio.fecha_salida_naviera = timezone.now()
        vacio.save()
    messages.success(request, f'Salida a naviera registrada para {vacio.folio}.')
    return redirect(reverse('vacios:detail', kwargs={'pk': pk}))


@login_required
@require_POST
def registrar_entrega_naviera(request, pk):
    vacio = get_object_or_404(Vacio, pk=pk)
    if vacio.estado != 'ASIGNADO':
        messages.warning(request, 'El vacío debe estar asignado para registrar la entrega.')
        return redirect(reverse('vacios:detail', kwargs={'pk': pk}))
    vacio.estado = 'ENTREGADO_NAVIERA'
    vacio.fecha_entrega_naviera = timezone.now()
    vacio.save()
    messages.success(request, f'{vacio.folio} entregado a la naviera.')
    return redirect(reverse('vacios:detail', kwargs={'pk': pk}))
```

- [ ] **Step 5: Añadir las rutas**

Modify `modulos/vacios/urls.py` — agregar dentro de `urlpatterns`, después de `detail`:

```python
    path('<int:pk>/editar/', views.VacioUpdateView.as_view(), name='update'),
    path('<int:pk>/eliminar/', views.VacioDeleteView.as_view(), name='delete'),
    path('<int:pk>/asignar/', views.AsignarUnidadOperadorVacioView.as_view(), name='asignar'),
    path('<int:pk>/retorno-patio/', views.registrar_retorno_patio, name='registrar_retorno_patio'),
    path('<int:pk>/reasignar/', views.reasignar_operador, name='reasignar_operador'),
    path('<int:pk>/salida-naviera/', views.registrar_salida_naviera, name='registrar_salida_naviera'),
    path('<int:pk>/entrega-naviera/', views.registrar_entrega_naviera, name='registrar_entrega_naviera'),
```

- [ ] **Step 6: Crear las plantillas de formulario**

Create `templates/vacios/vacio_form.html`:

```html
{% extends "base.html" %}
{% block title %}Editar {{ vacio.folio }}{% endblock %}
{% block content %}
<div class="max-w-xl mx-auto bg-white rounded-xl border border-gray-100 p-6">
  <h1 class="text-lg font-bold text-gray-900 mb-4">Editar datos — {{ vacio.folio }}</h1>
  <form method="post" class="space-y-4">
    {% csrf_token %}
    {% for field in form %}
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">{{ field.label }}</label>
      {{ field }}
      {% if field.errors %}<p class="text-xs text-red-500 mt-1">{{ field.errors.0 }}</p>{% endif %}
    </div>
    {% endfor %}
    <div class="flex justify-end gap-3 pt-4 border-t border-gray-100">
      <a href="{% url 'vacios:detail' vacio.pk %}" class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancelar</a>
      <button type="submit" class="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700">Guardar</button>
    </div>
  </form>
</div>
{% endblock %}
```

Create `templates/vacios/vacio_confirm_delete.html`:

```html
{% extends "base.html" %}
{% block title %}Eliminar {{ vacio.folio }}{% endblock %}
{% block content %}
<div class="max-w-md mx-auto bg-white rounded-xl border border-gray-100 p-6">
  <h1 class="text-lg font-bold text-gray-900 mb-2">Eliminar {{ vacio.folio }}</h1>
  <p class="text-sm text-gray-600 mb-4">Esta acción no se puede deshacer.</p>
  <form method="post">
    {% csrf_token %}
    <div class="flex justify-end gap-3">
      <a href="{% url 'vacios:detail' vacio.pk %}" class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancelar</a>
      <button type="submit" class="px-4 py-2 text-sm text-white bg-red-600 rounded-lg hover:bg-red-700">Eliminar</button>
    </div>
  </form>
</div>
{% endblock %}
```

Create `templates/vacios/asignar_unidad_operador.html`:

```html
{% extends "base.html" %}
{% block title %}Asignar unidad y operador — {{ vacio.folio }}{% endblock %}
{% block content %}
<div class="max-w-xl mx-auto bg-white rounded-xl border border-gray-100 p-6">
  <h1 class="text-lg font-bold text-gray-900">
    {% if vacio.operador_id %}Reasignar{% else %}Asignar unidad y operador{% endif %}
  </h1>
  <p class="text-sm text-gray-500 mb-4">{{ vacio.folio }} — {{ vacio.contenedor }}. Al elegir una unidad con operador ligado, el operador se llena solo; puedes cambiarlo.</p>
  <form method="post" class="space-y-4">
    {% csrf_token %}
    {% if form.non_field_errors %}<div class="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-3 py-2">{{ form.non_field_errors.0 }}</div>{% endif %}
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">Unidad local <span class="text-red-500">*</span></label>
      {{ form.unidad }}
      {% if form.unidad.errors %}<p class="text-xs text-red-500 mt-1">{{ form.unidad.errors.0 }}</p>{% endif %}
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">Operador local <span class="text-red-500">*</span></label>
      {{ form.operador }}
      {% if form.operador.errors %}<p class="text-xs text-red-500 mt-1">{{ form.operador.errors.0 }}</p>{% endif %}
    </div>
    <div class="flex justify-end gap-3 pt-4 border-t border-gray-100">
      <a href="{% url 'vacios:detail' vacio.pk %}" class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancelar</a>
      <button type="submit" class="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700">Guardar asignación</button>
    </div>
  </form>
</div>
<script>
  (function () {
    var mapa = {{ unidad_operador_map|safe }};
    var unidad = document.getElementById('id_unidad');
    var operador = document.getElementById('id_operador');
    if (!unidad || !operador) return;
    unidad.addEventListener('change', function () {
      var op = mapa[unidad.value];
      if (op) operador.value = op;
    });
  })();
</script>
{% endblock %}
```

- [ ] **Step 7: Añadir el bloque de acciones al detalle**

Modify `templates/vacios/vacio_detail.html` — reemplazar la línea
`{% block acciones_vacio %}{% endblock %}` por:

```html
<div class="bg-white rounded-xl border border-gray-100 p-4 mb-6">
  <h2 class="text-sm font-semibold text-gray-800 mb-3">Acciones</h2>
  <div class="flex flex-wrap gap-3 items-start">
    {% if vacio.estado == 'POR_VACIAR' %}
    <form method="post" action="{% url 'vacios:registrar_retorno_patio' vacio.pk %}">
      {% csrf_token %}
      <button class="px-4 py-2 text-sm text-white bg-purple-600 rounded-lg hover:bg-purple-700">Registrar retorno a Patio Esperanza</button>
    </form>
    {% endif %}

    {% if vacio.estado == 'EN_PATIO_ESPERANZA' %}
    <a href="{% url 'vacios:asignar' vacio.pk %}" class="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700">Asignar unidad y operador</a>
    {% endif %}

    {% if vacio.estado == 'ASIGNADO' %}
    <a href="{% url 'vacios:asignar' vacio.pk %}" class="px-4 py-2 text-sm border border-blue-300 text-blue-700 rounded-lg hover:bg-blue-50">Reasignar (vía asignar)</a>
    <form method="post" action="{% url 'vacios:reasignar_operador' vacio.pk %}" class="flex flex-wrap gap-2 items-end border-l border-gray-100 pl-3">
      {% csrf_token %}
      <div><label class="block text-xs text-gray-500">Unidad entrante</label>{{ reasignar_form.unidad_entrante }}</div>
      <div><label class="block text-xs text-gray-500">Operador entrante</label>{{ reasignar_form.operador_entrante }}</div>
      <div><label class="block text-xs text-gray-500">Causa</label>{{ reasignar_form.causa }}</div>
      <div><label class="block text-xs text-gray-500">Motivo</label>{{ reasignar_form.motivo }}</div>
      <button class="px-4 py-2 text-sm text-white bg-amber-600 rounded-lg hover:bg-amber-700">Reasignar operador</button>
    </form>
    <form method="post" action="{% url 'vacios:registrar_salida_naviera' vacio.pk %}">
      {% csrf_token %}
      <button class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Registrar salida a naviera</button>
    </form>
    <form method="post" action="{% url 'vacios:registrar_entrega_naviera' vacio.pk %}">
      {% csrf_token %}
      <button class="px-4 py-2 text-sm text-white bg-green-600 rounded-lg hover:bg-green-700">Registrar entrega a naviera</button>
    </form>
    {% endif %}

    {% if vacio.estado != 'ENTREGADO_NAVIERA' %}
    <a href="{% url 'vacios:registrar_retraso' vacio.pk %}" class="px-4 py-2 text-sm text-red-700 border border-red-200 rounded-lg hover:bg-red-50">Registrar retraso</a>
    {% endif %}
  </div>
</div>
```

Modify `modulos/vacios/views.py` `VacioDetailView.get_context_data` — añadir el form de reasignación al contexto:

```python
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['retrasos'] = self.object.retrasos.all()
        context['cambios_operador'] = self.object.cambios_operador.select_related(
            'operador_saliente', 'operador_entrante', 'unidad_saliente', 'unidad_entrante'
        )
        from .forms import ReasignarOperadorVacioForm
        context['reasignar_form'] = ReasignarOperadorVacioForm(vacio=self.object)
        return context
```

> El enlace `vacios:registrar_retraso` se crea en Task 6; si ejecutas los tests de esta tarea antes de Task 6, comenta esa línea del template o ejecútalas juntas. Recomendado: implementar Task 5 y Task 6 y luego correr toda la suite.

- [ ] **Step 8: Correr los tests hasta verde**

Run: `python manage.py test modulos.vacios.tests.TransicionesTests --settings=test_settings -v 2`
Expected: PASS (7 tests). Si falla por `NoReverseMatch: 'vacios:registrar_retraso'`, continúa con Task 6 y corre la suite completa al final de esa tarea.

- [ ] **Step 9: Commit**

```bash
git add modulos/vacios/forms.py modulos/vacios/views.py modulos/vacios/urls.py templates/vacios/ modulos/vacios/tests.py
git commit -m "Vacíos: acciones de transición de estado (retorno a patio, asignar, reasignar, salida y entrega a naviera)"
```

---

## Task 6: Retrasos y aviso automático por correo a la agencia

**Files:**
- Create: `modulos/vacios/notificaciones.py`
- Create: `templates/vacios/registrar_retraso.html`, `templates/vacios/email/retraso_agencia.html`, `templates/vacios/email/retraso_agencia.txt`
- Modify: `modulos/vacios/views.py`, `modulos/vacios/urls.py`
- Modify: `modulos/vacios/tests.py` (clase `RetrasoTests`)

**Interfaces:**
- Consumes: `RetrasoVacio`, `RetrasoVacioForm`, `Vacio`.
- Produces:
  - `modulos.vacios.notificaciones.notificar_retraso_agencia(retraso) -> bool` — envía el correo a `retraso.vacio.agencia.email_contacto`; en éxito sella `notificado_agencia=True` y `fecha_notificacion`. Devuelve `False` (sin excepción) si no hay destinatario o si el envío falla.
  - URLs: `vacios:registrar_retraso` (`'<int:pk>/retraso/'`, GET muestra form / POST crea), `vacios:reenviar_aviso_retraso` (`'<int:pk>/retraso/<int:rid>/reenviar/'`, POST).

- [ ] **Step 1: Escribir los tests**

Add to `modulos/vacios/tests.py`:

```python
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RetrasoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('t', password='x')
        self.client.force_login(self.user)
        self.agencia = Agencia.objects.create(nombre='LOGINCO', email_contacto='avisos@loginco.mx')
        self.vacio = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='C1',
            fecha_entrega_cliente=timezone.now(),
            agencia=self.agencia,
        )

    def test_registrar_retraso_crea_evento_y_notifica(self):
        mail.outbox = []
        resp = self.client.post(
            reverse('vacios:registrar_retraso', kwargs={'pk': self.vacio.pk}),
            {'tipo': 'MANIOBRA', 'motivo': 'grúa descompuesta', 'fecha_estimada_nueva': '2026-09-20'},
        )
        self.assertEqual(resp.status_code, 302)
        self.vacio.refresh_from_db()
        self.assertTrue(self.vacio.tiene_retraso)
        retraso = RetrasoVacio.objects.get()
        self.assertEqual(retraso.tipo, 'MANIOBRA')
        self.assertTrue(retraso.notificado_agencia)
        self.assertIsNotNone(retraso.fecha_notificacion)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('avisos@loginco.mx', mail.outbox[0].to)

    def test_sin_email_agencia_guarda_pero_no_notifica(self):
        self.agencia.email_contacto = ''
        self.agencia.save()
        mail.outbox = []
        self.client.post(
            reverse('vacios:registrar_retraso', kwargs={'pk': self.vacio.pk}),
            {'tipo': 'RETORNO', 'motivo': 'tráfico', 'fecha_estimada_nueva': '2026-09-21'},
        )
        retraso = RetrasoVacio.objects.get()
        self.assertFalse(retraso.notificado_agencia)
        self.assertEqual(len(mail.outbox), 0)

    def test_reenviar_aviso(self):
        retraso = RetrasoVacio.objects.create(
            vacio=self.vacio, tipo='MANIOBRA', motivo='x',
            fecha_estimada_nueva=date(2026, 9, 20),
        )
        mail.outbox = []
        resp = self.client.post(reverse('vacios:reenviar_aviso_retraso', kwargs={'pk': self.vacio.pk, 'rid': retraso.pk}))
        self.assertEqual(resp.status_code, 302)
        retraso.refresh_from_db()
        self.assertTrue(retraso.notificado_agencia)
        self.assertEqual(len(mail.outbox), 1)

    def test_notificar_retraso_agencia_devuelve_bool(self):
        from modulos.vacios.notificaciones import notificar_retraso_agencia
        retraso = RetrasoVacio.objects.create(
            vacio=self.vacio, tipo='RETORNO', motivo='x',
            fecha_estimada_nueva=date(2026, 9, 22),
        )
        self.assertIs(notificar_retraso_agencia(retraso), True)
        self.vacio.agencia = None
        self.vacio.save()
        retraso2 = RetrasoVacio.objects.create(
            vacio=self.vacio, tipo='RETORNO', motivo='y',
            fecha_estimada_nueva=date(2026, 9, 23),
        )
        self.assertIs(notificar_retraso_agencia(retraso2), False)
```

- [ ] **Step 2: Correr para verlos fallar**

Run: `python manage.py test modulos.vacios.tests.RetrasoTests --settings=test_settings -v 2`
Expected: FAIL (`NoReverseMatch` / `ModuleNotFoundError`).

- [ ] **Step 3: Implementar `notificaciones.py`**

Create `modulos/vacios/notificaciones.py`:

```python
"""Aviso por correo a la agencia aduanal cuando un vacío sufre un retraso."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def notificar_retraso_agencia(retraso) -> bool:
    """
    Envía el correo del retraso a la agencia del vacío. Sella
    notificado_agencia / fecha_notificacion en éxito. Nunca lanza:
    devuelve False si no hay destinatario o si el envío falla.
    """
    vacio = retraso.vacio
    agencia = vacio.agencia
    destinatario = getattr(agencia, 'email_contacto', '') if agencia else ''
    if not destinatario:
        logger.warning('Retraso %s: sin correo de agencia; no se notifica.', retraso.pk)
        return False

    contexto = {
        'retraso': retraso,
        'vacio': vacio,
        'agencia': agencia,
    }
    asunto = f'[Transportes Kasu] Retraso de vacío {vacio.folio} — {retraso.get_tipo_display()}'
    cuerpo_txt = render_to_string('vacios/email/retraso_agencia.txt', contexto)
    cuerpo_html = render_to_string('vacios/email/retraso_agencia.html', contexto)

    try:
        msg = EmailMultiAlternatives(
            subject=asunto,
            body=cuerpo_txt,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            to=[destinatario],
        )
        msg.attach_alternative(cuerpo_html, 'text/html')
        msg.send()
    except Exception:
        logger.exception('Retraso %s: falló el envío del correo a la agencia.', retraso.pk)
        return False

    retraso.notificado_agencia = True
    retraso.fecha_notificacion = timezone.now()
    retraso.save(update_fields=['notificado_agencia', 'fecha_notificacion'])
    return True
```

- [ ] **Step 4: Crear las plantillas de correo**

Create `templates/vacios/email/retraso_agencia.txt`:

```
Estimados,

El siguiente contenedor vacío presenta un retraso y requiere que se reasigne
su fecha de entrega a la naviera.

Vacío: {{ vacio.folio }}
Contenedor: {{ vacio.contenedor }}
Cliente: {{ vacio.cliente.nombre|default:"-" }}
Naviera: {{ vacio.naviera.nombre|default:"-" }}

Tipo de retraso: {{ retraso.get_tipo_display }}
Motivo: {{ retraso.motivo }}
Fecha comprometida anterior: {{ vacio.fecha_compromiso_naviera|date:"d/m/Y H:i"|default:"-" }}
Nueva fecha estimada: {{ retraso.fecha_estimada_nueva|date:"d/m/Y" }}

Por favor reasignen la fecha de entrega en su sistema.

Transportes Kasu
```

Create `templates/vacios/email/retraso_agencia.html`:

```html
<p>Estimados,</p>
<p>El siguiente contenedor vacío presenta un retraso y requiere que se reasigne su fecha de entrega a la naviera.</p>
<table cellpadding="4" style="border-collapse:collapse">
  <tr><td><strong>Vacío</strong></td><td>{{ vacio.folio }}</td></tr>
  <tr><td><strong>Contenedor</strong></td><td>{{ vacio.contenedor }}</td></tr>
  <tr><td><strong>Cliente</strong></td><td>{{ vacio.cliente.nombre|default:"-" }}</td></tr>
  <tr><td><strong>Naviera</strong></td><td>{{ vacio.naviera.nombre|default:"-" }}</td></tr>
  <tr><td><strong>Tipo de retraso</strong></td><td>{{ retraso.get_tipo_display }}</td></tr>
  <tr><td><strong>Motivo</strong></td><td>{{ retraso.motivo }}</td></tr>
  <tr><td><strong>Fecha comprometida anterior</strong></td><td>{{ vacio.fecha_compromiso_naviera|date:"d/m/Y H:i"|default:"-" }}</td></tr>
  <tr><td><strong>Nueva fecha estimada</strong></td><td>{{ retraso.fecha_estimada_nueva|date:"d/m/Y" }}</td></tr>
</table>
<p>Por favor reasignen la fecha de entrega en su sistema.</p>
<p>Transportes Kasu</p>
```

- [ ] **Step 5: Implementar las vistas de retraso**

Append to `modulos/vacios/views.py`:

```python
from .forms import RetrasoVacioForm
from .models import RetrasoVacio
from .notificaciones import notificar_retraso_agencia


class RegistrarRetrasoView(LoginRequiredMixin, UpdateView):
    model = Vacio
    form_class = RetrasoVacioForm
    template_name = 'vacios/registrar_retraso.html'
    context_object_name = 'vacio'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop('instance', None)  # el form es de RetrasoVacio, no de Vacio
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.estado == 'ENTREGADO_NAVIERA':
            messages.warning(request, 'El vacío ya fue entregado; no se registran retrasos.')
            return redirect(reverse('vacios:detail', kwargs={'pk': self.object.pk}))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        retraso = form.save(commit=False)
        retraso.vacio = self.object
        retraso.creado_por = self.request.user
        retraso.save()

        self.object.tiene_retraso = True
        self.object.save(update_fields=['tiene_retraso'])

        if notificar_retraso_agencia(retraso):
            messages.success(self.request, 'Retraso registrado y agencia notificada por correo.')
        else:
            messages.warning(
                self.request,
                'Retraso registrado, pero no se pudo notificar a la agencia '
                '(sin correo de contacto o falló el envío). Captura el correo en '
                '"Editar datos" y usa "Reenviar aviso".',
            )
        return redirect(reverse('vacios:detail', kwargs={'pk': self.object.pk}))
```

> `RegistrarRetrasoView` hereda de `UpdateView` solo para reutilizar `get_object`; el `ModelForm` es de `RetrasoVacio`, por eso se descarta `instance` en `get_form_kwargs`. En GET, Django llamará `get_context_data` con `form` sin instancia — correcto.

Append the resend FBV:

```python
@login_required
@require_POST
def reenviar_aviso_retraso(request, pk, rid):
    vacio = get_object_or_404(Vacio, pk=pk)
    retraso = get_object_or_404(RetrasoVacio, pk=rid, vacio=vacio)
    if notificar_retraso_agencia(retraso):
        messages.success(request, 'Aviso reenviado a la agencia.')
    else:
        messages.error(request, 'No se pudo enviar el aviso. Revisa el correo de la agencia.')
    return redirect(reverse('vacios:detail', kwargs={'pk': pk}))
```

- [ ] **Step 6: Añadir las rutas**

Modify `modulos/vacios/urls.py` — dentro de `urlpatterns`:

```python
    path('<int:pk>/retraso/', views.RegistrarRetrasoView.as_view(), name='registrar_retraso'),
    path('<int:pk>/retraso/<int:rid>/reenviar/', views.reenviar_aviso_retraso, name='reenviar_aviso_retraso'),
```

- [ ] **Step 7: Crear la plantilla del form de retraso**

Create `templates/vacios/registrar_retraso.html`:

```html
{% extends "base.html" %}
{% block title %}Registrar retraso — {{ vacio.folio }}{% endblock %}
{% block content %}
<div class="max-w-xl mx-auto bg-white rounded-xl border border-gray-100 p-6">
  <h1 class="text-lg font-bold text-gray-900 mb-1">Registrar retraso</h1>
  <p class="text-sm text-gray-500 mb-4">{{ vacio.folio }} — {{ vacio.contenedor }}. Al guardar se notifica a la agencia aduanal ({{ vacio.agencia.email_contacto|default:"sin correo de contacto" }}).</p>
  <form method="post" class="space-y-4">
    {% csrf_token %}
    {% for field in form %}
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">{{ field.label }}</label>
      {{ field }}
      {% if field.errors %}<p class="text-xs text-red-500 mt-1">{{ field.errors.0 }}</p>{% endif %}
    </div>
    {% endfor %}
    <div class="flex justify-end gap-3 pt-4 border-t border-gray-100">
      <a href="{% url 'vacios:detail' vacio.pk %}" class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancelar</a>
      <button type="submit" class="px-4 py-2 text-sm text-white bg-red-600 rounded-lg hover:bg-red-700">Guardar y notificar</button>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 8: Añadir el botón "Reenviar aviso" en el detalle**

Modify `templates/vacios/vacio_detail.html` — dentro del `{% for r in retrasos %}`, después de la línea del `motivo`:

```html
      <div class="text-gray-600">{{ r.motivo }}</div>
      {% if not r.notificado_agencia %}
      <form method="post" action="{% url 'vacios:reenviar_aviso_retraso' vacio.pk r.pk %}" class="mt-1">
        {% csrf_token %}
        <button class="text-xs text-blue-600 hover:underline">Reenviar aviso a la agencia</button>
      </form>
      {% endif %}
```

- [ ] **Step 9: Correr toda la suite de la app**

Run: `python manage.py test modulos.vacios --settings=test_settings -v 2`
Expected: PASS (todas las clases: modelo, signal, servicio, lectura, transiciones, retraso).

- [ ] **Step 10: Commit**

```bash
git add modulos/vacios templates/vacios
git commit -m "Vacíos: retrasos estructurados con aviso automático por correo a la agencia"
```

---

## Task 7: CRUD del catálogo Naviera

**Files:**
- Modify: `modulos/vacios/views.py`, `modulos/vacios/urls.py`
- Create: `templates/vacios/naviera_list.html`, `templates/vacios/naviera_form.html`, `templates/vacios/naviera_confirm_delete.html`
- Modify: `modulos/vacios/tests.py` (clase `NavieraCrudTests`)

**Interfaces:**
- Consumes: `Naviera`, `NavieraForm`.
- Produces (URLs): `vacios:naviera_list`, `vacios:naviera_create`, `vacios:naviera_update`, `vacios:naviera_delete`.

- [ ] **Step 1: Escribir los tests**

Add to `modulos/vacios/tests.py`:

```python
class NavieraCrudTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client.force_login(User.objects.create_user('t', password='x'))

    def test_list_200(self):
        Naviera.objects.create(nombre='MSC')
        resp = self.client.get(reverse('vacios:naviera_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'MSC')

    def test_create(self):
        resp = self.client.post(
            reverse('vacios:naviera_create'),
            {'nombre': 'MAERSK', 'direccion_retorno': 'Patio 3', 'activo': 'on'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Naviera.objects.filter(nombre='MAERSK').exists())

    def test_update(self):
        n = Naviera.objects.create(nombre='CMA')
        self.client.post(
            reverse('vacios:naviera_update', kwargs={'pk': n.pk}),
            {'nombre': 'CMA CGM', 'direccion_retorno': '', 'activo': 'on'},
        )
        n.refresh_from_db()
        self.assertEqual(n.nombre, 'CMA CGM')

    def test_delete(self):
        n = Naviera.objects.create(nombre='ONE')
        self.client.post(reverse('vacios:naviera_delete', kwargs={'pk': n.pk}))
        self.assertFalse(Naviera.objects.filter(pk=n.pk).exists())
```

- [ ] **Step 2: Correr para verlos fallar**

Run: `python manage.py test modulos.vacios.tests.NavieraCrudTests --settings=test_settings -v 2`
Expected: FAIL (`NoReverseMatch`).

- [ ] **Step 3: Implementar las vistas**

Append to `modulos/vacios/views.py`:

```python
from django.views.generic import CreateView
from .forms import NavieraForm
from .models import Naviera


class NavieraListView(LoginRequiredMixin, ListView):
    model = Naviera
    template_name = 'vacios/naviera_list.html'
    context_object_name = 'navieras'


class NavieraCreateView(LoginRequiredMixin, CreateView):
    model = Naviera
    form_class = NavieraForm
    template_name = 'vacios/naviera_form.html'
    success_url = reverse_lazy('vacios:naviera_list')

    def form_valid(self, form):
        messages.success(self.request, 'Naviera creada.')
        return super().form_valid(form)


class NavieraUpdateView(LoginRequiredMixin, UpdateView):
    model = Naviera
    form_class = NavieraForm
    template_name = 'vacios/naviera_form.html'
    success_url = reverse_lazy('vacios:naviera_list')

    def form_valid(self, form):
        messages.success(self.request, 'Naviera actualizada.')
        return super().form_valid(form)


class NavieraDeleteView(LoginRequiredMixin, DeleteView):
    model = Naviera
    template_name = 'vacios/naviera_confirm_delete.html'
    success_url = reverse_lazy('vacios:naviera_list')

    def post(self, request, *args, **kwargs):
        messages.success(request, 'Naviera eliminada.')
        return super().post(request, *args, **kwargs)
```

- [ ] **Step 4: Añadir las rutas**

Modify `modulos/vacios/urls.py` — dentro de `urlpatterns`:

```python
    path('navieras/', views.NavieraListView.as_view(), name='naviera_list'),
    path('navieras/nueva/', views.NavieraCreateView.as_view(), name='naviera_create'),
    path('navieras/<int:pk>/editar/', views.NavieraUpdateView.as_view(), name='naviera_update'),
    path('navieras/<int:pk>/eliminar/', views.NavieraDeleteView.as_view(), name='naviera_delete'),
```

- [ ] **Step 5: Crear las plantillas**

Create `templates/vacios/naviera_list.html`:

```html
{% extends "base.html" %}
{% block title %}Navieras{% endblock %}
{% block content %}
<div class="flex justify-between items-center mb-4">
  <h1 class="text-2xl font-bold text-gray-900">Navieras</h1>
  <a href="{% url 'vacios:naviera_create' %}" class="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700">Nueva naviera</a>
</div>
<div class="bg-white rounded-xl border border-gray-100 overflow-hidden">
  <table class="w-full text-sm">
    <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
      <tr><th class="text-left px-4 py-2">Nombre</th><th class="text-left px-4 py-2">Dirección de retorno</th><th class="text-left px-4 py-2">Activo</th><th class="px-4 py-2"></th></tr>
    </thead>
    <tbody>
      {% for n in navieras %}
      <tr class="border-t border-gray-100">
        <td class="px-4 py-2">{{ n.nombre }}</td>
        <td class="px-4 py-2 text-gray-500">{{ n.direccion_retorno|default:"—"|truncatechars:60 }}</td>
        <td class="px-4 py-2">{{ n.activo|yesno:"Sí,No" }}</td>
        <td class="px-4 py-2 text-right">
          <a href="{% url 'vacios:naviera_update' n.pk %}" class="text-xs text-blue-600 hover:underline">Editar</a>
          <a href="{% url 'vacios:naviera_delete' n.pk %}" class="text-xs text-red-600 hover:underline ml-2">Eliminar</a>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="4" class="px-4 py-6 text-center text-gray-400">Sin navieras.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

Create `templates/vacios/naviera_form.html`:

```html
{% extends "base.html" %}
{% block title %}Naviera{% endblock %}
{% block content %}
<div class="max-w-xl mx-auto bg-white rounded-xl border border-gray-100 p-6">
  <h1 class="text-lg font-bold text-gray-900 mb-4">{% if object %}Editar naviera{% else %}Nueva naviera{% endif %}</h1>
  <form method="post" class="space-y-4">
    {% csrf_token %}
    {% for field in form %}
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">{{ field.label }}</label>
      {{ field }}
      {% if field.errors %}<p class="text-xs text-red-500 mt-1">{{ field.errors.0 }}</p>{% endif %}
    </div>
    {% endfor %}
    <div class="flex justify-end gap-3 pt-4 border-t border-gray-100">
      <a href="{% url 'vacios:naviera_list' %}" class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancelar</a>
      <button type="submit" class="px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-700">Guardar</button>
    </div>
  </form>
</div>
{% endblock %}
```

Create `templates/vacios/naviera_confirm_delete.html`:

```html
{% extends "base.html" %}
{% block title %}Eliminar naviera{% endblock %}
{% block content %}
<div class="max-w-md mx-auto bg-white rounded-xl border border-gray-100 p-6">
  <h1 class="text-lg font-bold text-gray-900 mb-2">Eliminar {{ object.nombre }}</h1>
  <form method="post">
    {% csrf_token %}
    <div class="flex justify-end gap-3">
      <a href="{% url 'vacios:naviera_list' %}" class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancelar</a>
      <button type="submit" class="px-4 py-2 text-sm text-white bg-red-600 rounded-lg hover:bg-red-700">Eliminar</button>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 6: Correr hasta verde**

Run: `python manage.py test modulos.vacios.tests.NavieraCrudTests --settings=test_settings -v 2`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add modulos/vacios templates/vacios
git commit -m "Vacíos: CRUD del catálogo de navieras"
```

---

## Task 8: Generadores de reporte

**Files:**
- Create: `modulos/reportes/generadores/vacios.py`
- Create: `modulos/reportes/tests_vacios.py` (o clase nueva en `modulos/reportes/tests.py`)

**Interfaces:**
- Consumes: `modulos.vacios.models.Vacio`, `CambioOperadorVacio`, `RetrasoVacio`.
- Produces:
  - `generar_entregas_por_operador(periodo_inicio: date, periodo_fin: date) -> dict` con claves `tipo='VACIOS_ENTREGAS_SEMANAL'`, `titulo`, `periodo_inicio`, `periodo_fin`, `generado_en`, `resumen` (`total_entregados`, `operadores_activos`, `operador_top`, `entregas_operador_top`, `promedio_por_operador`, `cambios_operador_total`, `vacios_pendientes`), `filas`, `tablas` (`'Entregas por operador y semana'`, `'Totales por operador'`, `'Cambios de operador por causa'`, `'Aún sin entregar'`).
  - `generar_retrasos(periodo_inicio, periodo_fin) -> dict` con `tipo='VACIOS_RETRASOS'`, `resumen` (`total_retrasos`, `retrasos_maniobra`, `retrasos_retorno`, `pct_notificados`), `filas`, `tablas` (`'Retrasos del periodo'`).
  - `GENERADORES = {'VACIOS_ENTREGAS_SEMANAL': generar_entregas_por_operador, 'VACIOS_RETRASOS': generar_retrasos}`

- [ ] **Step 1: Escribir los tests**

Create `modulos/reportes/tests_vacios.py`:

```python
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from modulos.bitacoras.models import BitacoraViaje, Cliente
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad
from modulos.vacios.models import CambioOperadorVacio, RetrasoVacio, Vacio
from modulos.reportes.generadores.vacios import (
    generar_entregas_por_operador,
    generar_retrasos,
)


def _bitacora():
    ahora = timezone.now()
    return BitacoraViaje.objects.create(
        cliente=Cliente.objects.create(nombre='ACME'),
        operador=Operador.objects.create(nombre='Base', tipo='LOCAL'),
        unidad=Unidad.objects.create(
            numero_economico='ECO-B', placa='P-B', tipo='LOCAL', año=2020,
            capacidad_combustible=Decimal('200'), rendimiento_esperado=Decimal('3'),
        ),
        modalidad='SENCILLO', contenedor='C', fecha_carga=ahora, fecha_salida=ahora,
        destino='x',
    )


class EntregasPorOperadorTests(TestCase):
    def test_cuenta_entregas_por_operador_y_semana(self):
        op = Operador.objects.create(nombre='Pedro', tipo='LOCAL')
        entrega = timezone.now() - timedelta(days=2)
        for i in range(3):
            Vacio.objects.create(
                bitacora_viaje=_bitacora(), contenedor=f'C{i}',
                fecha_entrega_cliente=entrega - timedelta(days=10),
                estado='ENTREGADO_NAVIERA', operador=op,
                fecha_entrega_naviera=entrega,
            )
        desde = (timezone.now() - timedelta(days=7)).date()
        hasta = timezone.now().date()
        datos = generar_entregas_por_operador(desde, hasta)
        self.assertEqual(datos['tipo'], 'VACIOS_ENTREGAS_SEMANAL')
        self.assertEqual(datos['resumen']['total_entregados'], 3)
        self.assertEqual(datos['resumen']['operador_top'], 'Pedro')

    def test_incluye_cambios_de_operador_por_causa(self):
        v = Vacio.objects.create(
            bitacora_viaje=_bitacora(), contenedor='C',
            fecha_entrega_cliente=timezone.now(), estado='ASIGNADO',
        )
        CambioOperadorVacio.objects.create(vacio=v, causa='NO_CONFIRMA')
        CambioOperadorVacio.objects.create(vacio=v, causa='NO_CONFIRMA')
        CambioOperadorVacio.objects.create(vacio=v, causa='SE_NIEGA')
        desde = (timezone.now() - timedelta(days=7)).date()
        hasta = timezone.now().date()
        datos = generar_entregas_por_operador(desde, hasta)
        self.assertEqual(datos['resumen']['cambios_operador_total'], 3)
        tabla = datos['tablas']['Cambios de operador por causa']
        por_causa = {f['causa']: f['cantidad'] for f in tabla}
        self.assertEqual(por_causa['Operador no confirma'], 2)

    def test_snapshot_pendientes(self):
        Vacio.objects.create(
            bitacora_viaje=_bitacora(), contenedor='P',
            fecha_entrega_cliente=timezone.now() - timedelta(days=5),
            estado='POR_VACIAR',
        )
        desde = (timezone.now() - timedelta(days=7)).date()
        hasta = timezone.now().date()
        datos = generar_entregas_por_operador(desde, hasta)
        self.assertEqual(datos['resumen']['vacios_pendientes'], 1)
        self.assertEqual(len(datos['tablas']['Aún sin entregar']), 1)


class RetrasosReporteTests(TestCase):
    def test_cuenta_retrasos_por_tipo(self):
        v = Vacio.objects.create(
            bitacora_viaje=_bitacora(), contenedor='C',
            fecha_entrega_cliente=timezone.now(),
        )
        RetrasoVacio.objects.create(vacio=v, tipo='MANIOBRA', motivo='x', fecha_estimada_nueva=date(2026, 9, 1), notificado_agencia=True)
        RetrasoVacio.objects.create(vacio=v, tipo='RETORNO', motivo='y', fecha_estimada_nueva=date(2026, 9, 2))
        desde = (timezone.now() - timedelta(days=7)).date()
        hasta = timezone.now().date()
        datos = generar_retrasos(desde, hasta)
        self.assertEqual(datos['tipo'], 'VACIOS_RETRASOS')
        self.assertEqual(datos['resumen']['total_retrasos'], 2)
        self.assertEqual(datos['resumen']['retrasos_maniobra'], 1)
        self.assertEqual(datos['resumen']['pct_notificados'], 50.0)
```

- [ ] **Step 2: Correr para verlos fallar**

Run: `python manage.py test modulos.reportes.tests_vacios --settings=test_settings -v 2`
Expected: FAIL (`ModuleNotFoundError: modulos.reportes.generadores.vacios`).

- [ ] **Step 3: Implementar el generador**

Create `modulos/reportes/generadores/vacios.py`:

```python
"""Generadores de datos para reportes del módulo Vacíos."""

from collections import defaultdict
from datetime import date, timedelta

from django.utils import timezone

_MESES_ABREV = [
    '', 'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
]


def _rango_semana_iso(anio_iso: int, semana_iso: int) -> tuple:
    lunes = date.fromisocalendar(anio_iso, semana_iso, 1)
    return lunes, lunes + timedelta(days=6)


def _etiqueta_semana(anio_iso: int, semana_iso: int) -> str:
    lunes, domingo = _rango_semana_iso(anio_iso, semana_iso)
    return (
        f"{anio_iso}-W{semana_iso:02d} "
        f"({lunes.day} {_MESES_ABREV[lunes.month]} – {domingo.day} {_MESES_ABREV[domingo.month]})"
    )


def generar_entregas_por_operador(periodo_inicio: date, periodo_fin: date) -> dict:
    """Entregas de vacíos a la naviera por operador y semana ISO en el período.

    "Entregado" = Vacio con `fecha_entrega_naviera` dentro del rango y con
    `operador` asignado. Incluye también el conteo de cambios de operador por
    causa (por `CambioOperadorVacio.created_at` en el rango) y un snapshot de
    los vacíos que siguen sin entregar.
    """
    from modulos.vacios.models import CambioOperadorVacio, Vacio

    entregados = (
        Vacio.objects
        .filter(
            fecha_entrega_naviera__date__gte=periodo_inicio,
            fecha_entrega_naviera__date__lte=periodo_fin,
            operador__isnull=False,
        )
        .select_related('operador')
    )

    por_operador_semana = defaultdict(int)
    por_operador_total = defaultdict(int)
    semanas_vistas = {}

    for v in entregados:
        local = timezone.localtime(v.fecha_entrega_naviera)
        anio_iso, semana_iso, _ = local.isocalendar()
        nombre = v.operador.nombre
        por_operador_semana[(nombre, anio_iso, semana_iso)] += 1
        por_operador_total[nombre] += 1
        semanas_vistas[(anio_iso, semana_iso)] = _etiqueta_semana(anio_iso, semana_iso)

    filas = [
        {
            'operador': nombre,
            'semana': semanas_vistas[(anio_iso, semana_iso)],
            'entregas': conteo,
        }
        for (nombre, anio_iso, semana_iso), conteo in sorted(
            por_operador_semana.items(),
            key=lambda kv: (kv[0][1], kv[0][2], -kv[1], kv[0][0]),
        )
    ]

    totales_operador = [
        {'operador': nombre, 'entregas': conteo}
        for nombre, conteo in sorted(
            por_operador_total.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]

    # Cambios de operador por causa en el período
    cambios = (
        CambioOperadorVacio.objects
        .filter(created_at__date__gte=periodo_inicio, created_at__date__lte=periodo_fin)
    )
    causa_labels = dict(CambioOperadorVacio.CAUSA_CHOICES)
    por_causa = defaultdict(int)
    for c in cambios:
        por_causa[c.causa] += 1
    tabla_cambios = [
        {'causa': causa_labels.get(k, k), 'cantidad': v}
        for k, v in sorted(por_causa.items(), key=lambda kv: -kv[1])
    ]
    cambios_operador_total = sum(por_causa.values())

    # Snapshot de pendientes (no depende del rango)
    ahora = timezone.now()
    pendientes = (
        Vacio.objects
        .exclude(estado='ENTREGADO_NAVIERA')
        .select_related('cliente', 'operador')
        .order_by('fecha_entrega_cliente')
    )
    filas_pendientes = []
    for v in pendientes:
        dias = (ahora - v.fecha_entrega_cliente).days
        filas_pendientes.append({
            'folio': v.folio,
            'contenedor': v.contenedor,
            'cliente': v.cliente.nombre if v.cliente else '—',
            'estado': v.get_estado_display(),
            'dias_en_proceso': dias,
        })

    total_entregados = sum(por_operador_total.values())
    operadores_activos = len(por_operador_total)
    promedio_por_operador = (
        round(total_entregados / operadores_activos, 2) if operadores_activos else 0
    )
    operador_top = totales_operador[0]['operador'] if totales_operador else '—'
    entregas_operador_top = totales_operador[0]['entregas'] if totales_operador else 0

    return {
        'tipo': 'VACIOS_ENTREGAS_SEMANAL',
        'titulo': (
            f'Entregas de vacíos por operador — '
            f'{periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}'
        ),
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_entregados': total_entregados,
            'operadores_activos': operadores_activos,
            'operador_top': operador_top,
            'entregas_operador_top': entregas_operador_top,
            'promedio_por_operador': promedio_por_operador,
            'cambios_operador_total': cambios_operador_total,
            'vacios_pendientes': len(filas_pendientes),
        },
        'filas': filas,
        'tablas': {
            'Entregas por operador y semana': filas,
            'Totales por operador': totales_operador,
            'Cambios de operador por causa': tabla_cambios,
            'Aún sin entregar': filas_pendientes,
        },
    }


def generar_retrasos(periodo_inicio: date, periodo_fin: date) -> dict:
    """Retrasos de vacíos registrados en el período, por tipo."""
    from modulos.vacios.models import RetrasoVacio

    retrasos = (
        RetrasoVacio.objects
        .filter(created_at__date__gte=periodo_inicio, created_at__date__lte=periodo_fin)
        .select_related('vacio', 'vacio__cliente')
        .order_by('created_at')
    )

    filas = []
    maniobra = 0
    retorno = 0
    notificados = 0
    for r in retrasos:
        if r.tipo == 'MANIOBRA':
            maniobra += 1
        else:
            retorno += 1
        if r.notificado_agencia:
            notificados += 1
        filas.append({
            'folio': r.vacio.folio,
            'contenedor': r.vacio.contenedor,
            'cliente': r.vacio.cliente.nombre if r.vacio.cliente else '—',
            'tipo': r.get_tipo_display(),
            'motivo': r.motivo,
            'fecha_estimada_nueva': r.fecha_estimada_nueva.strftime('%d/%m/%Y'),
            'notificado_agencia': 'Sí' if r.notificado_agencia else 'No',
        })

    total = maniobra + retorno
    pct_notificados = round(notificados / total * 100, 1) if total else 0

    return {
        'tipo': 'VACIOS_RETRASOS',
        'titulo': (
            f'Retrasos de vacíos — '
            f'{periodo_inicio.strftime("%d/%m/%Y")} al {periodo_fin.strftime("%d/%m/%Y")}'
        ),
        'periodo_inicio': str(periodo_inicio),
        'periodo_fin': str(periodo_fin),
        'generado_en': timezone.now().isoformat(),
        'resumen': {
            'total_retrasos': total,
            'retrasos_maniobra': maniobra,
            'retrasos_retorno': retorno,
            'pct_notificados': pct_notificados,
        },
        'filas': filas,
        'tablas': {
            'Retrasos del periodo': filas,
        },
    }


GENERADORES = {
    'VACIOS_ENTREGAS_SEMANAL': generar_entregas_por_operador,
    'VACIOS_RETRASOS': generar_retrasos,
}
```

- [ ] **Step 4: Correr hasta verde**

Run: `python manage.py test modulos.reportes.tests_vacios --settings=test_settings -v 2`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add modulos/reportes/generadores/vacios.py modulos/reportes/tests_vacios.py
git commit -m "Vacíos: generadores de reporte (entregas semanales por operador, retrasos)"
```

---

## Task 9: Registrar los reportes en el comando programado, choices y narrativa

**Files:**
- Modify: `modulos/reportes/models.py` (`MODULO_CHOICES`, `TIPO_CHOICES`)
- Modify: `modulos/reportes/management/commands/generar_reportes.py` (import + `GENERADORES`)
- Modify: `modulos/reportes/generadores/narrativa.py` (`_NOMBRES_REPORTE`)
- Modify: `modulos/reportes/tests_vacios.py` (clase `RegistroReportesTests`)

**Interfaces:**
- Consumes: `modulos.reportes.generadores.vacios.GENERADORES`.
- Produces: `ConfiguracionReporte` acepta `modulo='VACIOS'` y `tipo_reporte in {'VACIOS_ENTREGAS_SEMANAL', 'VACIOS_RETRASOS'}`; el comando `generar_reportes` resuelve esos tipos a sus generadores.

- [ ] **Step 1: Escribir el test**

Add to `modulos/reportes/tests_vacios.py`:

```python
from modulos.reportes.models import ConfiguracionReporte


class RegistroReportesTests(TestCase):
    def test_choices_incluyen_vacios(self):
        modulos = dict(ConfiguracionReporte.MODULO_CHOICES)
        tipos = dict(ConfiguracionReporte.TIPO_CHOICES)
        self.assertIn('VACIOS', modulos)
        self.assertIn('VACIOS_ENTREGAS_SEMANAL', tipos)
        self.assertIn('VACIOS_RETRASOS', tipos)

    def test_comando_conoce_los_generadores(self):
        from modulos.reportes.management.commands.generar_reportes import GENERADORES
        self.assertIn('VACIOS_ENTREGAS_SEMANAL', GENERADORES)
        self.assertIn('VACIOS_RETRASOS', GENERADORES)
```

- [ ] **Step 2: Correr para verlo fallar**

Run: `python manage.py test modulos.reportes.tests_vacios.RegistroReportesTests --settings=test_settings -v 2`
Expected: FAIL (`AssertionError: 'VACIOS' not found`).

- [ ] **Step 3: Ampliar los choices**

Modify `modulos/reportes/models.py` — en `MODULO_CHOICES`, después de `('MODULACION', 'Modulación'),`:

```python
        ('MODULACION', 'Modulación'),
        ('VACIOS', 'Vacíos'),
```

En `TIPO_CHOICES`, después de la línea `('MODULACION_RETIROS_PATIO', 'Modulación — Retiros de Patio Esperanza'),`:

```python
        ('MODULACION_RETIROS_PATIO', 'Modulación — Retiros de Patio Esperanza'),
        # Vacíos
        ('VACIOS_ENTREGAS_SEMANAL', 'Vacíos — Entregas por operador (semanal)'),
        ('VACIOS_RETRASOS', 'Vacíos — Retrasos del período'),
```

- [ ] **Step 4: Generar la migración de choices**

Run:
```bash
python manage.py makemigrations reportes --settings=test_settings
```
Expected: crea `modulos/reportes/migrations/00XX_alter_configuracionreporte_modulo_and_more.py` (cambio de `choices`, sin cambio de datos).

- [ ] **Step 5: Registrar el generador en el comando**

Modify `modulos/reportes/management/commands/generar_reportes.py`:

Añadir el import junto a los otros generadores (después de `from modulos.reportes.generadores import modulacion as gen_modulacion`):

```python
from modulos.reportes.generadores import vacios as gen_vacios
```

En el dict `GENERADORES`, añadir la última línea:

```python
GENERADORES = {
    **gen_almacen.GENERADORES,
    **gen_combustible.GENERADORES,
    **gen_unidades.GENERADORES,
    **gen_flota.GENERADORES,
    **gen_modulacion.GENERADORES,
    **gen_vacios.GENERADORES,
}
```

- [ ] **Step 6: Añadir nombres legibles a la narrativa**

Modify `modulos/reportes/generadores/narrativa.py` — en el dict `_NOMBRES_REPORTE`, después de la entrada `'MODULACION_RETIROS_PATIO': ...`:

```python
    'MODULACION_RETIROS_PATIO': 'Retiros de Patio Esperanza (Transportes Kasu, externos y en espera)',
    'VACIOS_ENTREGAS_SEMANAL': 'Entregas de vacíos por operador (semanal)',
    'VACIOS_RETRASOS': 'Retrasos de vacíos (maniobra y retorno)',
```

- [ ] **Step 7: Correr los tests + suite de reportes**

Run:
```bash
python manage.py test modulos.reportes --settings=test_settings -v 2
```
Expected: PASS (suite de reportes existente + `tests_vacios`).

- [ ] **Step 8: Commit**

```bash
git add modulos/reportes
git commit -m "Vacíos: registrar reportes en generar_reportes, choices de ConfiguracionReporte y narrativa"
```

---

## Task 10: Vista en pantalla del reporte de entregas

**Files:**
- Modify: `modulos/reportes/views.py`, `modulos/reportes/urls.py`
- Create: `templates/reportes/entregas_vacios_por_operador.html`
- Modify: `templates/reportes/historial.html` (enlace)
- Modify: `modulos/reportes/tests_vacios.py` (clase `VistaEntregasVaciosTests`)

**Interfaces:**
- Consumes: `generar_entregas_por_operador`.
- Produces: URL `reportes:entregas_vacios_por_operador` (`'vacios/entregas-por-operador/'`), template con selector de rango `desde`/`hasta` (default: última semana).

- [ ] **Step 1: Escribir el test**

Add to `modulos/reportes/tests_vacios.py`:

```python
from django.contrib.auth import get_user_model
from django.urls import reverse


class VistaEntregasVaciosTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client.force_login(User.objects.create_user('t', password='x'))

    def test_vista_200_default(self):
        resp = self.client.get(reverse('reportes:entregas_vacios_por_operador'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Entregas de vacíos')

    def test_vista_200_con_rango(self):
        resp = self.client.get(
            reverse('reportes:entregas_vacios_por_operador'),
            {'desde': '2026-08-01', 'hasta': '2026-08-28'},
        )
        self.assertEqual(resp.status_code, 200)
```

- [ ] **Step 2: Correr para verlo fallar**

Run: `python manage.py test modulos.reportes.tests_vacios.VistaEntregasVaciosTests --settings=test_settings -v 2`
Expected: FAIL (`NoReverseMatch`).

- [ ] **Step 3: Implementar la vista**

Modify `modulos/reportes/views.py`:

Añadir al import de generadores (arriba, junto a `from .generadores.modulacion import generar_contenedores_por_operador`):

```python
from .generadores.vacios import generar_entregas_por_operador
```

Añadir la clase (después de `ContenedoresPorOperadorView`):

```python
class EntregasVaciosPorOperadorView(LoginRequiredMixin, TemplateView):
    """Vista bajo demanda del reporte de entregas de vacíos por operador."""
    template_name = 'reportes/entregas_vacios_por_operador.html'

    def _parse_fecha(self, valor):
        try:
            return datetime.strptime(valor, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        default_hasta = hoy - timedelta(days=1)
        default_desde = default_hasta - timedelta(days=6)

        desde = self._parse_fecha(self.request.GET.get('desde'))
        hasta = self._parse_fecha(self.request.GET.get('hasta'))

        if self.request.GET and (desde is None or hasta is None):
            messages.warning(self.request, 'Rango de fechas inválido; se muestra la última semana.')

        if desde is None:
            desde = default_desde
        if hasta is None:
            hasta = default_hasta
        if desde > hasta:
            desde, hasta = hasta, desde

        ctx['datos'] = generar_entregas_por_operador(desde, hasta)
        ctx['desde'] = desde
        ctx['hasta'] = hasta
        return ctx
```

- [ ] **Step 4: Añadir la ruta**

Modify `modulos/reportes/urls.py` — dentro de `urlpatterns`, junto a la ruta de `contenedores_por_operador`:

```python
    path(
        'vacios/entregas-por-operador/',
        views.EntregasVaciosPorOperadorView.as_view(),
        name='entregas_vacios_por_operador',
    ),
```

- [ ] **Step 5: Crear la plantilla**

Create `templates/reportes/entregas_vacios_por_operador.html`:

```html
{% extends "base.html" %}
{% block title %}Entregas de vacíos por operador{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold text-gray-900 mb-1">Entregas de vacíos por operador</h1>
<p class="text-sm text-gray-500 mb-4">{{ datos.titulo }}</p>

<form method="get" class="bg-white rounded-xl border border-gray-100 p-4 mb-4 flex gap-3 items-end">
  <div>
    <label class="block text-xs text-gray-500 mb-1">Desde</label>
    <input type="date" name="desde" value="{{ desde|date:'Y-m-d' }}" class="border border-gray-300 rounded-lg px-2 py-1 text-sm">
  </div>
  <div>
    <label class="block text-xs text-gray-500 mb-1">Hasta</label>
    <input type="date" name="hasta" value="{{ hasta|date:'Y-m-d' }}" class="border border-gray-300 rounded-lg px-2 py-1 text-sm">
  </div>
  <button type="submit" class="px-4 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700">Actualizar</button>
</form>

<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
  <div class="bg-white rounded-xl border border-gray-100 p-4"><div class="text-2xl font-bold">{{ datos.resumen.total_entregados }}</div><div class="text-xs text-gray-500">Entregados</div></div>
  <div class="bg-white rounded-xl border border-gray-100 p-4"><div class="text-2xl font-bold">{{ datos.resumen.operadores_activos }}</div><div class="text-xs text-gray-500">Operadores activos</div></div>
  <div class="bg-white rounded-xl border border-gray-100 p-4"><div class="text-2xl font-bold">{{ datos.resumen.cambios_operador_total }}</div><div class="text-xs text-gray-500">Cambios de operador</div></div>
  <div class="bg-white rounded-xl border border-gray-100 p-4"><div class="text-2xl font-bold">{{ datos.resumen.vacios_pendientes }}</div><div class="text-xs text-gray-500">Aún sin entregar</div></div>
</div>

{% for nombre_tabla, filas in datos.tablas.items %}
<h2 class="text-sm font-semibold text-gray-800 mt-6 mb-2">{{ nombre_tabla }}</h2>
<div class="bg-white rounded-xl border border-gray-100 overflow-x-auto">
  <table class="w-full text-sm">
    {% if filas %}
    <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
      <tr>{% for k in filas.0.keys %}<th class="text-left px-4 py-2">{{ k }}</th>{% endfor %}</tr>
    </thead>
    <tbody>
      {% for fila in filas %}
      <tr class="border-t border-gray-100">{% for v in fila.values %}<td class="px-4 py-2">{{ v }}</td>{% endfor %}</tr>
      {% endfor %}
    </tbody>
    {% else %}
    <tbody><tr><td class="px-4 py-6 text-center text-gray-400">Sin datos.</td></tr></tbody>
    {% endif %}
  </table>
</div>
{% endfor %}
{% endblock %}
```

- [ ] **Step 6: Enlazar desde el historial**

Modify `templates/reportes/historial.html` — buscar el enlace existente a `reportes:contenedores_por_operador` y añadir junto a él:

```html
<a href="{% url 'reportes:entregas_vacios_por_operador' %}" class="text-sm text-blue-600 hover:underline">Entregas de vacíos por operador</a>
```

(Si no hubiera un contenedor obvio, colócalo dentro del mismo bloque/encabezado donde vive el enlace de contenedores por operador.)

- [ ] **Step 7: Correr los tests**

Run:
```bash
python manage.py test modulos.reportes --settings=test_settings -v 2
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add modulos/reportes templates/reportes
git commit -m "Vacíos: vista en pantalla del reporte de entregas por operador"
```

---

## Task 11: Navegación, tarjeta del dashboard principal y documentación

**Files:**
- Modify: `config/views.py` (`IndexView.get_context_data`)
- Modify: `templates/base.html` (enlace de navegación)
- Modify: `templates/index.html` (tarjeta de vacíos)
- Modify: `CLAUDE.md`
- Modify: `config/tests.py` o crear `modulos/vacios/tests.py` clase `DashboardPrincipalTests` (según dónde vivan los tests de `IndexView`; si no hay, añadir a `modulos/vacios/tests.py`)

**Interfaces:**
- Consumes: `modulos.vacios.models.Vacio`.
- Produces: `IndexView` deja en contexto `vacios_por_vaciar`, `vacios_en_patio`, `vacios_retrasos_abiertos`.

- [ ] **Step 1: Escribir el test**

Add to `modulos/vacios/tests.py`:

```python
class DashboardPrincipalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client.force_login(User.objects.create_user('t', password='x'))

    def test_index_incluye_conteos_de_vacios(self):
        Vacio.objects.create(bitacora_viaje=_bitacora(), contenedor='A', fecha_entrega_cliente=timezone.now())
        Vacio.objects.create(
            bitacora_viaje=_bitacora(), contenedor='B', fecha_entrega_cliente=timezone.now(),
            estado='EN_PATIO_ESPERANZA',
        )
        resp = self.client.get(reverse('inicio'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['vacios_por_vaciar'], 1)
        self.assertEqual(resp.context['vacios_en_patio'], 1)
        self.assertEqual(resp.context['vacios_retrasos_abiertos'], 0)
```

> Verifica el `name` de la ruta del dashboard en `config/urls.py` (`inicio`). Si fuera otro, ajústalo aquí.

- [ ] **Step 2: Correr para verlo fallar**

Run: `python manage.py test modulos.vacios.tests.DashboardPrincipalTests --settings=test_settings -v 2`
Expected: FAIL (`KeyError: 'vacios_por_vaciar'`).

- [ ] **Step 3: Ampliar `IndexView`**

Modify `config/views.py`:

Añadir el import junto a los demás:

```python
from modulos.vacios.models import Vacio
```

Al final de `get_context_data`, antes del `return context`:

```python
        # ========== Estadísticas de Vacíos ==========
        vacios_qs = Vacio.objects.all()
        context['vacios_por_vaciar'] = vacios_qs.filter(estado='POR_VACIAR').count()
        context['vacios_en_patio'] = vacios_qs.filter(estado='EN_PATIO_ESPERANZA').count()
        context['vacios_retrasos_abiertos'] = (
            vacios_qs.filter(tiene_retraso=True).exclude(estado='ENTREGADO_NAVIERA').count()
        )
```

- [ ] **Step 4: Enlace en la navegación**

Modify `templates/base.html` — después del bloque `<!-- Modulación -->` (el `<a href="{% url 'modulacion:dashboard' %}" ...>` y su `</a>` / cierre de `<li>`), añadir un bloque análogo:

```html
                    <!-- Vacíos -->
                    <li>
                        <a href="{% url 'vacios:dashboard' %}"
                           class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition
                                  {% if ns == 'vacios' %}nav-active{% else %}text-slate-400 hover:text-white hover:bg-slate-800{% endif %}">
                            <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
                            </svg>
                            <span>Vacíos</span>
                        </a>
                    </li>
```

(Copia la estructura exacta del `<li>` de Modulación que ya exista en el archivo; lo importante es `{% url 'vacios:dashboard' %}` y `ns == 'vacios'`.)

- [ ] **Step 5: Tarjeta en `templates/index.html`**

Modify `templates/index.html` — localizar la tarjeta/sección de Modulación y añadir una equivalente para Vacíos usando las variables nuevas:

```html
<div class="bg-white rounded-xl border border-gray-100 p-5">
  <h3 class="text-sm font-semibold text-gray-800 mb-3">Vacíos</h3>
  <div class="grid grid-cols-3 gap-3 text-center">
    <div><div class="text-xl font-bold text-gray-900">{{ vacios_por_vaciar }}</div><div class="text-xs text-gray-500">Por vaciar</div></div>
    <div><div class="text-xl font-bold text-gray-900">{{ vacios_en_patio }}</div><div class="text-xs text-gray-500">En patio</div></div>
    <div><div class="text-xl font-bold text-red-600">{{ vacios_retrasos_abiertos }}</div><div class="text-xs text-gray-500">Retrasos</div></div>
  </div>
  <a href="{% url 'vacios:dashboard' %}" class="mt-3 inline-block text-sm text-blue-600 hover:underline">Ir a Vacíos</a>
</div>
```

- [ ] **Step 6: Actualizar `CLAUDE.md`**

Modify `CLAUDE.md`:

- En la tabla de "Core Modules", añadir fila:

```
| **vacios** | Retorno de contenedores vacíos a la naviera | `Vacio`, `Naviera`, `RetrasoVacio`, `CambioOperadorVacio` |
```

- En "Project Structure" → lista de `modulos/`, añadir `├── vacios/`.
- En "URL Structure", añadir `/vacios/            → vacios app`.
- En "Django Signals", cambiar la nota "(combustible, taller, almacen only)" para incluir `vacios`, y añadir:

```
**vacios/signals.py:**
- `post_save` sobre `BitacoraViaje`: crea un `Vacio` por contenedor con fecha de entrega registrada (`fecha_hora_entrega` / `fecha_hora_entrega_2`). Idempotente; solo crea, nunca borra.
```

- En "Folio Generation", añadir: `- `Vacio`: `VAC-YYYYMMDD-XXX``.
- En "Status Workflows", añadir:

```
**vacios:** POR_VACIAR → EN_PATIO_ESPERANZA → ASIGNADO → ENTREGADO_NAVIERA
```

- [ ] **Step 7: Correr toda la batería de tests afectada**

Run:
```bash
python manage.py test modulos.vacios modulos.reportes modulos.modulacion modulos.bitacoras --settings=test_settings -v 2
```
Expected: PASS en todas. Cero fallos, cero errores.

- [ ] **Step 8: Commit**

```bash
git add config/views.py templates/base.html templates/index.html CLAUDE.md modulos/vacios/tests.py
git commit -m "Vacíos: navegación, tarjeta en dashboard principal y documentación en CLAUDE.md"
```

---

## Self-Review (checklist ya ejecutado)

**1. Cobertura del spec:**

| Requisito del spec | Task |
|--------------------|------|
| Modelos `Naviera`, `Vacio`, `RetrasoVacio`, `CambioOperadorVacio` | 1 |
| `Agencia.email_contacto` | 1 |
| Folio `VAC-YYYYMMDD-XXX` con reintento | 1 |
| `unique_together(bitacora_viaje, numero_contenedor)` | 1 |
| Signal `post_save` sobre `BitacoraViaje`, 1 vacío por contenedor, FULL→2, idempotente, solo crea | 2 |
| Auto-llenado de `agencia` desde `bitacora.modulacion` | 2 |
| "Operador libre" (excluye modulación activa / vacío asignado / bitácora en curso) | 3 |
| Dashboard, lista con filtro mes/año, detalle | 4 |
| Transición `POR_VACIAR → EN_PATIO_ESPERANZA` (sella `fecha_retorno_patio`) | 5 |
| Asignación unidad→operador (sella `fecha_asignacion` 1 vez) con auto-llenado JS | 5 |
| Reasignación con `CambioOperadorVacio` (unidad/operador saliente y entrante, causa) | 5 |
| Salida y entrega a naviera (sin `BitacoraViaje`) | 5 |
| Edición de `naviera` / `agencia` / `fecha_compromiso_naviera` | 5 |
| Retraso estructurado (`tipo`, `motivo`, `fecha_estimada_nueva`) + `tiene_retraso` | 6 |
| Aviso automático por correo a la agencia; sin correo → warning + reenviar | 6 |
| `notificaciones.py` no lanza excepción, registra con logging | 6 |
| CRUD `Naviera` | 7 |
| Generador `VACIOS_ENTREGAS_SEMANAL` (semana ISO, cambios por causa, snapshot pendientes) | 8 |
| Generador `VACIOS_RETRASOS` (por tipo, % notificados) | 8 |
| Registro en `generar_reportes`, `ConfiguracionReporte` choices + migración, narrativa | 9 |
| Vista en pantalla `EntregasVaciosPorOperadorView` + enlace en historial | 10 |
| Enlace de navegación, tarjeta en `IndexView`, `CLAUDE.md` | 11 |

Sin huecos.

**2. Placeholders:** Ninguno — todos los pasos con código muestran el código completo. Las dos notas de "ajusta si el `name` difiere" (`inicio`, enlace en `historial.html`) son verificaciones puntuales contra el código existente, no trabajo diferido.

**3. Consistencia de tipos/nombres:**
- `operadores_libres()` (Task 3) usada en `forms.py` (Task 5) y en `generadores/vacios.py` no la usa — OK.
- `notificar_retraso_agencia(retraso) -> bool` definida en Task 6, usada en Task 6 (vistas) — firma consistente.
- Claves de `resumen` de los generadores (Task 8) usadas en el template de Task 10 (`total_entregados`, `operadores_activos`, `cambios_operador_total`, `vacios_pendientes`) y en tests de Task 8 — consistentes.
- URL names: `vacios:registrar_retraso` referenciada en el template de Task 5 y definida en Task 6 — anotado explícitamente en Task 5, Step 7/8.
- `ESTADO_CHOICES` idéntico en modelo (Task 1), vistas y tests.
- Migraciones: `makemigrations vacios modulacion` (Task 1), `makemigrations reportes` (Task 9) — dos rondas, sin solapamiento.
