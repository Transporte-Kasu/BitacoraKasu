from django.db import models
from django.utils.text import slugify


class Dolly(models.Model):
    numero_economico = models.CharField(
        max_length=30, unique=True, verbose_name='Número económico'
    )
    slug = models.SlugField(max_length=50, unique=True, blank=True)
    marca = models.CharField(max_length=60, blank=True, verbose_name='Marca')
    color = models.CharField(max_length=30, blank=True, verbose_name='Color')
    numero_serie = models.CharField(
        max_length=60, unique=True, verbose_name='No. de serie'
    )
    activo = models.BooleanField(default=True, verbose_name='Activo')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Dolly'
        verbose_name_plural = 'Dollys'
        ordering = ['numero_economico']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['activo']),
            models.Index(fields=['marca']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.numero_economico) or f"dolly-{self.numero_economico.lower()}"
            slug = base
            counter = 1
            qs = Dolly.objects.filter(slug=slug)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            while qs.exists():
                slug = f"{base}-{counter}"
                counter += 1
                qs = Dolly.objects.filter(slug=slug).exclude(pk=self.pk or 0)
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero_economico} — {self.marca}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('dollys:detail', kwargs={'slug': self.slug})
