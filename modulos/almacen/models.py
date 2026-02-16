from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal


class ProductoAlmacen(models.Model):
    """Catálogo de productos en almacén"""
    # Campos básicos
    categoria = models.CharField(max_length=100)
    subcategoria = models.CharField(max_length=100, blank=True)
    sku = models.CharField(max_length=50, unique=True, help_text="Código SKU único")
    codigo_barras = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text="Código de barras (opcional)"
    )
    descripcion = models.TextField()
    
    # Ubicación
    localidad = models.CharField(
        max_length=100,
        help_text="Ubicación física en almacén (ej: Pasillo A, Estante 3)"
    )
    
    # Control de stock
    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Cantidad actual en inventario"
    )
    unidad_medida = models.CharField(
        max_length=50,
        help_text="Ej: Pieza, Litro, Kg, Caja, Metro"
    )
    stock_minimo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Stock mínimo antes de generar alerta"
    )
    stock_maximo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Stock máximo recomendado"
    )
    
    # Costos
    costo_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Costo unitario del producto"
    )
    
    # Caducidad
    tiene_caducidad = models.BooleanField(
        default=False,
        help_text="Indica si el producto tiene fecha de caducidad"
    )
    fecha_caducidad = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha de caducidad (si aplica)"
    )
    
    # Imagen
    imagen = models.ImageField(
        upload_to='almacen/productos/',
        null=True,
        blank=True,
        help_text="Imagen del producto"
    )
    
    # Relación con módulo de compras
    producto_compra = models.ForeignKey(
        'compras.Producto',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='productos_almacen',
        help_text="Vínculo con catálogo de compras"
    )
    
    # Campos adicionales sugeridos
    proveedor_principal = models.ForeignKey(
        'compras.Proveedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='productos_almacen',
        help_text="Proveedor principal de este producto"
    )
    tiempo_reorden_dias = models.IntegerField(
        default=7,
        validators=[MinValueValidator(1)],
        help_text="Días estimados para reabastecimiento"
    )
    notas = models.TextField(blank=True)
    
    # Tipo de producto
    es_consumible = models.BooleanField(
        default=False,
        help_text="Indica si es un producto consumible de taller (trapos, gasolina blanca, desengrasante, etc.)"
    )

    # Metadata
    activo = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Producto de Almacén"
        verbose_name_plural = "Productos de Almacén"
        ordering = ['categoria', 'subcategoria', 'descripcion']
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['codigo_barras']),
            models.Index(fields=['categoria', 'subcategoria']),
            models.Index(fields=['cantidad']),
            models.Index(fields=['fecha_caducidad']),
            models.Index(fields=['activo']),
        ]
    
    def __str__(self):
        return f"{self.sku} - {self.descripcion}"
    
    @property
    def costo_total(self):
        """Calcula el costo total del inventario actual"""
        return self.cantidad * self.costo_unitario
    
    @property
    def stock_bajo(self):
        """Indica si el stock está por debajo del mínimo"""
        return self.cantidad <= self.stock_minimo
    
    @property
    def stock_agotado(self):
        """Indica si no hay stock"""
        return self.cantidad == 0
    
    @property
    def stock_excedido(self):
        """Indica si el stock excede el máximo"""
        if self.stock_maximo > 0:
            return self.cantidad > self.stock_maximo
        return False
    
    @property
    def proximo_caducar(self):
        """Indica si está próximo a caducar (30 días)"""
        if self.tiene_caducidad and self.fecha_caducidad:
            from datetime import timedelta
            dias_restantes = (self.fecha_caducidad - timezone.now().date()).days
            return 0 <= dias_restantes <= 30
        return False
    
    @property
    def caducado(self):
        """Indica si ya caducó"""
        if self.tiene_caducidad and self.fecha_caducidad:
            return self.fecha_caducidad < timezone.now().date()
        return False
    
    def agregar_stock(self, cantidad):
        """Agregar cantidad al inventario"""
        self.cantidad += Decimal(str(cantidad))
        self.save()
    
    def reducir_stock(self, cantidad):
        """Reducir cantidad del inventario"""
        cantidad_decimal = Decimal(str(cantidad))
        if self.cantidad >= cantidad_decimal:
            self.cantidad -= cantidad_decimal
            self.save()
            return True
        return False


