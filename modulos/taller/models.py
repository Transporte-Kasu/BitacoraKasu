from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from modulos.unidades.models import Unidad
from modulos.operadores.models import Operador
from modulos.compras.models import Requisicion, ItemRequisicion, Producto


class TipoMantenimiento(models.Model):
    """Catálogo de tipos de mantenimiento"""
    TIPO_CHOICES = [
        ('PREVENTIVO', 'Preventivo'),
        ('CORRECTIVO', 'Correctivo'),
        ('PREDICTIVO', 'Predictivo'),
    ]

    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    descripcion = models.TextField()
    kilometraje_sugerido = models.IntegerField(
        null=True,
        blank=True,
        help_text="Kilometraje sugerido para este mantenimiento"
    )
    dias_sugeridos = models.IntegerField(
        null=True,
        blank=True,
        help_text="Días sugeridos entre mantenimientos"
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tipo de Mantenimiento"
        verbose_name_plural = "Tipos de Mantenimiento"
        ordering = ['tipo', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


class CategoriaFalla(models.Model):
    """Categorías de fallas/problemas"""
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    prioridad_default = models.CharField(
        max_length=10,
        choices=[('BAJA', 'Baja'), ('MEDIA', 'Media'), ('ALTA', 'Alta'), ('CRITICA', 'Crítica')],
        default='MEDIA'
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Categoría de Falla"
        verbose_name_plural = "Categorías de Fallas"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class OrdenTrabajo(models.Model):
    """Órdenes de trabajo del taller"""
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_DIAGNOSTICO', 'En Diagnóstico'),
        ('ESPERANDO_PIEZAS', 'Esperando Piezas'),
        ('EN_REPARACION', 'En Reparación'),
        ('EN_PRUEBAS', 'En Pruebas'),
        ('COMPLETADA', 'Completada'),
        ('CANCELADA', 'Cancelada'),
    ]

    PRIORIDAD_CHOICES = [
        ('BAJA', 'Baja'),
        ('MEDIA', 'Media'),
        ('ALTA', 'Alta'),
        ('CRITICA', 'Crítica'),
    ]

    # Información básica
    folio = models.CharField(max_length=20, unique=True, editable=False)
    unidad = models.ForeignKey(Unidad, on_delete=models.CASCADE, related_name='ordenes_trabajo')
    operador_reporta = models.ForeignKey(
        Operador,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordenes_reportadas'
    )

    # Tipo de mantenimiento
    tipo_mantenimiento = models.ForeignKey(
        TipoMantenimiento,
        on_delete=models.SET_NULL,
        null=True,
        related_name='ordenes'
    )
    categoria_falla = models.ForeignKey(
        CategoriaFalla,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordenes'
    )

    # Descripción del problema
    descripcion_problema = models.TextField(help_text="Descripción del problema o servicio requerido")
    sintomas = models.TextField(blank=True, help_text="Síntomas observados")

    # Prioridad y fechas
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD_CHOICES, default='MEDIA')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_programada = models.DateField(null=True, blank=True)
    fecha_inicio_real = models.DateTimeField(null=True, blank=True)
    fecha_finalizacion = models.DateTimeField(null=True, blank=True)

    # Kilometraje al momento del reporte
    kilometraje_ingreso = models.IntegerField(
        help_text="Kilometraje al ingresar al taller"
    )
    kilometraje_salida = models.IntegerField(
        null=True,
        blank=True,
        help_text="Kilometraje al salir del taller"
    )

    # Asignación
    mecanico_asignado = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordenes_asignadas',
        limit_choices_to={'groups__name': 'Mecánicos'}
    )
    supervisor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordenes_supervisadas'
    )

    # Estado y seguimiento
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')

    # Diagnóstico
    diagnostico = models.TextField(blank=True, help_text="Diagnóstico técnico del problema")
    fecha_diagnostico = models.DateTimeField(null=True, blank=True)

    # Trabajo realizado
    trabajo_realizado = models.TextField(blank=True, help_text="Descripción del trabajo realizado")

    # Costos (estimados y reales)
    costo_estimado_mano_obra = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Costo estimado de mano de obra"
    )
    costo_real_mano_obra = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Costo real de mano de obra"
    )

    # Observaciones
    observaciones = models.TextField(blank=True)

    # Creación
    creada_por = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ordenes_taller_creadas'
    )

    class Meta:
        verbose_name = "Orden de Trabajo"
        verbose_name_plural = "Órdenes de Trabajo"
        ordering = ['-fecha_creacion']
        permissions = [
            ("diagnosticar_orden", "Puede realizar diagnóstico"),
            ("asignar_mecanico", "Puede asignar mecánicos"),
            ("aprobar_orden", "Puede aprobar órdenes"),
            ("cerrar_orden", "Puede cerrar órdenes"),
        ]

    def save(self, *args, **kwargs):
        if not self.folio:
            # Generar folio automático: OT-YYYYMMDD-XXX
            from django.db.models import Max
            fecha = timezone.now().strftime('%Y%m%d')
            ultimo = OrdenTrabajo.objects.filter(folio__startswith=f'OT-{fecha}').aggregate(
                Max('folio')
            )['folio__max']

            if ultimo:
                numero = int(ultimo.split('-')[-1]) + 1
            else:
                numero = 1

            self.folio = f'OT-{fecha}-{numero:03d}'

        # Si se completa, actualizar fechas de mantenimiento de la unidad
        if self.estado == 'COMPLETADA' and self.pk:
            old_obj = OrdenTrabajo.objects.filter(pk=self.pk).first()
            if old_obj and old_obj.estado != 'COMPLETADA':
                self.unidad.ultimo_mantenimiento = timezone.now().date()

                # Calcular próximo mantenimiento si aplica
                if self.tipo_mantenimiento and self.tipo_mantenimiento.dias_sugeridos:
                    from datetime import timedelta
                    self.unidad.proximo_mantenimiento = (
                        timezone.now().date() + timedelta(days=self.tipo_mantenimiento.dias_sugeridos)
                    )

                # Actualizar kilometraje de la unidad si hay kilometraje de salida
                if self.kilometraje_salida:
                    self.unidad.kilometraje_actual = self.kilometraje_salida

                self.unidad.save()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.folio} - {self.unidad.numero_economico} - {self.get_estado_display()}"

    @property
    def costo_total_piezas_estimado(self):
        """Calcula el costo total estimado de piezas"""
        return sum(
            item.cantidad * item.costo_estimado
            for item in self.piezas_requeridas.all()
        )

    @property
    def costo_total_piezas_real(self):
        """Calcula el costo total real de piezas"""
        return sum(
            item.cantidad * (item.costo_real or 0)
            for item in self.piezas_requeridas.all()
        )

    @property
    def costo_total_estimado(self):
        """Costo total estimado (mano de obra + piezas)"""
        return self.costo_estimado_mano_obra + self.costo_total_piezas_estimado

    @property
    def costo_total_real(self):
        """Costo total real (mano de obra + piezas)"""
        return self.costo_real_mano_obra + self.costo_total_piezas_real

    @property
    def dias_en_taller(self):
        """Calcula los días que lleva la unidad en taller"""
        if self.fecha_inicio_real:
            fin = self.fecha_finalizacion or timezone.now()
            return (fin - self.fecha_inicio_real).days
        return 0

    @property
    def horas_en_taller(self):
        """Calcula las horas que lleva la unidad en taller"""
        if self.fecha_inicio_real:
            fin = self.fecha_finalizacion or timezone.now()
            return round((fin - self.fecha_inicio_real).total_seconds() / 3600, 1)
        return 0

    @property
    def requiere_piezas(self):
        """Verifica si la orden tiene piezas pendientes"""
        return self.piezas_requeridas.filter(estado='PENDIENTE').exists()

    @property
    def kilometros_recorridos_en_taller(self):
        """Calcula los kilómetros recorridos durante el servicio (pruebas)"""
        if self.kilometraje_salida and self.kilometraje_ingreso:
            return self.kilometraje_salida - self.kilometraje_ingreso
        return 0

    def iniciar_diagnostico(self):
        """Cambia el estado a diagnóstico"""
        self.estado = 'EN_DIAGNOSTICO'
        if not self.fecha_inicio_real:
            self.fecha_inicio_real = timezone.now()
        self.save()

    def completar_diagnostico(self, diagnostico, usuario):
        """Completa el diagnóstico"""
        self.diagnostico = diagnostico
        self.fecha_diagnostico = timezone.now()
        # Si hay piezas requeridas, cambiar a esperando piezas
        if self.piezas_requeridas.exists():
            self.estado = 'ESPERANDO_PIEZAS'
        else:
            self.estado = 'EN_REPARACION'
        self.save()

    def iniciar_reparacion(self):
        """Inicia la reparación"""
        self.estado = 'EN_REPARACION'
        self.save()

    def completar(self, trabajo_realizado, costo_real_mano_obra, kilometraje_salida=None):
        """Completa la orden de trabajo"""
        self.trabajo_realizado = trabajo_realizado
        self.costo_real_mano_obra = costo_real_mano_obra
        if kilometraje_salida:
            self.kilometraje_salida = kilometraje_salida
        self.estado = 'COMPLETADA'
        self.fecha_finalizacion = timezone.now()
        self.save()

    def cancelar(self, motivo):
        """Cancela la orden de trabajo"""
        self.estado = 'CANCELADA'
        self.observaciones += f"\n\nCANCELADA: {motivo}"
        self.fecha_finalizacion = timezone.now()
        self.save()


