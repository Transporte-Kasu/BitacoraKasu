from django.db import models
from django.utils.text import slugify


class Equipo(models.Model):
    TIPO_CHOICES = [
        ('CHASIS', 'Chasis'),
        ('PLANA', 'Plana'),
        ('OTRO', 'Otro'),
    ]

    numero_economico = models.CharField(
        max_length=30, unique=True, verbose_name='Número económico'
    )
    tipo = models.CharField(
        max_length=10, choices=TIPO_CHOICES, default='CHASIS', verbose_name='Tipo'
    )
    slug = models.SlugField(max_length=50, unique=True, blank=True)
    placas = models.CharField(max_length=20, blank=True, verbose_name='Placas')
    marca = models.CharField(max_length=60, blank=True, verbose_name='Marca')
    modelo = models.CharField(max_length=60, blank=True, verbose_name='Modelo')
    color = models.CharField(max_length=30, blank=True, verbose_name='Color')
    numero_serie = models.CharField(
        max_length=60, unique=True, verbose_name='No. de serie'
    )
    vigencia_doble_articulado = models.DateField(
        null=True, blank=True, verbose_name='Vigencia doble articulado'
    )
    verificacion = models.BooleanField(default=True, verbose_name='Verificación')
    activo = models.BooleanField(default=True, verbose_name='Activo')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Equipo'
        verbose_name_plural = 'Equipos'
        ordering = ['numero_economico']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['tipo', 'activo']),
            models.Index(fields=['marca']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.numero_economico) or self.numero_economico.lower().replace(' ', '-')
            slug = base
            counter = 1
            qs = Equipo.objects.filter(slug=slug)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            while qs.exists():
                slug = f"{base}-{counter}"
                counter += 1
                qs = Equipo.objects.filter(slug=slug).exclude(pk=self.pk or 0)
            self.slug = slug
        # Extraer tipo del numero_economico si no está asignado
        if not self.tipo or self.tipo == 'OTRO':
            eco = self.numero_economico.upper()
            if eco.startswith('PLANA'):
                self.tipo = 'PLANA'
            elif eco.startswith('CHASIS'):
                self.tipo = 'CHASIS'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero_economico} — {self.marca}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('equipos:detail', kwargs={'slug': self.slug})