class EntradaAlmacen(models.Model):
    """Registro de entradas al almacén"""
    TIPO_CHOICES = [
        ('FACTURA', 'Producto Nuevo desde Factura'),
        ('TALLER_REPARADO', 'Pieza Reparada del Taller'),
        ('TALLER_RECICLADO', 'Pieza/Material para Reciclar del Taller'),
        ('AJUSTE', 'Ajuste Manual de Inventario'),
    ]
    
    # Tipo y folio
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    folio = models.CharField(max_length=20, unique=True, editable=False)
    
    # Fechas
    fecha_entrada = models.DateTimeField(default=timezone.now)
    
    # Referencias
    orden_compra = models.ForeignKey(
        'compras.OrdenCompra',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='entradas_almacen'
    )
    orden_trabajo = models.ForeignKey(
        'taller.OrdenTrabajo',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='entradas_almacen'
    )
    recepcion_almacen_compras = models.ForeignKey(
        'compras.RecepcionAlmacen',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entradas_almacen_nuevo'
    )
    
    # Usuario
    recibido_por = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='entradas_recibidas'
    )
    
    # Datos de factura (para tipo FACTURA)
    factura_numero = models.CharField(max_length=50, blank=True)
    factura_archivo = models.FileField(
        upload_to='almacen/facturas/',
        null=True,
        blank=True
    )
    
    # Costos adicionales
    costo_envio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    costo_adicional = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    # Observaciones
    observaciones = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Entrada de Almacén"
        verbose_name_plural = "Entradas de Almacén"
        ordering = ['-fecha_entrada']
        indexes = [
            models.Index(fields=['tipo', '-fecha_entrada']),
            models.Index(fields=['folio']),
            models.Index(fields=['-fecha_entrada']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.folio:
            # Generar folio automático: ENT-YYYYMMDD-XXX
            from django.db.models import Max
            fecha = timezone.now().strftime('%Y%m%d')
            ultimo = EntradaAlmacen.objects.filter(
                folio__startswith=f'ENT-{fecha}'
            ).aggregate(Max('folio'))['folio__max']
            
            if ultimo:
                numero = int(ultimo.split('-')[-1]) + 1
            else:
                numero = 1
            
            self.folio = f'ENT-{fecha}-{numero:03d}'
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.folio} - {self.get_tipo_display()}"
    
    @property
    def total_items(self):
        """Total de items en esta entrada"""
        return self.items.count()
    
    @property
    def costo_total_productos(self):
        """Costo total de productos"""
        return sum(item.costo_total for item in self.items.all())
    
    @property
    def costo_total_entrada(self):
        """Costo total incluyendo envío y adicionales"""
        return self.costo_total_productos + self.costo_envio + self.costo_adicional


class ItemEntradaAlmacen(models.Model):
    """Detalle de productos en cada entrada"""
    entrada = models.ForeignKey(
        EntradaAlmacen,
        on_delete=models.CASCADE,
        related_name='items'
    )
    producto_almacen = models.ForeignKey(
        ProductoAlmacen,
        on_delete=models.CASCADE,
        related_name='entradas'
    )
    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    costo_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    
    # Trazabilidad
    lote = models.CharField(max_length=50, blank=True)
    fecha_caducidad = models.DateField(null=True, blank=True)
    ubicacion_asignada = models.CharField(max_length=100, blank=True)
    observaciones = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Item de Entrada"
        verbose_name_plural = "Items de Entrada"
        ordering = ['entrada', 'producto_almacen']
    
    def __str__(self):
        return f"{self.entrada.folio} - {self.producto_almacen.descripcion} ({self.cantidad})"
    
    @property
    def costo_total(self):
        """Calcula el costo total del item"""
        return self.cantidad * self.costo_unitario


class SolicitudSalida(models.Model):
    """Solicitudes de salida de productos"""
    TIPO_CHOICES = [
        ('ORDEN_TRABAJO', 'Para Orden de Trabajo del Taller'),
        ('SOLICITUD_GENERAL', 'Solicitud General'),
    ]
    
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de Autorización'),
        ('AUTORIZADA', 'Autorizada'),
        ('RECHAZADA', 'Rechazada'),
        ('ENTREGADA', 'Entregada'),
        ('CANCELADA', 'Cancelada'),
    ]
    
    # Tipo y folio
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    folio = models.CharField(max_length=20, unique=True, editable=False)
    
    # Referencias
    orden_trabajo = models.ForeignKey(
        'taller.OrdenTrabajo',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='solicitudes_almacen'
    )
    solicitante = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='solicitudes_almacen'
    )
    
    # Fechas
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    
    # Estado
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE'
    )
    
    # Justificación
    justificacion = models.TextField(help_text="Motivo de la solicitud")
    
    # Autorización
    requiere_autorizacion = models.BooleanField(default=True)
    autorizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salidas_autorizadas'
    )
    fecha_autorizacion = models.DateTimeField(null=True, blank=True)
    comentarios_autorizacion = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Solicitud de Salida"
        verbose_name_plural = "Solicitudes de Salida"
        ordering = ['-fecha_solicitud']
        indexes = [
            models.Index(fields=['estado', '-fecha_solicitud']),
            models.Index(fields=['folio']),
            models.Index(fields=['orden_trabajo']),
        ]
        permissions = [
            ("autorizar_salida_almacen", "Puede autorizar salidas de almacén"),
        ]
    
    def save(self, *args, **kwargs):
        if not self.folio:
            # Generar folio automático: SOL-YYYYMMDD-XXX
            from django.db.models import Max
            fecha = timezone.now().strftime('%Y%m%d')
            ultimo = SolicitudSalida.objects.filter(
                folio__startswith=f'SOL-{fecha}'
            ).aggregate(Max('folio'))['folio__max']
            
            if ultimo:
                numero = int(ultimo.split('-')[-1]) + 1
            else:
                numero = 1
            
            self.folio = f'SOL-{fecha}-{numero:03d}'
        
        # Determinar si requiere autorización
        if self.tipo == 'SOLICITUD_GENERAL':
            self.requiere_autorizacion = True
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.folio} - {self.solicitante.get_full_name()} - {self.get_estado_display()}"
    
    @property
    def total_items(self):
        """Total de items solicitados"""
        return self.items.count()
    
    def autorizar(self, usuario, comentarios=''):
        """Autorizar la solicitud"""
        self.estado = 'AUTORIZADA'
        self.autorizado_por = usuario
        self.fecha_autorizacion = timezone.now()
        self.comentarios_autorizacion = comentarios
        self.save()
    
    def rechazar(self, usuario, comentarios):
        """Rechazar la solicitud"""
        self.estado = 'RECHAZADA'
        self.autorizado_por = usuario
        self.fecha_autorizacion = timezone.now()
        self.comentarios_autorizacion = comentarios
        self.save()
    
    def cancelar(self, motivo):
        """Cancelar la solicitud"""
        self.estado = 'CANCELADA'
        self.comentarios_autorizacion += f"\n\nCANCELADA: {motivo}"
        self.save()


