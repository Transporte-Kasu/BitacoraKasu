from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class ConfiguracionReporte(models.Model):
    """Define qué reporte generar, con qué frecuencia y a quién enviarlo."""

    MODULO_CHOICES = [
        ('ALMACEN', 'Almacén'),
        ('COMBUSTIBLE', 'Combustible'),
        ('TALLER', 'Taller'),
    ]

    TIPO_CHOICES = [
        # Almacén
        ('ALMACEN_INVENTARIO',   'Almacén — Inventario general'),
        ('ALMACEN_STOCK_CRITICO','Almacén — Stock crítico'),
        ('ALMACEN_CADUCIDAD',    'Almacén — Próximos a caducar'),
        ('ALMACEN_MOVIMIENTOS',  'Almacén — Movimientos del período'),
        # Combustible
        ('COMBUSTIBLE_CARGAS',   'Combustible — Cargas del período'),
        ('COMBUSTIBLE_CONSUMO',  'Combustible — Consumo por unidad'),
        ('COMBUSTIBLE_ALERTAS',  'Combustible — Alertas de candado'),
    ]

    FRECUENCIA_CHOICES = [
        ('DIARIO',   'Diario'),
        ('SEMANAL',  'Semanal'),
        ('MENSUAL',  'Mensual'),
    ]

    DIA_SEMANA_CHOICES = [
        (0, 'Lunes'), (1, 'Martes'), (2, 'Miércoles'),
        (3, 'Jueves'), (4, 'Viernes'), (5, 'Sábado'), (6, 'Domingo'),
    ]

    nombre = models.CharField(max_length=200, verbose_name='Nombre del reporte')
    modulo = models.CharField(max_length=20, choices=MODULO_CHOICES, verbose_name='Módulo')
    tipo_reporte = models.CharField(max_length=40, choices=TIPO_CHOICES, verbose_name='Tipo de reporte')
    frecuencia = models.CharField(max_length=10, choices=FRECUENCIA_CHOICES, verbose_name='Frecuencia')

    # Para reporte semanal: qué día de la semana
    dia_semana = models.IntegerField(
        null=True, blank=True,
        choices=DIA_SEMANA_CHOICES,
        verbose_name='Día de la semana',
        help_text='Solo para frecuencia semanal'
    )
    # Para reporte mensual: qué día del mes
    dia_mes = models.IntegerField(
        null=True, blank=True,
        verbose_name='Día del mes',
        help_text='Solo para frecuencia mensual (1-28)'
    )

    destinatarios = models.TextField(
        verbose_name='Destinatarios',
        help_text='Emails separados por coma. Ej: juan@empresa.com, maria@empresa.com'
    )

    activo = models.BooleanField(default=True, verbose_name='Activo')
    adjuntar_excel = models.BooleanField(
        default=False,
        verbose_name='Adjuntar Excel',
        help_text='Adjunta un archivo Excel con el detalle completo del período al correo'
    )
    ultimo_envio = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Último envío',
        editable=False
    )

    creado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='reportes_configurados',
        verbose_name='Creado por'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Configuración de Reporte'
        verbose_name_plural = 'Configuraciones de Reportes'
        ordering = ['modulo', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.get_frecuencia_display()})"

    def get_destinatarios_list(self):
        """Devuelve la lista de emails como lista Python."""
        return [e.strip() for e in self.destinatarios.split(',') if e.strip()]

    def es_debido(self):
        """Determina si este reporte debe ejecutarse ahora según su frecuencia."""
        ahora = timezone.now()

        if not self.ultimo_envio:
            return True  # Nunca se ha ejecutado

        delta = ahora - self.ultimo_envio

        if self.frecuencia == 'DIARIO':
            return delta.days >= 1

        if self.frecuencia == 'SEMANAL':
            if delta.days < 7:
                return False
            # Verificar día de la semana si está configurado
            if self.dia_semana is not None:
                return ahora.weekday() == self.dia_semana
            return True

        if self.frecuencia == 'MENSUAL':
            if delta.days < 28:
                return False
            # Verificar día del mes si está configurado
            if self.dia_mes is not None:
                return ahora.day == self.dia_mes
            return True

        return False


class ReporteGenerado(models.Model):
    """Registro histórico de cada reporte generado y enviado."""

    ESTADO_CHOICES = [
        ('GENERADO', 'Generado y enviado'),
        ('ERROR',    'Error al generar'),
        ('PARCIAL',  'Enviado con errores parciales'),
    ]

    configuracion = models.ForeignKey(
        ConfiguracionReporte,
        on_delete=models.CASCADE,
        related_name='reportes_generados',
        verbose_name='Configuración'
    )
    fecha_generacion = models.DateTimeField(auto_now_add=True)
    periodo_inicio = models.DateField(verbose_name='Período inicio')
    periodo_fin = models.DateField(verbose_name='Período fin')

    estado = models.CharField(
        max_length=10, choices=ESTADO_CHOICES, default='GENERADO'
    )
    destinatarios_enviados = models.TextField(
        blank=True,
        verbose_name='Enviado a',
        help_text='Emails que recibieron el reporte'
    )
    resumen = models.JSONField(
        default=dict,
        verbose_name='Resumen de datos',
        help_text='Snapshot de los datos clave del reporte'
    )
    mensaje_error = models.TextField(blank=True, verbose_name='Error')

    class Meta:
        verbose_name = 'Reporte Generado'
        verbose_name_plural = 'Reportes Generados'
        ordering = ['-fecha_generacion']
        indexes = [
            models.Index(fields=['configuracion', '-fecha_generacion']),
            models.Index(fields=['-fecha_generacion']),
        ]

    def __str__(self):
        return (
            f"{self.configuracion.nombre} — "
            f"{self.fecha_generacion.strftime('%d/%m/%Y %H:%M')}"
        )
