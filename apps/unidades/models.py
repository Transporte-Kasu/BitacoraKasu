from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal


class Unidad(models.Model):
    """
    Modelo para gestionar las unidades de transporte
    Ubicación: apps/unidades/models.py
    """
    TIPO_CHOICES = [
        ('LOCAL', 'Local'),
        ('FORANEA', 'Foránea'),
        ('ESPERANZA', 'Esperanza'),
    ]
    
    # Identificación
    numero_economico = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="Número económico"
    )
    placa = models.CharField(
        max_length=10,
        verbose_name="Placa vehicular"
    )
    
    # Clasificación
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        verbose_name="Tipo de unidad"
    )
    
    # Especificaciones técnicas
    marca = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Marca"
    )
    modelo = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Modelo"
    )
    año = models.IntegerField(
        validators=[
            MinValueValidator(1990),
            MaxValueValidator(2030)
        ],
        verbose_name="Año"
    )
    
    # Capacidades y rendimiento
    capacidad_combustible = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Capacidad de combustible (litros)"
    )
    rendimiento_esperado = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Rendimiento esperado en km/litro",
        verbose_name="Rendimiento esperado (km/lt)"
    )
    
    # Kilometraje
    kilometraje_actual = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Kilometraje actual"
    )
    
    # Estado
    activa = models.BooleanField(
        default=True,
        verbose_name="Unidad activa"
    )
    fecha_alta = models.DateField(
        auto_now_add=True,
        verbose_name="Fecha de alta"
    )
    fecha_baja = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de baja"
    )
    
    # Mantenimiento
    ultimo_mantenimiento = models.DateField(
        null=True,
        blank=True,
        verbose_name="Último mantenimiento"
    )
    proximo_mantenimiento = models.DateField(
        null=True,
        blank=True,
        verbose_name="Próximo mantenimiento"
    )
    
    # Metadatos
    notas = models.TextField(
        blank=True,
        verbose_name="Notas adicionales"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Unidad"
        verbose_name_plural = "Unidades"
        ordering = ['numero_economico']
        indexes = [
            models.Index(fields=['tipo', 'activa']),
            models.Index(fields=['numero_economico']),
        ]
    
    def __str__(self):
        return f"Unidad {self.numero_economico} - {self.placa}"
    
    def rendimiento_promedio_real(self):
        """Calcula el rendimiento promedio real basado en bitácoras"""
        viajes = self.bitacoras.filter(
            fecha_llegada__isnull=False,
            diesel_cargado__gt=0
        )
        
        if not viajes.exists():
            return 0
        
        rendimientos = [v.rendimiento_combustible for v in viajes if v.rendimiento_combustible > 0]
        return round(sum(rendimientos) / len(rendimientos), 2) if rendimientos else 0
    
    def eficiencia_combustible(self):
        """
        Calcula porcentaje de eficiencia vs rendimiento esperado
        Retorna un valor entre 0-100+
        """
        rendimiento_real = self.rendimiento_promedio_real()
        if rendimiento_real == 0 or self.rendimiento_esperado == 0:
            return 0
        
        eficiencia = (float(rendimiento_real) / float(self.rendimiento_esperado)) * 100
        return round(eficiencia, 2)
    
    def requiere_mantenimiento(self):
        """Verifica si la unidad requiere mantenimiento"""
        if not self.proximo_mantenimiento:
            return False
        return self.proximo_mantenimiento <= timezone.now().date()
    
    def viajes_completados(self):
        """Retorna el número de viajes completados"""
        return self.bitacoras.filter(fecha_llegada__isnull=False).count()