class ItemSolicitudSalida(models.Model):
    """Detalle de productos solicitados"""
    solicitud = models.ForeignKey(
        SolicitudSalida,
        on_delete=models.CASCADE,
        related_name='items'
    )
    producto_almacen = models.ForeignKey(
        ProductoAlmacen,
        on_delete=models.CASCADE,
        related_name='solicitudes_salida'
    )
    cantidad_solicitada = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    cantidad_entregada = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    observaciones = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Item de Solicitud de Salida"
        verbose_name_plural = "Items de Solicitud de Salida"
        ordering = ['solicitud', 'producto_almacen']
    
    def __str__(self):
        return f"{self.solicitud.folio} - {self.producto_almacen.descripcion} ({self.cantidad_solicitada})"
    
    @property
    def cantidad_pendiente(self):
        """Calcula la cantidad pendiente de entregar"""
        return self.cantidad_solicitada - self.cantidad_entregada
    
    @property
    def entrega_completa(self):
        """Indica si se entregó la cantidad completa"""
        return self.cantidad_entregada >= self.cantidad_solicitada


class SalidaAlmacen(models.Model):
    """Registro de salidas efectivas del almacén"""
    solicitud_salida = models.ForeignKey(
        SolicitudSalida,
        on_delete=models.CASCADE,
        related_name='salidas'
    )
    folio = models.CharField(max_length=20, unique=True, editable=False)
    fecha_salida = models.DateTimeField(default=timezone.now)
    
    # Usuarios
    entregado_a = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='salidas_recibidas'
    )
    entregado_por = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='salidas_entregadas'
    )
    
    observaciones = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Salida de Almacén"
        verbose_name_plural = "Salidas de Almacén"
        ordering = ['-fecha_salida']
        indexes = [
            models.Index(fields=['-fecha_salida']),
            models.Index(fields=['folio']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.folio:
            # Generar folio automático: SAL-YYYYMMDD-XXX
            from django.db.models import Max
            fecha = timezone.now().strftime('%Y%m%d')
            ultimo = SalidaAlmacen.objects.filter(
                folio__startswith=f'SAL-{fecha}'
            ).aggregate(Max('folio'))['folio__max']
            
            if ultimo:
                numero = int(ultimo.split('-')[-1]) + 1
            else:
                numero = 1
            
            self.folio = f'SAL-{fecha}-{numero:03d}'
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.folio} - {self.solicitud_salida.folio}"
    
    @property
    def total_items(self):
        """Total de items en esta salida"""
        return self.items.count()


class ItemSalidaAlmacen(models.Model):
    """Detalle de productos entregados"""
    salida = models.ForeignKey(
        SalidaAlmacen,
        on_delete=models.CASCADE,
        related_name='items'
    )
    item_solicitud = models.ForeignKey(
        ItemSolicitudSalida,
        on_delete=models.CASCADE,
        related_name='items_entregados'
    )
    producto_almacen = models.ForeignKey(
        ProductoAlmacen,
        on_delete=models.CASCADE,
        related_name='salidas'
    )
    cantidad_entregada = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    
    # Trazabilidad
    lote = models.CharField(max_length=50, blank=True)
    ubicacion_origen = models.CharField(max_length=100, blank=True)
    
    class Meta:
        verbose_name = "Item de Salida"
        verbose_name_plural = "Items de Salida"
        ordering = ['salida', 'producto_almacen']
    
    def __str__(self):
        return f"{self.salida.folio} - {self.producto_almacen.descripcion} ({self.cantidad_entregada})"


class MovimientoAlmacen(models.Model):
    """Historial completo de movimientos de inventario"""
    TIPO_CHOICES = [
        ('ENTRADA', 'Entrada'),
        ('SALIDA', 'Salida'),
        ('AJUSTE', 'Ajuste'),
        ('TRASLADO', 'Traslado'),
    ]
    
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    producto_almacen = models.ForeignKey(
        ProductoAlmacen,
        on_delete=models.CASCADE,
        related_name='movimientos'
    )
    
    # Cantidad (positivo para entrada, negativo para salida)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad_anterior = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad_posterior = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Referencias
    entrada_almacen = models.ForeignKey(
        EntradaAlmacen,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos'
    )
    salida_almacen = models.ForeignKey(
        SalidaAlmacen,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos'
    )
    
    # Metadata
    fecha_movimiento = models.DateTimeField(default=timezone.now)
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='movimientos_almacen'
    )
    observaciones = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Movimiento de Almacén"
        verbose_name_plural = "Movimientos de Almacén"
        ordering = ['-fecha_movimiento']
        indexes = [
            models.Index(fields=['producto_almacen', '-fecha_movimiento']),
            models.Index(fields=['tipo']),
            models.Index(fields=['-fecha_movimiento']),
        ]
    
    def __str__(self):
        return f"{self.get_tipo_display()} - {self.producto_almacen.sku} - {self.cantidad}"


