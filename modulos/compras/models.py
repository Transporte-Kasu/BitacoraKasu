from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Proveedor(models.Model):
    """Modelo para proveedores"""
    nombre = models.CharField(max_length=200)
    rfc = models.CharField(max_length=13, unique=True)
    direccion = models.TextField()
    telefono = models.CharField(max_length=15)
    email = models.EmailField()
    contacto = models.CharField(max_length=200, help_text="Nombre del contacto principal")
    activo = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} - {self.rfc}"


class Producto(models.Model):
    """Catálogo de productos"""
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField()
    unidad_medida = models.CharField(max_length=50, help_text="Ej: Pieza, Litro, Kg, Caja")
    categoria = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['categoria', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.unidad_medida})"


class Requisicion(models.Model):
    """Requisiciones de compra"""
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de Aprobación'),
        ('APROBADA', 'Aprobada'),
        ('RECHAZADA', 'Rechazada'),
        ('EN_COMPRA', 'En Proceso de Compra'),
        ('COMPLETADA', 'Completada'),
        ('CANCELADA', 'Cancelada'),
    ]

    solicitante = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requisiciones')
    folio = models.CharField(max_length=20, unique=True, editable=False)
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_requerida = models.DateField(help_text="Fecha en que se necesitan los productos")
    justificacion = models.TextField(help_text="Motivo de la requisición")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')

    # Aprobación
    aprobada_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requisiciones_aprobadas'
    )
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    comentarios_aprobacion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Requisición"
        verbose_name_plural = "Requisiciones"
        ordering = ['-fecha_solicitud']
        permissions = [
            ("aprobar_requisicion", "Puede aprobar requisiciones"),
            ("procesar_compra", "Puede procesar compras"),
            ("gestionar_almacen", "Puede gestionar almacén"),
        ]

    def save(self, *args, **kwargs):
        if not self.folio:
            # Generar folio automático: REQ-YYYYMMDD-XXX
            from django.db.models import Max
            fecha = timezone.now().strftime('%Y%m%d')
            ultimo = Requisicion.objects.filter(folio__startswith=f'REQ-{fecha}').aggregate(
                Max('folio')
            )['folio__max']

            if ultimo:
                numero = int(ultimo.split('-')[-1]) + 1
            else:
                numero = 1

            self.folio = f'REQ-{fecha}-{numero:03d}'

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.folio} - {self.solicitante.get_full_name()}"

    @property
    def total_items(self):
        return self.items.count()

    def aprobar(self, usuario, comentarios=''):
        """Aprobar la requisición"""
        self.estado = 'APROBADA'
        self.aprobada_por = usuario
        self.fecha_aprobacion = timezone.now()
        self.comentarios_aprobacion = comentarios
        self.save()

    def rechazar(self, usuario, comentarios):
        """Rechazar la requisición"""
        self.estado = 'RECHAZADA'
        self.aprobada_por = usuario
        self.fecha_aprobacion = timezone.now()
        self.comentarios_aprobacion = comentarios
        self.save()