class PiezaRequerida(models.Model):
    """Piezas requeridas para una orden de trabajo"""
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de Solicitar'),
        ('SOLICITADA', 'Solicitada en Requisición'),
        ('EN_COMPRA', 'En Proceso de Compra'),
        ('RECIBIDA', 'Recibida en Almacén'),
        ('INSTALADA', 'Instalada'),
        ('CANCELADA', 'Cancelada'),
    ]

    orden_trabajo = models.ForeignKey(
        OrdenTrabajo,
        on_delete=models.CASCADE,
        related_name='piezas_requeridas'
    )
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion_uso = models.TextField(
        blank=True,
        help_text="Descripción de dónde/cómo se usará la pieza"
    )

    # Estado
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')

    # Costos
    costo_estimado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Costo unitario estimado"
    )
    costo_real = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Costo unitario real"
    )

    # Relación con requisición
    item_requisicion = models.ForeignKey(
        ItemRequisicion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='piezas_orden_trabajo'
    )

    # Fechas
    fecha_solicitud = models.DateTimeField(null=True, blank=True)
    fecha_recepcion = models.DateTimeField(null=True, blank=True)
    fecha_instalacion = models.DateTimeField(null=True, blank=True)

    # Tracking
    agregada_por = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='piezas_taller_agregadas'
    )
    fecha_agregada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pieza Requerida"
        verbose_name_plural = "Piezas Requeridas"
        ordering = ['estado', 'fecha_agregada']

    def __str__(self):
        return f"{self.producto.nombre} - {self.cantidad} ({self.get_estado_display()})"

    @property
    def subtotal_estimado(self):
        return self.cantidad * self.costo_estimado

    @property
    def subtotal_real(self):
        if self.costo_real:
            return self.cantidad * self.costo_real
        return 0

    def marcar_como_solicitada(self, item_requisicion):
        """Marca la pieza como solicitada y la vincula a un item de requisición"""
        self.estado = 'SOLICITADA'
        self.item_requisicion = item_requisicion
        self.fecha_solicitud = timezone.now()
        self.save()

    def marcar_como_recibida(self, costo_real=None):
        """Marca la pieza como recibida"""
        self.estado = 'RECIBIDA'
        self.fecha_recepcion = timezone.now()
        if costo_real:
            self.costo_real = costo_real
        self.save()

    def marcar_como_instalada(self):
        """Marca la pieza como instalada"""
        self.estado = 'INSTALADA'
        self.fecha_instalacion = timezone.now()
        self.save()