class AlertaStock(models.Model):
    """Alertas automáticas de inventario"""
    TIPO_CHOICES = [
        ('STOCK_MINIMO', 'Stock Mínimo Alcanzado'),
        ('STOCK_AGOTADO', 'Stock Agotado'),
        ('PROXIMO_CADUCAR', 'Próximo a Caducar'),
        ('CADUCADO', 'Producto Caducado'),
    ]
    
    producto_almacen = models.ForeignKey(
        ProductoAlmacen,
        on_delete=models.CASCADE,
        related_name='alertas'
    )
    tipo_alerta = models.CharField(max_length=20, choices=TIPO_CHOICES)
    mensaje = models.TextField()
    
    fecha_generacion = models.DateTimeField(auto_now_add=True)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)
    
    resuelta = models.BooleanField(default=False)
    resuelta_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alertas_resueltas'
    )
    
    class Meta:
        verbose_name = "Alerta de Stock"
        verbose_name_plural = "Alertas de Stock"
        ordering = ['-fecha_generacion']
        indexes = [
            models.Index(fields=['producto_almacen', 'resuelta']),
            models.Index(fields=['tipo_alerta', '-fecha_generacion']),
        ]
    
    def __str__(self):
        return f"{self.get_tipo_alerta_display()} - {self.producto_almacen.sku}"
    
    def resolver(self, usuario):
        """Marcar la alerta como resuelta"""
        self.resuelta = True
        self.resuelta_por = usuario
        self.fecha_resolucion = timezone.now()
        self.save()


