from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from modulos.unidades.models import Unidad
from decimal import Decimal

from config.storage_backends import MediaStorage


class Despachador(models.Model):
    """Modelo para los despachadores de combustible"""
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='despachador',
        verbose_name="Usuario"
    )
    nombre = models.CharField(max_length=100, verbose_name="Nombre completo")
    telefono = models.CharField(max_length=15, blank=True, verbose_name="Teléfono")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Despachador"
        verbose_name_plural = "Despachadores"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class CargaCombustible(models.Model):
    """Modelo para el registro de carga de combustible"""

    NIVEL_COMBUSTIBLE_CHOICES = [
        ('VACIO', 'Vacío'),
        ('CUARTO', '1/4'),
        ('MEDIO', '1/2'),
        ('TRES_CUARTOS', '3/4'),
    ]

    ESTADO_CANDADO_CHOICES = [
        ('NORMAL', 'Normal'),
        ('ALTERADO', 'Alterado'),
        ('VIOLADO', 'Violado'),
        ('SIN_CANDADO', 'Sin candado'),
    ]

    ESTADO_CHOICES = [
        ('INICIADO', 'Iniciado'),
        ('EN_PROCESO', 'En proceso de carga'),
        ('COMPLETADO', 'Completado'),
        ('CANCELADO', 'Cancelado'),
    ]

    # Relaciones
    despachador = models.ForeignKey(
        Despachador,
        on_delete=models.PROTECT,
        related_name='cargas',
        verbose_name="Despachador"
    )
    unidad = models.ForeignKey(
        Unidad,
        on_delete=models.PROTECT,
        related_name='cargas_combustible',
        verbose_name="Unidad"
    )

    # Datos de la carga
    cantidad_litros = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Cantidad de litros cargados"
    )

    # Datos del tablero (Paso 2)
    kilometraje_actual = models.IntegerField(
        validators=[MinValueValidator(0)],
        verbose_name="Kilometraje actual"
    )
    nivel_combustible_inicial = models.CharField(
        max_length=20,
        choices=NIVEL_COMBUSTIBLE_CHOICES,
        verbose_name="Nivel de combustible inicial"
    )

    # Estado del candado anterior (Paso 3)
    estado_candado_anterior = models.CharField(
        max_length=20,
        choices=ESTADO_CANDADO_CHOICES,
        verbose_name="Estado del candado anterior"
    )
    observaciones_candado = models.TextField(
        blank=True,
        verbose_name="Observaciones del candado"
    )

    # Tiempos de carga (Paso 4)
    fecha_hora_inicio = models.DateTimeField(
        verbose_name="Fecha y hora de inicio"
    )
    fecha_hora_fin = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha y hora de finalización"
    )
    tiempo_carga_minutos = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Tiempo de carga (minutos)"
    )

    # Fotos del proceso
    foto_numero_economico = models.ImageField(
        storage=MediaStorage(),
        upload_to='combustible/numero_economico/%Y/%m/',
        verbose_name="Foto número económico"
    )
    foto_tablero = models.ImageField(
        storage=MediaStorage(),
        upload_to='combustible/tablero/%Y/%m/',
        verbose_name="Foto del tablero"
    )
    foto_candado_anterior = models.ImageField(
        storage=MediaStorage(),
        upload_to='combustible/candado_anterior/%Y/%m/',
        verbose_name="Foto candado anterior"
    )
    foto_candado_nuevo = models.ImageField(
        storage=MediaStorage(),
        upload_to='combustible/candado_nuevo/%Y/%m/',
        null=True,
        blank=True,
        verbose_name="Foto candado nuevo"
    )
    foto_ticket = models.ImageField(
        storage=MediaStorage(),
        upload_to='combustible/tickets/%Y/%m/',
        null=True,
        blank=True,
        verbose_name="Foto del ticket o medidor"
    )

    # Estado y control
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='INICIADO',
        verbose_name="Estado de la carga"
    )

    # Metadatos
    notas = models.TextField(blank=True, verbose_name="Notas adicionales")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Carga de Combustible"
        verbose_name_plural = "Cargas de Combustible"
        ordering = ['-fecha_hora_inicio']
        indexes = [
            models.Index(fields=['unidad', '-fecha_hora_inicio']),
            models.Index(fields=['despachador', '-fecha_hora_inicio']),
            models.Index(fields=['estado', '-fecha_hora_inicio']),
        ]

    def __str__(self):
        return f"Carga {self.id} - {self.unidad.numero_economico} - {self.fecha_hora_inicio.strftime('%d/%m/%Y %H:%M')}"

    def save(self, *args, **kwargs):
        # Calcular tiempo de carga si ambas fechas están presentes
        if self.fecha_hora_inicio and self.fecha_hora_fin:
            diferencia = self.fecha_hora_fin - self.fecha_hora_inicio
            self.tiempo_carga_minutos = int(diferencia.total_seconds() / 60)

        # Actualizar kilometraje de la unidad si la carga está completada
        if self.estado == 'COMPLETADO' and self.unidad:
            self.unidad.kilometraje_actual = self.kilometraje_actual
            self.unidad.save(update_fields=['kilometraje_actual'])

        super().save(*args, **kwargs)

    def iniciar_carga(self):
        """Marca el inicio del proceso de carga"""
        self.fecha_hora_inicio = timezone.now()
        self.estado = 'EN_PROCESO'
        self.save()

    def finalizar_carga(self):
        """Marca la finalización del proceso de carga"""
        self.fecha_hora_fin = timezone.now()
        self.estado = 'COMPLETADO'
        self.save()

    def calcular_rendimiento(self):
        """Calcula el rendimiento aproximado basado en la carga"""
        if self.cantidad_litros > 0 and self.unidad:
            # Estimación simple, puede mejorarse con datos históricos
            return round(float(self.unidad.rendimiento_esperado), 2)
        return 0

    def tiene_alertas(self):
        """Verifica si hay alertas en el candado"""
        return self.estado_candado_anterior in ['ALTERADO', 'VIOLADO', 'SIN_CANDADO']


