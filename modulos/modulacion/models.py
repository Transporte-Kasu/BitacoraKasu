from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.utils import timezone


class Agencia(models.Model):
    """Agente aduanal/despachante que gestiona la operación (ej. LOGINCO)."""
    nombre = models.CharField(max_length=120, unique=True, verbose_name="Nombre")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    email_contacto = models.EmailField(
        blank=True,
        verbose_name="Correo de contacto",
        help_text="Destino de los avisos automáticos de retraso de vacíos.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Agencia"
        verbose_name_plural = "Agencias"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class TerminalPortuaria(models.Model):
    """Recinto fiscalizado/terminal portuaria donde se encuentra el contenedor."""
    nombre = models.CharField(max_length=120, unique=True, verbose_name="Nombre")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    requiere_datos_extra = models.BooleanField(
        default=False,
        verbose_name="Requiere datos de terminal",
        help_text="Si está activo, el correo de HAL9MIL incluye un link para "
                   "que el capturista complete carril/horarios de este contenedor.",
    )
    requiere_carril = models.BooleanField(default=False, verbose_name="Requiere carril")
    requiere_hora_ingreso = models.BooleanField(default=False, verbose_name="Requiere hora de ingreso")
    requiere_hora_carga = models.BooleanField(default=False, verbose_name="Requiere hora de carga")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Terminal portuaria"
        verbose_name_plural = "Terminales portuarias"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


TRANSICIONES_MODULACION = {
    'PENDIENTE': ['ASIGNADO'],
    'MODULADO': ['ASIGNADO'],
    'ASIGNADO': ['INGRESADO'],
    'INGRESADO': ['DESADUANAMIENTO_LIBRE', 'RECONOCIMIENTO_ADUANAL'],
    'DESADUANAMIENTO_LIBRE': ['VERIFICACION_EN_TRANSPORTE', 'EN_PATIO_ESPERANZA'],
    'RECONOCIMIENTO_ADUANAL': ['RETENIDO', 'EN_PATIO_ESPERANZA'],
    'RETENIDO': ['EN_PATIO_ESPERANZA'],
    'VERIFICACION_EN_TRANSPORTE': ['EN_PATIO_ESPERANZA'],
    'EN_PATIO_ESPERANZA': ['ENVIADO_BITACORA', 'RETIRADO_TERCERO'],
    'ENVIADO_BITACORA': [],
    'RETIRADO_TERCERO': [],
}

# Estados que muestra el tablero de Atención a Clientes (ni iniciales ni terminales).
ESTADOS_EN_SEGUIMIENTO = [
    'ASIGNADO', 'INGRESADO', 'DESADUANAMIENTO_LIBRE', 'RECONOCIMIENTO_ADUANAL',
    'RETENIDO', 'VERIFICACION_EN_TRANSPORTE', 'EN_PATIO_ESPERANZA',
]

_BADGE_POR_ESTADO = {
    'PENDIENTE': 'bg-gray-100 text-gray-700',
    'MODULADO': 'bg-gray-100 text-gray-700',
    'ASIGNADO': 'bg-indigo-100 text-indigo-700',
    'INGRESADO': 'bg-blue-100 text-blue-700',
    'DESADUANAMIENTO_LIBRE': 'bg-green-100 text-green-700',
    'RECONOCIMIENTO_ADUANAL': 'bg-red-100 text-red-700',
    'RETENIDO': 'bg-amber-100 text-amber-700',
    'VERIFICACION_EN_TRANSPORTE': 'bg-purple-100 text-purple-700',
    'EN_PATIO_ESPERANZA': 'bg-green-100 text-green-700',
    'ENVIADO_BITACORA': 'bg-blue-100 text-blue-700',
    'RETIRADO_TERCERO': 'bg-gray-100 text-gray-700',
}


# Transiciones con flujo dedicado propio (EnviarABitacoraView crea el
# BitacoraViaje; retirar_de_patio captura el transportista). NO se ofrecen como
# botón genérico de avance ni las acepta avanzar_estado_modulacion: llegar a
# ellas por `transicionar()` a secas dejaría la Modulación en estado terminal
# sin viaje / sin transportista y sin vuelta atrás.
TRANSICIONES_CON_FLUJO_DEDICADO = {'ENVIADO_BITACORA', 'RETIRADO_TERCERO'}


class TransicionInvalida(Exception):
    """Se intentó un cambio de estado que TRANSICIONES_MODULACION no permite."""


class Modulacion(models.Model):
    """
    Registro de un contenedor recibido para su extracción/modulación.
    Un registro = un contenedor. Puede llegar por API (HAL9MIL/LOGINCO) o
    capturarse manualmente. De aquí se promueve a BitacoraViaje (viaje local)
    o se envía al Patio Esperanza para su retiro posterior.
    """
    ORIGEN_CHOICES = [
        ('HAL9MIL', 'HAL9MIL / LOGINCO'),
        ('MANUAL', 'Captura manual'),
        ('LCTPC', 'Programación LCTPC'),
    ]

    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de modulación'),
        ('MODULADO', 'Modulado'),
        ('ASIGNADO', 'Asignado / pendiente de ingreso'),
        ('INGRESADO', 'Ingresado'),
        ('DESADUANAMIENTO_LIBRE', 'Desaduanamiento libre (verde)'),
        ('RECONOCIMIENTO_ADUANAL', 'Reconocimiento aduanal (rojo)'),
        ('RETENIDO', 'Retenido (esperando aduana)'),
        ('VERIFICACION_EN_TRANSPORTE', 'Verificación en transporte'),
        ('EN_PATIO_ESPERANZA', 'En Patio Esperanza'),
        ('ENVIADO_BITACORA', 'Enviado a Bitácora de Viajes'),
        ('RETIRADO_TERCERO', 'Retirado por transporte externo'),
    ]

    folio = models.CharField(max_length=20, unique=True, editable=False)

    agencia = models.ForeignKey(
        Agencia,
        on_delete=models.PROTECT,
        related_name='modulaciones',
        verbose_name="Agencia",
    )
    terminal_portuaria = models.ForeignKey(
        TerminalPortuaria,
        on_delete=models.PROTECT,
        related_name='modulaciones',
        verbose_name="Terminal portuaria",
    )
    tipo_contenedor = models.CharField(
        max_length=10,
        verbose_name="Tipo de contenedor",
        help_text="Ej. 20DC, 40HC (tal como llega del sistema de origen)",
    )
    peso_toneladas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Peso (toneladas)",
    )
    contenedor = models.CharField(max_length=50, verbose_name="Contenedor")
    cliente = models.ForeignKey(
        'bitacoras.Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modulaciones',
        verbose_name="Cliente",
    )
    num_pedimento = models.CharField(max_length=30, blank=True, verbose_name="Número de pedimento")
    num_doda = models.CharField(max_length=34, blank=True, verbose_name="Número de DODA")

    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default='MANUAL', verbose_name="Origen")
    estado = models.CharField(max_length=30, choices=ESTADO_CHOICES, default='PENDIENTE', verbose_name="Estado")

    unidad = models.ForeignKey(
        'unidades.Unidad',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modulaciones',
        verbose_name="Unidad asignada",
    )
    operador = models.ForeignKey(
        'operadores.Operador',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modulaciones',
        verbose_name="Operador asignado",
    )
    fecha_asignacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de asignación",
        help_text="Se sella la primera vez que se asigna unidad y operador.",
    )

    bitacora_viaje = models.OneToOneField(
        'bitacoras.BitacoraViaje',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modulacion',
        verbose_name="Bitácora de viaje",
    )
    transportista_externo = models.CharField(max_length=120, blank=True, verbose_name="Transportista externo")

    fecha_recepcion = models.DateTimeField(
        default=timezone.now,
        verbose_name="Fecha de recepción",
        help_text=(
            "Fecha real del DODA cuando el origen la manda (HAL9MIL); si no "
            "llega, la fecha en que se recibió el registro."
        ),
    )
    fecha_patio_esperanza = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de entrada a Patio Esperanza",
        help_text="Se sella la primera vez que el contenedor se manda a Patio Esperanza.",
    )
    fecha_retiro = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de retiro")

    carril = models.CharField(max_length=10, blank=True, verbose_name="Carril")
    tipo_cita = models.CharField(
        max_length=10,
        blank=True,
        choices=[('FULL', 'Full'), ('SENCILLO', 'Sencillo')],
        verbose_name="Tipo de cita",
        help_text="Clasificación FULL/SENCILLO derivada de la programación de la terminal.",
    )
    grupo_cita = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        verbose_name="Grupo de cita FULL",
        help_text="Comparten valor los 2 contenedores de un mismo FULL.",
    )
    hora_registro = models.DateTimeField(null=True, blank=True, verbose_name="Hora de registro")
    hora_ingreso = models.DateTimeField(null=True, blank=True, verbose_name="Hora de ingreso")
    hora_carga = models.DateTimeField(null=True, blank=True, verbose_name="Hora de carga")
    fecha_modulacion_aduana = models.DateField(
        null=True, blank=True, verbose_name="Fecha de modulación ante aduana",
    )

    observaciones = models.TextField(blank=True, verbose_name="Observaciones")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Modulación"
        verbose_name_plural = "Modulaciones"
        ordering = ['-fecha_recepcion']
        constraints = [
            models.UniqueConstraint(
                fields=['num_doda', 'contenedor'],
                condition=Q(num_doda__gt=''),
                name='uniq_doda_contenedor',
            )
        ]

    def __str__(self):
        return f"{self.folio} - {self.contenedor}"

    def save(self, *args, **kwargs):
        if self.folio:
            super().save(*args, **kwargs)
            return

        # Generación de folio con reintento ante colisión: con
        # --workers 1 --threads 4 (ver Procfile), dos requests concurrentes a
        # recibir_modulacion (p.ej. dos patentes de HAL9MIL sincronizando casi
        # al mismo tiempo) pueden calcular el mismo consecutivo antes de que
        # cualquiera haga commit. select_for_update() serializa contra el
        # último folio del día ya existente; el reintento cubre además el caso
        # límite del primer folio del día (sin fila que bloquear todavía).
        #
        # El folio se agrupa por fecha_recepcion (que ya trae la fecha real
        # del DODA cuando el origen la manda) y no por "ahora": un reintento
        # masivo de historial atrasado no debe amontonar cientos de folios
        # bajo el día en que se corrió el reintento.
        fecha = self.fecha_recepcion.strftime('%Y%m%d')
        ultimo_error = None
        for _intento in range(5):
            with transaction.atomic():
                ultimo = (
                    Modulacion.objects
                    .select_for_update()
                    .filter(folio__startswith=f'MOD-{fecha}')
                    .order_by('-folio')
                    .first()
                )
                numero = int(ultimo.folio.split('-')[-1]) + 1 if ultimo else 1
                self.folio = f'MOD-{fecha}-{numero:03d}'
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

    @property
    def badge_class(self):
        """Clase Tailwind del chip de estado (para plantillas)."""
        return _BADGE_POR_ESTADO.get(self.estado, 'bg-gray-100 text-gray-700')

    @property
    def transiciones_validas(self):
        """[(clave, label)] de transiciones que se avanzan con un botón simple.

        Excluye las que tienen flujo dedicado (ENVIADO_BITACORA /
        RETIRADO_TERCERO): esas se hacen por EnviarABitacoraView /
        retirar_de_patio, no por avanzar_estado_modulacion.
        """
        labels = dict(self.ESTADO_CHOICES)
        return [
            (c, labels[c])
            for c in TRANSICIONES_MODULACION.get(self.estado, [])
            if c not in TRANSICIONES_CON_FLUJO_DEDICADO
        ]

    def transicionar(self, nuevo_estado, *, usuario=None, nota=''):
        """Cambia de estado validando contra TRANSICIONES_MODULACION y deja
        una fila de SeguimientoModulacion. Lanza TransicionInvalida si el
        salto no está permitido desde el estado actual."""
        if nuevo_estado not in TRANSICIONES_MODULACION.get(self.estado, []):
            raise TransicionInvalida(
                f'{self.folio}: no se puede pasar de {self.estado} a {nuevo_estado}.'
            )
        with transaction.atomic():
            self.estado = nuevo_estado
            if nuevo_estado == 'EN_PATIO_ESPERANZA' and self.fecha_patio_esperanza is None:
                self.fecha_patio_esperanza = timezone.now()
            if nuevo_estado == 'RETIRADO_TERCERO' and self.fecha_retiro is None:
                self.fecha_retiro = timezone.now()
            self.save()
            SeguimientoModulacion.objects.create(
                modulacion=self, estado=nuevo_estado, usuario=usuario, nota=nota,
            )


