from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class Operador(models.Model):
    """
    Modelo para gestionar los operadores de transporte
    Ubicación: apps/operadores/models.py
    """
    TIPO_CHOICES = [
        ('LOCAL', 'Local'),
        ('FORANEO', 'Foráneo'),
        ('ESPERANZA', 'Foráneo Esperanza'),
    ]
    
    # Información básica
    nombre = models.CharField(
        max_length=200,
        verbose_name="Nombre completo"
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        verbose_name="Tipo de operador"
    )
    
    # Asignación de unidad (relación con otra app)
    unidad_asignada = models.ForeignKey(
        'unidades.Unidad',  # Referencia a otra aplicación
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operadores',
        verbose_name="Unidad asignada"
    )
    
    # Documentación
    licencia = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Número de licencia"
    )
    telefono = models.CharField(
        max_length=15,
        blank=True,
        verbose_name="Teléfono de contacto"
    )
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Correo electrónico"
    )
    
    # Estado y fechas
    activo = models.BooleanField(
        default=True,
        verbose_name="Operador activo"
    )
    fecha_ingreso = models.DateField(
        auto_now_add=True,
        verbose_name="Fecha de ingreso"
    )
    fecha_baja = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de baja"
    )
    
    # Metadatos
    notas = models.TextField(
        blank=True,
        verbose_name="Notas adicionales"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Operador"
        verbose_name_plural = "Operadores"
        ordering = ['nombre']
        indexes = [
            models.Index(fields=['tipo', 'activo']),
            models.Index(fields=['nombre']),
        ]
    
    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"
    
    def horas_trabajadas_periodo(self, fecha_inicio, fecha_fin):
        """Calcula horas trabajadas en un período"""
        viajes = self.bitacoras.filter(
            fecha_salida__gte=fecha_inicio,
            fecha_llegada__lte=fecha_fin,
            fecha_llegada__isnull=False
        )
        
        total_horas = sum(v.horas_viaje for v in viajes)
        return round(total_horas, 2)
    
    def viajes_completados(self):
        """Retorna el número de viajes completados"""
        return self.bitacoras.filter(fecha_llegada__isnull=False).count()
    
    def promedio_rendimiento(self):
        """Calcula el rendimiento promedio de combustible"""
        viajes = self.bitacoras.filter(
            fecha_llegada__isnull=False,
            diesel_cargado__gt=0
        )
        
        if not viajes.exists():
            return 0
        
        rendimientos = [v.rendimiento_combustible for v in viajes if v.rendimiento_combustible > 0]
        return round(sum(rendimientos) / len(rendimientos), 2) if rendimientos else 0