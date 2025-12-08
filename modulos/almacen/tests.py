from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from modulos.almacen.models import (
    ProductoAlmacen, EntradaAlmacen, ItemEntradaAlmacen,
    SolicitudSalida, ItemSolicitudSalida, SalidaAlmacen,
    AlertaStock, MovimientoAlmacen
)


class ProductoAlmacenModelTest(TestCase):
    """Tests para el modelo ProductoAlmacen"""
    
    def setUp(self):
        self.producto = ProductoAlmacen.objects.create(
            categoria='Refacciones',
            subcategoria='Motor',
            sku='TEST-001',
            descripcion='Filtro de aceite',
            localidad='Pasillo A1',
            cantidad=Decimal('10.00'),
            unidad_medida='Pieza',
            stock_minimo=Decimal('5.00'),
            stock_maximo=Decimal('50.00'),
            costo_unitario=Decimal('150.00'),
            activo=True
        )
    
    def test_producto_creation(self):
        """Verificar creación de producto"""
        self.assertEqual(self.producto.sku, 'TEST-001')
        self.assertEqual(self.producto.cantidad, Decimal('10.00'))
    
    def test_costo_total_property(self):
        """Verificar cálculo de costo total"""
        self.assertEqual(self.producto.costo_total, Decimal('1500.00'))
    
    def test_stock_bajo_property(self):
        """Verificar detección de stock bajo"""
        self.assertFalse(self.producto.stock_bajo)
        self.producto.cantidad = Decimal('4.00')
        self.assertTrue(self.producto.stock_bajo)
    
    def test_agregar_stock(self):
        """Verificar método agregar_stock"""
        cantidad_inicial = self.producto.cantidad
        self.producto.agregar_stock(5)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.cantidad, cantidad_inicial + Decimal('5.00'))
    
    def test_reducir_stock(self):
        """Verificar método reducir_stock"""
        resultado = self.producto.reducir_stock(5)
        self.assertTrue(resultado)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.cantidad, Decimal('5.00'))
        
        # Intentar reducir más de lo disponible
        resultado = self.producto.reducir_stock(10)
        self.assertFalse(resultado)


class EntradaAlmacenModelTest(TestCase):
    """Tests para el modelo EntradaAlmacen"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.entrada = EntradaAlmacen.objects.create(
            tipo='AJUSTE',
            recibido_por=self.user,
            observaciones='Entrada de prueba'
        )
    
    def test_entrada_creation(self):
        """Verificar creación de entrada"""
        self.assertIsNotNone(self.entrada.folio)
        self.assertTrue(self.entrada.folio.startswith('ENT-'))
    
    def test_folio_generation(self):
        """Verificar generación automática de folio"""
        entrada2 = EntradaAlmacen.objects.create(
            tipo='AJUSTE',
            recibido_por=self.user
        )
        self.assertNotEqual(self.entrada.folio, entrada2.folio)


class SolicitudSalidaModelTest(TestCase):
    """Tests para el modelo SolicitudSalida"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.solicitud = SolicitudSalida.objects.create(
            tipo='SOLICITUD_GENERAL',
            solicitante=self.user,
            justificacion='Solicitud de prueba'
        )
    
    def test_solicitud_creation(self):
        """Verificar creación de solicitud"""
        self.assertIsNotNone(self.solicitud.folio)
        self.assertTrue(self.solicitud.folio.startswith('SOL-'))
        self.assertEqual(self.solicitud.estado, 'PENDIENTE')
    
    def test_requiere_autorizacion(self):
        """Verificar que SOLICITUD_GENERAL requiere autorización"""
        self.assertTrue(self.solicitud.requiere_autorizacion)
    
    def test_autorizar_solicitud(self):
        """Verificar método autorizar"""
        usuario_autorizador = User.objects.create_user(username='autorizador', password='12345')
        self.solicitud.autorizar(usuario_autorizador, 'Aprobado')
        self.assertEqual(self.solicitud.estado, 'AUTORIZADA')
        self.assertEqual(self.solicitud.autorizado_por, usuario_autorizador)
        self.assertIsNotNone(self.solicitud.fecha_autorizacion)
    
    def test_rechazar_solicitud(self):
        """Verificar método rechazar"""
        usuario_autorizador = User.objects.create_user(username='autorizador', password='12345')
        self.solicitud.rechazar(usuario_autorizador, 'No aprobado')
        self.assertEqual(self.solicitud.estado, 'RECHAZADA')


class AlertaStockTest(TestCase):
    """Tests para alertas de stock"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.producto = ProductoAlmacen.objects.create(
            categoria='Test',
            sku='TEST-ALERTA',
            descripcion='Producto para alertas',
            localidad='Test',
            cantidad=Decimal('3.00'),
            unidad_medida='Pieza',
            stock_minimo=Decimal('5.00'),
            costo_unitario=Decimal('100.00'),
            activo=True
        )
    
    def test_alerta_stock_minimo_generada(self):
        """Verificar que se genera alerta de stock mínimo automáticamente"""
        # El signal debería haber generado una alerta
        alertas = AlertaStock.objects.filter(
            producto_almacen=self.producto,
            tipo_alerta='STOCK_MINIMO',
            resuelta=False
        )
        self.assertTrue(alertas.exists())
    
    def test_resolver_alerta(self):
        """Verificar método resolver de alerta"""
        alerta = AlertaStock.objects.filter(producto_almacen=self.producto).first()
        if alerta:
            alerta.resolver(self.user)
            self.assertTrue(alerta.resuelta)
            self.assertEqual(alerta.resuelta_por, self.user)
            self.assertIsNotNone(alerta.fecha_resolucion)
