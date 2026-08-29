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
