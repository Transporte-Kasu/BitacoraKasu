from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
import os


class Cliente(models.Model):
    """Cliente que recibe notificaciones de programación de contenedores."""
    nombre = models.CharField(max_length=120, verbose_name="Nombre")
    email = models.EmailField(blank=True, verbose_name="Correo electrónico")
    celular = models.CharField(
        max_length=20,
        blank=True,
        help_text="Con código de país, ej. +5217531234567",
        verbose_name="Celular (WhatsApp)",
    )
    activo = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class BitacoraViaje(models.Model):
    """
    Modelo para registrar cada viaje realizado
    Ubicación: apps/bitacoras/models.py
    """
    MODALIDAD_CHOICES = [
        ('SENCILLO', 'Sencillo'),
        ('FULL', 'Full'),
        ('LOCAL', 'Local'),
        ('LOCAL_FULL', 'Local Full'),
    ]
    
    TIPO_CONTENEDOR_CHOICES = [('20', '20 pies'), ('40', '40 pies')]

    # Relaciones con otras aplicaciones
    cliente = models.ForeignKey(
        'Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bitacoras',
        verbose_name="Cliente",
    )
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
    salida_a_ruta = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Salida a ruta"
    )
    contenedor = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Contenedor 1"
    )
    peso = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Peso 1 (toneladas)"
    )
    contenedor_2 = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Contenedor 2"
    )
    peso_2 = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Peso 2 (toneladas)"
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
    
    # Combustible y kilometraje (gestionados desde módulo combustible)
    diesel_cargado = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Diesel cargado (litros)"
    )
    kilometraje_salida = models.IntegerField(
        null=True,
        blank=True,
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
        verbose_name="Dirección de entrega"
    )
    domicilio_carta_porte = models.TextField(
        blank=True,
        verbose_name="Domicilio carta porte"
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
    cp_destino_2 = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="CP destino 2 (reparto)"
    )
    distancia_calculada_2 = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distancia al segundo destino (reparto) en km según Google Maps",
        verbose_name="Distancia calculada destino 2 (km)"
    )
    duracion_estimada_2 = models.IntegerField(
        null=True,
        blank=True,
        help_text="Duración estimada al segundo destino en minutos",
        verbose_name="Duración estimada destino 2 (min)"
    )

    # Seguridad
    sellos = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Sellos contenedor 1"
    )
    sellos_2 = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Sellos contenedor 2"
    )
    tipo_contenedor = models.CharField(
        max_length=2,
        choices=[('20', '20 pies'), ('40', '40 pies')],
        default='40',
        verbose_name="Tipo de contenedor",
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
        if self.diesel_cargado and self.diesel_cargado > 0 and self.kilometros_recorridos > 0:
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
    def distancia_efectiva(self):
        """Retorna la mayor distancia calculada (para rendimiento con reparto)"""
        if self.distancia_calculada_2 and self.distancia_calculada:
            return max(self.distancia_calculada, self.distancia_calculada_2)
        return self.distancia_calculada

    @property
    def diferencia_distancias(self):
        """
        Compara distancia real vs calculada por Google Maps
        Retorna diferencia en kilómetros
        """
        dist_efectiva = self.distancia_efectiva
        if dist_efectiva and self.kilometros_recorridos > 0:
            return round(self.kilometros_recorridos - float(dist_efectiva), 2)
        return None
    
    @property
    def alerta_bajo_rendimiento(self):
        """Verifica si el rendimiento está por debajo del umbral (2.5 km/lt)"""
        return self.rendimiento_combustible > 0 and self.rendimiento_combustible < 2.5
    
    # ========================================================================
    # VALIDACIONES
    # ========================================================================

    def clean(self):
        from django.core.exceptions import ValidationError
        modalidad = self.modalidad

        if modalidad in ('FULL', 'LOCAL_FULL') and not self.contenedor_2:
            raise ValidationError({'contenedor_2': 'Full y Local Full requieren el segundo contenedor.'})

        if modalidad in ('SENCILLO', 'LOCAL'):
            if self.contenedor_2 or self.peso_2 or self.sellos_2:
                raise ValidationError('SENCILLO y LOCAL no pueden tener datos del segundo contenedor.')
            if self.reparto:
                raise ValidationError({'reparto': 'SENCILLO y LOCAL no usan reparto.'})

        if modalidad == 'LOCAL_FULL' and self.reparto:
            raise ValidationError({'reparto': 'Local Full no usa reparto.'})

    # ========================================================================
    # MÉTODOS
    # ========================================================================

    def calcular_distancia_google(self, api_key=None):
        """
        Calcula distancia y duración usando Google Distance Matrix API.
        Si hay reparto y cp_destino_2, también calcula la segunda distancia.
        Retorna: dict con 'distancia_km', 'duracion_min', 'status' (y _2 si aplica)
        """
        from config.services.google_maps import GoogleMapsService

        if not api_key:
            api_key = os.environ.get('GOOGLE_MAPS_API_KEY')

        if not api_key:
            return {'status': 'error', 'message': 'No se encontró API key de Google Maps'}

        if not self.cp_destino:
            return {'status': 'error', 'message': 'No hay código postal de destino'}

        try:
            maps_service = GoogleMapsService(api_key)
            resultado = maps_service.calcular_distancia(self.cp_origen, self.cp_destino)

            if resultado['success']:
                self.distancia_calculada = Decimal(str(round(resultado['distancia_km'], 2)))
                self.duracion_estimada = int(resultado['duracion_min'])
                update_fields = ['distancia_calculada', 'duracion_estimada']

                return_data = {
                    'status': 'success',
                    'distancia_km': resultado['distancia_km'],
                    'duracion_min': resultado['duracion_min'],
                    'distancia_texto': resultado['distancia_texto'],
                    'duracion_texto': resultado['duracion_texto'],
                }

                # Segundo destino (reparto con CP diferente)
                if self.reparto and self.cp_destino_2:
                    resultado_2 = maps_service.calcular_distancia(self.cp_origen, self.cp_destino_2)
                    if resultado_2['success']:
                        self.distancia_calculada_2 = Decimal(str(round(resultado_2['distancia_km'], 2)))
                        self.duracion_estimada_2 = int(resultado_2['duracion_min'])
                        update_fields.extend(['distancia_calculada_2', 'duracion_estimada_2'])
                        return_data['distancia_km_2'] = resultado_2['distancia_km']
                        return_data['duracion_min_2'] = resultado_2['duracion_min']
                        return_data['distancia_texto_2'] = resultado_2['distancia_texto']
                        return_data['duracion_texto_2'] = resultado_2['duracion_texto']

                self.save(update_fields=update_fields)
                return return_data
            else:
                return {'status': 'error', 'message': resultado['error']}

        except Exception as e:
            return {'status': 'error', 'message': f"Error inesperado: {str(e)}"}
    
    def save(self, *args, **kwargs):
        """Override del método save para validaciones y cálculos automáticos"""
        # Validar que la fecha de llegada sea posterior a la salida
        if self.fecha_llegada and self.fecha_llegada < self.fecha_salida:
            raise ValueError("La fecha de llegada no puede ser anterior a la fecha de salida")
        
        # Validar que el kilometraje de llegada sea mayor al de salida
        if self.kilometraje_llegada and self.kilometraje_salida:
            if self.kilometraje_llegada < self.kilometraje_salida:
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