class AlertaCombustible(models.Model):
    """Alertas generadas automáticamente en cargas de combustible"""

    TIPO_CHOICES = [
        ('CANDADO_ALTERADO', 'Candado Alterado'),
        ('CANDADO_VIOLADO', 'Candado Violado'),
        ('SIN_CANDADO', 'Sin Candado'),
        ('EXCESO_COMBUSTIBLE', 'Exceso de Combustible'),
    ]

    carga = models.ForeignKey(
        CargaCombustible,
        on_delete=models.CASCADE,
        related_name='alertas',
        verbose_name="Carga de combustible"
    )
    tipo_alerta = models.CharField(
        max_length=30,
        choices=TIPO_CHOICES,
        verbose_name="Tipo de alerta"
    )
    mensaje = models.TextField(verbose_name="Mensaje")
    fecha_generacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de generación")
    resuelta = models.BooleanField(default=False, verbose_name="Resuelta")
    resuelta_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alertas_combustible_resueltas',
        verbose_name="Resuelta por"
    )
    fecha_resolucion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de resolución")

    class Meta:
        verbose_name = "Alerta de Combustible"
        verbose_name_plural = "Alertas de Combustible"
        ordering = ['-fecha_generacion']

    def __str__(self):
        return f"{self.get_tipo_alerta_display()} - Carga {self.carga_id}"

    def resolver(self, usuario):
        """Marca la alerta como resuelta"""
        self.resuelta = True
        self.resuelta_por = usuario
        self.fecha_resolucion = timezone.now()
        self.save()


class FotoCandadoNuevo(models.Model):
    """Modelo para almacenar múltiples fotos del candado nuevo"""
    carga = models.ForeignKey(
        CargaCombustible,
        on_delete=models.CASCADE,
        related_name='fotos_candado_nuevo',
        verbose_name="Carga de combustible"
    )
    foto = models.ImageField(
        storage=MediaStorage(),
        upload_to='combustible/candado_nuevo/%Y/%m/',
        verbose_name="Foto del candado nuevo"
    )
    descripcion = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Descripción",
        help_text="Ej: Tanque 1, Tanque 2"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Foto de Candado Nuevo"
        verbose_name_plural = "Fotos de Candado Nuevo"
        ordering = ['created_at']

    def __str__(self):
        return f"Foto candado - Carga {self.carga_id} - {self.descripcion or self.id}"