class SalidaRapidaConsumible(models.Model):
    """Salida rápida de productos consumibles sin flujo de autorización"""
    folio = models.CharField(max_length=20, unique=True, editable=False)
    producto = models.ForeignKey(
        ProductoAlmacen,
        on_delete=models.CASCADE,
        related_name='salidas_rapidas',
        limit_choices_to={'es_consumible': True, 'activo': True}
    )
    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    entregado_por = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='salidas_rapidas_entregadas'
    )
    solicitante = models.CharField(
        max_length=200,
        help_text="Nombre de quien solicita el consumible"
    )
    motivo = models.CharField(
        max_length=500,
        blank=True,
        help_text="Motivo o uso del consumible (opcional)"
    )
    fecha_salida = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Salida Rápida de Consumible"
        verbose_name_plural = "Salidas Rápidas de Consumibles"
        ordering = ['-fecha_salida']
        indexes = [
            models.Index(fields=['-fecha_salida']),
            models.Index(fields=['folio']),
            models.Index(fields=['producto']),
        ]

    def save(self, *args, **kwargs):
        if not self.folio:
            from django.db.models import Max
            fecha = timezone.now().strftime('%Y%m%d')
            ultimo = SalidaRapidaConsumible.objects.filter(
                folio__startswith=f'CON-{fecha}'
            ).aggregate(Max('folio'))['folio__max']

            if ultimo:
                numero = int(ultimo.split('-')[-1]) + 1
            else:
                numero = 1

            self.folio = f'CON-{fecha}-{numero:03d}'

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.folio} - {self.producto.descripcion} ({self.cantidad})"