class ItemRequisicion(models.Model):
    """Items individuales de una requisición"""
    requisicion = models.ForeignKey(Requisicion, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion_adicional = models.TextField(blank=True, help_text="Especificaciones adicionales")

    class Meta:
        verbose_name = "Item de Requisición"
        verbose_name_plural = "Items de Requisición"

    def __str__(self):
        return f"{self.producto.nombre} - {self.cantidad} {self.producto.unidad_medida}"


class OrdenCompra(models.Model):
    """Órdenes de compra"""
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de Envío'),
        ('ENVIADA', 'Enviada al Proveedor'),
        ('CONFIRMADA', 'Confirmada por Proveedor'),
        ('EN_TRANSITO', 'En Tránsito'),
        ('RECIBIDA', 'Recibida en Almacén'),
        ('CANCELADA', 'Cancelada'),
    ]

    requisicion = models.ForeignKey(Requisicion, on_delete=models.CASCADE, related_name='ordenes_compra')
    folio = models.CharField(max_length=20, unique=True, editable=False)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_estimada_entrega = models.DateField()

    creada_por = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ordenes_creadas')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')

    # Datos de factura
    factura_numero = models.CharField(max_length=50, blank=True)
    factura_fecha = models.DateField(null=True, blank=True)
    factura_monto = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    factura_archivo = models.FileField(upload_to='facturas/', null=True, blank=True)

    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = "Orden de Compra"
        verbose_name_plural = "Órdenes de Compra"
        ordering = ['-fecha_creacion']

    def save(self, *args, **kwargs):
        if not self.folio:
            # Generar folio automático: OC-YYYYMMDD-XXX
            from django.db.models import Max
            fecha = timezone.now().strftime('%Y%m%d')
            ultimo = OrdenCompra.objects.filter(folio__startswith=f'OC-{fecha}').aggregate(
                Max('folio')
            )['folio__max']

            if ultimo:
                numero = int(ultimo.split('-')[-1]) + 1
            else:
                numero = 1

            self.folio = f'OC-{fecha}-{numero:03d}'

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.folio} - {self.proveedor.nombre}"

    @property
    def total_items(self):
        return self.items.count()


class ItemOrdenCompra(models.Model):
    """Items de la orden de compra"""
    orden = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name='items')
    item_requisicion = models.ForeignKey(ItemRequisicion, on_delete=models.CASCADE)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Item de Orden de Compra"
        verbose_name_plural = "Items de Orden de Compra"

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def __str__(self):
        return f"{self.item_requisicion.producto.nombre} - {self.cantidad}"


class RecepcionAlmacen(models.Model):
    """Registro de recepción en almacén"""
    ESTADO_CHOICES = [
        ('RECIBIDO', 'Recibido'),
        ('ALMACENADO', 'Almacenado'),
        ('DISTRIBUIDO', 'Distribuido'),
    ]

    orden_compra = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name='recepciones')
    fecha_recepcion = models.DateTimeField(auto_now_add=True)
    recibido_por = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recepciones')

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='RECIBIDO')
    ubicacion_almacen = models.CharField(max_length=100, help_text="Ubicación física en almacén")
    observaciones = models.TextField(blank=True)

    # Documentos
    remision = models.CharField(max_length=50, blank=True, help_text="Número de remisión")
    foto_recepcion = models.ImageField(upload_to='recepciones/', null=True, blank=True)

    class Meta:
        verbose_name = "Recepción de Almacén"
        verbose_name_plural = "Recepciones de Almacén"
        ordering = ['-fecha_recepcion']

    def __str__(self):
        return f"Recepción {self.orden_compra.folio} - {self.fecha_recepcion.strftime('%d/%m/%Y')}"


class ItemRecepcion(models.Model):
    """Items recibidos en almacén"""
    recepcion = models.ForeignKey(RecepcionAlmacen, on_delete=models.CASCADE, related_name='items')
    item_orden = models.ForeignKey(ItemOrdenCompra, on_delete=models.CASCADE)
    cantidad_recibida = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad_aceptada = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad_rechazada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    motivo_rechazo = models.TextField(blank=True)

    class Meta:
        verbose_name = "Item de Recepción"
        verbose_name_plural = "Items de Recepción"

    def __str__(self):
        return f"{self.item_orden.item_requisicion.producto.nombre} - Recibido: {self.cantidad_recibida}"


class Inventario(models.Model):
    """Control de inventario"""
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='inventario')
    cantidad_disponible = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ubicacion = models.CharField(max_length=100)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Inventario"
        verbose_name_plural = "Inventario"
        unique_together = ['producto', 'ubicacion']

    def __str__(self):
        return f"{self.producto.nombre} - {self.cantidad_disponible} {self.producto.unidad_medida}"

    def agregar_stock(self, cantidad):
        """Agregar cantidad al inventario"""
        self.cantidad_disponible += cantidad
        self.save()

    def reducir_stock(self, cantidad):
        """Reducir cantidad del inventario"""
        if self.cantidad_disponible >= cantidad:
            self.cantidad_disponible -= cantidad
            self.save()
            return True
        return False