class SeguimientoOrden(models.Model):
    """Bitácora de seguimiento de la orden de trabajo"""
    orden_trabajo = models.ForeignKey(
        OrdenTrabajo,
        on_delete=models.CASCADE,
        related_name='seguimientos'
    )
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    estado_anterior = models.CharField(max_length=20)
    estado_nuevo = models.CharField(max_length=20)
    comentario = models.TextField(blank=True)

    # Archivos adjuntos (fotos, documentos)
    archivo = models.FileField(upload_to='taller/seguimientos/', null=True, blank=True)

    class Meta:
        verbose_name = "Seguimiento de Orden"
        verbose_name_plural = "Seguimientos de Órdenes"
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.orden_trabajo.folio} - {self.fecha.strftime('%d/%m/%Y %H:%M')}"


class ChecklistMantenimiento(models.Model):
    """Checklist de items a revisar/realizar en mantenimiento"""
    tipo_mantenimiento = models.ForeignKey(
        TipoMantenimiento,
        on_delete=models.CASCADE,
        related_name='checklist_items'
    )
    descripcion = models.CharField(max_length=300)
    orden = models.IntegerField(default=0, help_text="Orden de aparición")
    es_obligatorio = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Item de Checklist"
        verbose_name_plural = "Items de Checklist"
        ordering = ['tipo_mantenimiento', 'orden', 'descripcion']

    def __str__(self):
        return f"{self.tipo_mantenimiento.nombre} - {self.descripcion}"


