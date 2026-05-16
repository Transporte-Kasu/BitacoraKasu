from django.db import models
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator


class CajaSeca(models.Model):
    numero_economico = models.CharField(
        max_length=30, unique=True, verbose_name='Número económico'
    )
    slug = models.SlugField(max_length=30, unique=True, blank=True)
    placas = models.CharField(max_length=20, blank=True, verbose_name='Placas')
    numero_serie = models.CharField(
        max_length=60, unique=True, verbose_name='No. de serie'
    )
    marca = models.CharField(max_length=60, blank=True, verbose_name='Marca')
    modelo = models.CharField(max_length=60, blank=True, verbose_name='Modelo')
    anio = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1990), MaxValueValidator(2040)],
        verbose_name='Año',
    )
    color = models.CharField(max_length=30, blank=True, verbose_name='Color')
    activo = models.BooleanField(default=True, verbose_name='Activo')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Caja Seca'
        verbose_name_plural = 'Cajas Secas'
        ordering = ['numero_economico']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['activo']),
            models.Index(fields=['marca']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.numero_economico) or self.numero_economico.lower().replace(' ', '-')
            slug = base
            counter = 1
            qs = CajaSeca.objects.filter(slug=slug)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            while qs.exists():
                slug = f"{base}-{counter}"
                counter += 1
                qs = CajaSeca.objects.filter(slug=slug).exclude(pk=self.pk or 0)
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero_economico} — {self.marca}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('caja_seca:detail', kwargs={'slug': self.slug})
