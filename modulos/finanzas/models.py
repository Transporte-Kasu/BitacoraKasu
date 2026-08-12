from decimal import Decimal

from django.db import models


class TarifaKilometro(models.Model):
    """Tarifa única global (histórica) que se cobra por kilómetro recorrido."""

    valor = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor por km")
    vigente_desde = models.DateField(verbose_name="Vigente desde")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Tarifa por Kilómetro"
        verbose_name_plural = "Tarifas por Kilómetro"
        ordering = ['-vigente_desde']

    def __str__(self):
        return f"${self.valor}/km desde {self.vigente_desde}"

    @classmethod
    def vigente_en(cls, fecha):
        return (
            cls.objects
            .filter(vigente_desde__lte=fecha, activo=True)
            .order_by('-vigente_desde')
            .first()
        )


class RecepcionPipa(models.Model):
    """Registro de cada pipa real que rellena el tanque de diésel de la empresa."""

    fecha = models.DateField(verbose_name="Fecha de recepción")
    litros = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Litros recibidos")
    costo_total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Costo total pagado")
    proveedor = models.CharField(max_length=200, blank=True, verbose_name="Proveedor")
    factura = models.FileField(
        upload_to='combustible/pipas/%Y/%m/',
        null=True,
        blank=True,
        verbose_name="Factura/ticket",
    )
    notas = models.TextField(blank=True, verbose_name="Notas")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Recepción de Pipa"
        verbose_name_plural = "Recepciones de Pipa"
        ordering = ['-fecha']

    def __str__(self):
        return f"Pipa {self.fecha} - {self.litros} L - ${self.costo_total}"

    @property
    def precio_litro(self):
        if not self.litros:
            return None
        return self.costo_total / self.litros


class PrecioDieselMensual(models.Model):
    """Histórico mensual del precio de diésel, derivado de RecepcionPipa."""

    anio = models.PositiveIntegerField(verbose_name="Año")
    mes = models.PositiveSmallIntegerField(verbose_name="Mes")
    litros_totales = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Litros totales")
    costo_total = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Costo total")
    precio_promedio_litro = models.DecimalField(
        max_digits=10, decimal_places=4, verbose_name="Precio promedio por litro"
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Precio de Diésel Mensual"
        verbose_name_plural = "Precios de Diésel Mensuales"
        unique_together = ('anio', 'mes')
        ordering = ['-anio', '-mes']

    def __str__(self):
        return f"{self.mes:02d}/{self.anio}: ${self.precio_promedio_litro}/L"

    @classmethod
    def vigente_en(cls, fecha):
        return (
            cls.objects
            .filter(
                models.Q(anio__lt=fecha.year) |
                models.Q(anio=fecha.year, mes__lte=fecha.month)
            )
            .order_by('-anio', '-mes')
            .first()
        )

    @classmethod
    def recalcular(cls, anio, mes):
        """Recalcula (o borra) el renglón mensual a partir de las RecepcionPipa de ese mes."""
        agregados = RecepcionPipa.objects.filter(fecha__year=anio, fecha__month=mes).aggregate(
            litros_totales=models.Sum('litros'),
            costo_total=models.Sum('costo_total'),
        )
        litros_totales = agregados['litros_totales']
        costo_total = agregados['costo_total']

        if not litros_totales:
            cls.objects.filter(anio=anio, mes=mes).delete()
            return

        precio_promedio = (costo_total / litros_totales).quantize(Decimal('0.0001'))
        cls.objects.update_or_create(
            anio=anio,
            mes=mes,
            defaults={
                'litros_totales': litros_totales,
                'costo_total': costo_total,
                'precio_promedio_litro': precio_promedio,
            },
        )
