from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
import os


class BitacoraViaje(models.Model):
    """
    Modelo para registrar cada viaje realizado
    Ubicación: apps/bitacoras/models.py
    """
    MODALIDAD_CHOICES = [
        ('SENCILLO', 'Sencillo'),
        ('FULL', 'Full'),
    ]
    
    # Relaciones con otras aplicaciones
    operador = models.ForeignKey(
        'operadores.Operador',  # Referencia a otra aplicación
        on_delete=models.PROTECT,
        related_name='bitacoras',
        verbose_name="Operador"
    )
    unidad = models.ForeignKey(
        'unidades.Unidad',  # Referencia a otra aplicación
        on_delete=models.PROTECT,
        related_name='bitacoras',
        verbose_name="Unidad"
    )
    
    # Información del viaje
    modalidad = models.CharField(
        max_length=20,
        choices=MODALIDAD_CHOICES,
        verbose_name="Modalidad"
    )
    contenedor = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Número de contenedor"
    )
    peso = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Peso (kg)"
    )
    
    # Fechas y horas
    fecha_carga = models.DateTimeField(
        verbose_name="Fecha/hora de carga"
    )
    fecha_salida = models.DateTimeField(
        verbose_name="Fecha/hora de salida"
    )
    fecha_llegada = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha/hora de llegada"
    )
    
    # Combustible y kilometraje
    diesel_cargado = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Diesel cargado (litros)"
    )
    kilometraje_salida = models.IntegerField(
        validators=[MinValueValidator(0)],
        verbose_name="Kilometraje de salida"
    )
    kilometraje_llegada = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Kilometraje de llegada"
    )
    
    # Ubicación
    cp_origen = models.CharField(
        max_length=10,
        default='40812',
        verbose_name="Código postal origen"
    )
    cp_destino = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="Código postal destino"
    )
    destino = models.TextField(
        verbose_name="Destino (descripción)"
    )
    
    # Datos calculados de Google Maps
    distancia_calculada = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distancia en kilómetros según Google Maps",
        verbose_name="Distancia calculada (km)"
    )
    duracion_estimada = models.IntegerField(
        null=True,
        blank=True,
        help_text="Duración estimada en minutos según Google Maps",
        verbose_name="Duración estimada (min)"
    )
    
    # Seguridad
    sellos = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Números de sellos"
    )
    
    # Control adicional
    reparto = models.BooleanField(
        default=False,
        verbose_name="Viaje con reparto"
    )
    observaciones = models.TextField(
        blank=True,
        verbose_name="Observaciones"
    )
    
    # Estado del viaje
    completado = models.BooleanField(
        default=False,
        verbose_name="Viaje completado"
    )
    
    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Bitácora de viaje"
        verbose_name_plural = "Bitácoras de viajes"
        ordering = ['-fecha_salida']
        indexes = [
            models.Index(fields=['-fecha_salida']),
            models.Index(fields=['operador', 'fecha_salida']),
            models.Index(fields=['unidad', 'fecha_salida']),
            models.Index(fields=['completado']),
        ]
    
    def __str__(self):
        return f"Viaje {self.id} - {self.unidad} ({self.fecha_salida.strftime('%Y-%m-%d')})"
    
    # ========================================================================
    # PROPIEDADES CALCULADAS
    # ========================================================================
    
    @property
    def kilometros_recorridos(self):
        """Calcula kilómetros recorridos basados en odómetro"""
        if self.kilometraje_llegada and self.kilometraje_salida:
            return self.kilometraje_llegada - self.kilometraje_salida
        return 0
    
    @property
    def rendimiento_combustible(self):
        """Calcula rendimiento real de combustible (km/lt)"""
        if self.diesel_cargado > 0 and self.kilometros_recorridos > 0:
            return round(float(self.kilometros_recorridos) / float(self.diesel_cargado), 2)
        return 0
    
    @property
    def horas_viaje(self):
        """Calcula horas totales de viaje"""
        if self.fecha_llegada and self.fecha_salida:
            delta = self.fecha_llegada - self.fecha_salida
            return round(delta.total_seconds() / 3600, 2)
        return 0
    
    @property
    def velocidad_promedio(self):
        """Calcula velocidad promedio del viaje (km/h)"""
        if self.horas_viaje > 0 and self.kilometros_recorridos > 0:
            return round(self.kilometros_recorridos / self.horas_viaje, 2)
        return 0
    
    @property
    def eficiencia_vs_esperado(self):
        """
        Calcula porcentaje de eficiencia vs rendimiento esperado de la unidad
        """
        if self.unidad and self.unidad.rendimiento_esperado > 0 and self.rendimiento_combustible > 0:
            eficiencia = (self.rendimiento_combustible / float(self.unidad.rendimiento_esperado)) * 100
            return round(eficiencia, 2)
        return 0
    
    @property
    def diferencia_distancias(self):
        """
        Compara distancia real vs calculada por Google Maps
        Retorna diferencia en kilómetros
        """
        if self.distancia_calculada and self.kilometros_recorridos > 0:
            return round(self.kilometros_recorridos - float(self.distancia_calculada), 2)
        return None
    
    @property
    def alerta_bajo_rendimiento(self):
        """Verifica si el rendimiento está por debajo del umbral (2.5 km/lt)"""
        return self.rendimiento_combustible > 0 and self.rendimiento_combustible < 2.5
    
    # ========================================================================
    # MÉTODOS
    # ========================================================================
    
    def calcular_distancia_google(self, api_key=None):
        """
        Calcula distancia y duración usando Google Distance Matrix API
        Retorna: dict con 'distancia_km', 'duracion_min', 'status'
        """
        from core.services.google_maps import GoogleMapsService
        
        if not api_key:
            api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
        
        if not api_key:
            return {
                'status': 'error',
                'message': 'No se encontró API key de Google Maps'
            }
        
        if not self.cp_destino:
            return {
                'status': 'error',
                'message': 'No hay código postal de destino'
            }
        
        try:
            maps_service = GoogleMapsService(api_key)
            resultado = maps_service.calcular_distancia(self.cp_origen, self.cp_destino)
            
            if resultado['success']:
                # Guardar en el modelo
                self.distancia_calculada = Decimal(str(round(resultado['distancia_km'], 2)))
                self.duracion_estimada = int(resultado['duracion_min'])
                self.save(update_fields=['distancia_calculada', 'duracion_estimada'])
                
                return {
                    'status': 'success',
                    'distancia_km': resultado['distancia_km'],
                    'duracion_min': resultado['duracion_min'],
                    'distancia_texto': resultado['distancia_texto'],
                    'duracion_texto': resultado['duracion_texto']
                }
            else:
                return {
                    'status': 'error',
                    'message': resultado['error']
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Error inesperado: {str(e)}"
            }
    
    def save(self, *args, **kwargs):
        """Override del método save para validaciones y cálculos automáticos"""
        # Validar que la fecha de llegada sea posterior a la salida
        if self.fecha_llegada and self.fecha_llegada < self.fecha_salida:
            raise ValueError("La fecha de llegada no puede ser anterior a la fecha de salida")
        
        # Validar que el kilometraje de llegada sea mayor al de salida
        if self.kilometraje_llegada and self.kilometraje_llegada < self.kilometraje_salida:
            raise ValueError("El kilometraje de llegada no puede ser menor al de salida")
        
        # Marcar como completado si tiene fecha de llegada
        if self.fecha_llegada and not self.completado:
            self.completado = True
        
        # Actualizar kilometraje de la unidad al completar el viaje
        if self.completado and self.kilometraje_llegada:
            if self.kilometraje_llegada > self.unidad.kilometraje_actual:
                self.unidad.kilometraje_actual = self.kilometraje_llegada
                self.unidad.save(update_fields=['kilometraje_actual'])
        
        super().save(*args, **kwargs)