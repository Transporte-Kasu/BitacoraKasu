from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Max, Q
from django.utils import timezone


class Agencia(models.Model):
    """Agente aduanal/despachante que gestiona la operación (ej. LOGINCO)."""
    nombre = models.CharField(max_length=120, unique=True, verbose_name="Nombre")
    activo = models.BooleanField(default=True, verbose_name="Activo")
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Terminal portuaria"
        verbose_name_plural = "Terminales portuarias"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


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
    ]

    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de modulación'),
        ('MODULADO', 'Modulado'),
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
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE', verbose_name="Estado")

    bitacora_viaje = models.OneToOneField(
        'bitacoras.BitacoraViaje',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modulacion',
        verbose_name="Bitácora de viaje",
    )
    transportista_externo = models.CharField(max_length=120, blank=True, verbose_name="Transportista externo")

    fecha_recepcion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de recepción")
    fecha_retiro = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de retiro")

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
        if not self.folio:
            fecha = timezone.now().strftime('%Y%m%d')
            ultimo = Modulacion.objects.filter(folio__startswith=f'MOD-{fecha}').aggregate(
                Max('folio')
            )['folio__max']

            if ultimo:
                numero = int(ultimo.split('-')[-1]) + 1
            else:
                numero = 1

            self.folio = f'MOD-{fecha}-{numero:03d}'

        super().save(*args, **kwargs)