class ChecklistOrden(models.Model):
    """Items de checklist completados en una orden"""
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('OK', 'OK'),
        ('REQUIERE_ATENCION', 'Requiere Atención'),
        ('REPARADO', 'Reparado'),
        ('NO_APLICA', 'No Aplica'),
    ]

    orden_trabajo = models.ForeignKey(
        OrdenTrabajo,
        on_delete=models.CASCADE,
        related_name='checklist'
    )
    item_checklist = models.ForeignKey(
        ChecklistMantenimiento,
        on_delete=models.CASCADE
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    observaciones = models.TextField(blank=True)
    fecha_revision = models.DateTimeField(null=True, blank=True)
    revisado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Checklist de Orden"
        verbose_name_plural = "Checklists de Órdenes"
        unique_together = ['orden_trabajo', 'item_checklist']

    def __str__(self):
        return f"{self.orden_trabajo.folio} - {self.item_checklist.descripcion}"


class HistorialMantenimiento(models.Model):
    """Historial resumido de mantenimientos por unidad"""
    unidad = models.ForeignKey(
        Unidad,
        on_delete=models.CASCADE,
        related_name='historial_mantenimiento'
    )
    orden_trabajo = models.OneToOneField(
        OrdenTrabajo,
        on_delete=models.CASCADE,
        related_name='historial'
    )
    fecha_servicio = models.DateField()
    kilometraje_ingreso = models.IntegerField()
    kilometraje_salida = models.IntegerField(null=True, blank=True)
    tipo_servicio = models.CharField(max_length=200)
    descripcion_breve = models.TextField()
    costo_total = models.DecimalField(max_digits=10, decimal_places=2)
    tiempo_fuera_servicio_dias = models.IntegerField(default=0)
    tiempo_fuera_servicio_horas = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=0,
        help_text="Horas totales en taller"
    )

    class Meta:
        verbose_name = "Historial de Mantenimiento"
        verbose_name_plural = "Historiales de Mantenimiento"
        ordering = ['-fecha_servicio']
        indexes = [
            models.Index(fields=['unidad', '-fecha_servicio']),
            models.Index(fields=['unidad', '-kilometraje_ingreso']),
        ]

    def __str__(self):
        return f"{self.unidad.numero_economico} - {self.fecha_servicio} - {self.tipo_servicio}"

    @property
    def kilometros_en_taller(self):
        """Kilómetros recorridos durante el servicio"""
        if self.kilometraje_salida and self.kilometraje_ingreso:
            return self.kilometraje_salida - self.kilometraje_ingreso
        return 0