class ImportacionProgramacionLCTPC(models.Model):
    """
    Auditoría e idempotencia de cada correo de programación de citas de LCTPC
    (`atencionspf@lctpc.com.mx`) procesado por el import automático.
    Un registro = un correo. `graph_message_id` único evita reprocesar.
    """
    ESTADO_CHOICES = [
        ('OK', 'Procesado sin avisos'),
        ('OK_CON_AVISOS', 'Procesado con avisos'),
        ('ERROR', 'Error al procesar'),
    ]

    graph_message_id = models.CharField(max_length=255, unique=True, verbose_name="ID de mensaje (Graph)")
    asunto = models.CharField(max_length=300, verbose_name="Asunto")
    fecha_recibido = models.DateTimeField(verbose_name="Fecha de recepción del correo")
    fecha_modulacion_aduana = models.DateField(
        null=True, blank=True, verbose_name="Fecha de modulación ante aduana",
    )
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, verbose_name="Estado")
    total_renglones = models.PositiveIntegerField(default=0, verbose_name="Renglones en el Excel")
    creadas = models.PositiveIntegerField(default=0, verbose_name="Modulaciones creadas")
    actualizadas = models.PositiveIntegerField(default=0, verbose_name="Modulaciones actualizadas")
    ambiguas = models.PositiveIntegerField(default=0, verbose_name="Coincidencias ambiguas")
    detalle = models.JSONField(
        default=list, blank=True,
        verbose_name="Detalle por contenedor",
        help_text="[{contenedor, folio_lctpc, resultado, modulacion_id, tipo_cita}]",
    )
    mensaje_error = models.TextField(blank=True, verbose_name="Error / avisos")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Importación de programación LCTPC"
        verbose_name_plural = "Importaciones de programación LCTPC"
        ordering = ['-fecha_recibido']

    def __str__(self):
        return f"{self.asunto} ({self.estado})"


class SeguimientoModulacion(models.Model):
    """Historial de cambios de estado de una Modulación. Una fila por
    transición hecha vía `Modulacion.transicionar()`."""
    modulacion = models.ForeignKey(
        Modulacion, on_delete=models.CASCADE, related_name='seguimientos',
        verbose_name="Modulación",
    )
    estado = models.CharField(
        max_length=30, choices=Modulacion.ESTADO_CHOICES, verbose_name="Estado",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Usuario",
    )
    nota = models.TextField(blank=True, verbose_name="Nota")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Seguimiento de modulación"
        verbose_name_plural = "Seguimientos de modulación"
        ordering = ['creado_en']

    def __str__(self):
        return f"{self.modulacion.folio} → {self.get_estado_display()}"

    @property
    def badge_class(self):
        return _BADGE_POR_ESTADO.get(self.estado, 'bg-gray-100 text-gray-700')
