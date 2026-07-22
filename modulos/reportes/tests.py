from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from modulos.reportes.models import ConfiguracionReporte
from modulos.reportes.generadores.flota import generar_vigencias_flota
from modulos.equipos.models import Equipo
from modulos.dollys.models import Dolly
from modulos.caja_seca.models import CajaSeca
from modulos.almacen.models import (
    ProductoAlmacen, AsignacionDirectaAlmacen, AsignacionSalida,
    ItemAsignacionSalida, EntradaAlmacen, AuditoriaAlmacen,
)
from modulos.unidades.models import Unidad
from modulos.reportes.generadores.almacen import generar_analisis_integral


class EsDebidoMensualTests(TestCase):
    def _config(self, dia_mes, ultimo_envio):
        return ConfiguracionReporte(
            nombre='Test', modulo='FLOTA', tipo_reporte='FLOTA_VIGENCIAS',
            frecuencia='MENSUAL', dia_mes=dia_mes,
            destinatarios='a@b.com', ultimo_envio=ultimo_envio,
        )

    def test_no_dispara_antes_del_dia_configurado(self):
        hoy = timezone.now()
        mes_pasado = (hoy.replace(day=1) - timedelta(days=1)).replace(day=1)
        config = self._config(dia_mes=15, ultimo_envio=mes_pasado)
        if hoy.day < 15:
            self.assertFalse(config.es_debido())

    def test_dispara_en_o_despues_del_dia_configurado(self):
        hoy = timezone.now()
        if hoy.day < 15:
            self.skipTest('Solo verificable a partir del día 15 del mes actual')
        mes_pasado = (hoy.replace(day=1) - timedelta(days=1)).replace(day=1)
        config = self._config(dia_mes=15, ultimo_envio=mes_pasado)
        self.assertTrue(config.es_debido())

    def test_no_dispara_en_el_mismo_mes_del_ultimo_envio(self):
        hoy = timezone.now()
        config = self._config(dia_mes=1, ultimo_envio=hoy)
        self.assertFalse(config.es_debido())

    def test_sin_dia_mes_se_comporta_como_dia_1(self):
        hoy = timezone.now()
        mes_pasado = (hoy.replace(day=1) - timedelta(days=1)).replace(day=1)
        config = self._config(dia_mes=None, ultimo_envio=mes_pasado)
        self.assertTrue(config.es_debido())


class GenerarVigenciasFlotaTests(TestCase):
    def setUp(self):
        hoy = timezone.now().date()
        Equipo.objects.create(
            numero_economico='CHASIS-VENCIDO', numero_serie='S1',
            vigencia_doble_articulado=hoy - timedelta(days=5),
        )
        Equipo.objects.create(
            numero_economico='CHASIS-POR-VENCER', numero_serie='S2',
            vigencia_doble_articulado=hoy + timedelta(days=10),
        )
        Equipo.objects.create(
            numero_economico='CHASIS-VIGENTE', numero_serie='S3',
            vigencia_doble_articulado=hoy + timedelta(days=200),
        )
        Equipo.objects.create(
            numero_economico='CHASIS-SIN-DATO', numero_serie='S4',
        )
        Equipo.objects.create(
            numero_economico='CHASIS-INACTIVO', numero_serie='S5', activo=False,
            vigencia_doble_articulado=hoy - timedelta(days=100),
        )
        Dolly.objects.create(numero_economico='DOLLY-1', numero_serie='D1')
        CajaSeca.objects.create(numero_economico='CAJA-1', numero_serie='C1')

    def test_resumen_clasifica_equipos_correctamente(self):
        datos = generar_vigencias_flota(timezone.now().date(), timezone.now().date())
        resumen = datos['resumen']
        self.assertEqual(resumen['total_equipos'], 4)  # excluye el inactivo
        self.assertEqual(resumen['equipos_vencidos'], 1)
        self.assertEqual(resumen['equipos_por_vencer_30d'], 1)
        self.assertEqual(resumen['equipos_sin_dato'], 1)
        self.assertEqual(resumen['total_dollys'], 1)
        self.assertEqual(resumen['total_cajas_secas'], 1)

    def test_filas_incluye_los_tres_tipos_de_equipo(self):
        datos = generar_vigencias_flota(timezone.now().date(), timezone.now().date())
        tipos = {f['tipo_equipo'] for f in datos['filas']}
        self.assertEqual(tipos, {'Equipo', 'Dolly', 'Caja Seca'})

    def test_vencidos_aparecen_antes_que_vigentes(self):
        datos = generar_vigencias_flota(timezone.now().date(), timezone.now().date())
        estados = [f['estado_vigencia'] for f in datos['filas'] if f['tipo_equipo'] == 'Equipo']
        self.assertEqual(estados[0], 'VENCIDO')


class GenerarAnalisisIntegralAlmacenTests(TestCase):
    def setUp(self):
        self.hoy = timezone.now().date()

        self.mecanico1 = User.objects.create_user(
            username='mecanico1', first_name='Juan', last_name='Perez', password='12345'
        )
        self.mecanico2 = User.objects.create_user(
            username='mecanico2', first_name='Ana', last_name='Lopez', password='12345'
        )

        self.unidad = Unidad.objects.create(
            numero_economico='U-100', placa='ABC123', tipo='LOCAL', año=2020,
            capacidad_combustible=Decimal('200.00'), rendimiento_esperado=Decimal('3.50'),
        )

        self.producto = ProductoAlmacen.objects.create(
            categoria='Refacciones', sku='FOC-001', descripcion='Foco delantero',
            localidad='Pasillo A1', cantidad=Decimal('50.00'), unidad_medida='Pieza',
            stock_minimo=Decimal('5.00'), costo_unitario=Decimal('80.00'), activo=True,
        )

        AsignacionDirectaAlmacen.objects.create(
            producto=self.producto, unidad=self.unidad, cantidad=Decimal('2.00'),
            motivo='Cambio de foco', entregado_por=self.mecanico1,
            fecha_asignacion=timezone.now(),
        )

        asignacion_salida = AsignacionSalida.objects.create(
            solicitante='Juan Perez', tipo_destino='UNIDAD', unidad=self.unidad,
            justificacion='Reparación urgente', entregado_por=self.mecanico1,
        )
        ItemAsignacionSalida.objects.create(
            asignacion=asignacion_salida, producto=self.producto, cantidad=Decimal('3.00'),
        )

        EntradaAlmacen.objects.create(tipo='FACTURA', recibido_por=self.mecanico2)
        EntradaAlmacen.objects.create(tipo='ENTRADA_DIRECTA', recibido_por=self.mecanico2)

        for _ in range(6):
            AuditoriaAlmacen.objects.create(
                usuario=self.mecanico1, accion='ELIMINAR', modelo='ProductoAlmacen',
                objeto_id='1', objeto_str='Producto de prueba',
            )
        AuditoriaAlmacen.objects.create(
            usuario=self.mecanico2, accion='CREAR', modelo='EntradaAlmacen',
            objeto_id='1', objeto_str='Entrada de prueba',
        )

    def test_resumen_cuenta_asignaciones_y_entradas(self):
        datos = generar_analisis_integral(self.hoy, self.hoy)
        resumen = datos['resumen']
        self.assertEqual(resumen['total_asignaciones_directas'], 1)
        self.assertEqual(resumen['total_asignaciones_salida'], 1)
        self.assertEqual(resumen['total_items_asignados'], 5.0)
        self.assertEqual(resumen['total_entradas'], 2)
        self.assertEqual(resumen['entradas_por_tipo']['Producto Nuevo desde Factura'], 1)
        self.assertEqual(resumen['entradas_por_tipo']['Entrada Directa'], 1)

    def test_top_destinos_incluye_la_unidad(self):
        datos = generar_analisis_integral(self.hoy, self.hoy)
        destinos = {d['destino'] for d in datos['top_destinos']}
        self.assertIn(str(self.unidad), destinos)

    def test_auditoria_detecta_concentracion_y_eliminaciones(self):
        datos = generar_analisis_integral(self.hoy, self.hoy)
        resumen = datos['resumen']
        self.assertEqual(resumen['total_eventos_auditoria'], 7)
        self.assertEqual(resumen['auditoria_por_accion']['Eliminar'], 6)
        self.assertEqual(len(resumen['alertas_auditoria']), 2)
        self.assertIn('Juan Perez', resumen['alertas_auditoria'][0])
        self.assertIn('eliminaciones', resumen['alertas_auditoria'][1].lower())

    def test_tablas_para_excel_incluye_las_tres_secciones(self):
        datos = generar_analisis_integral(self.hoy, self.hoy)
        self.assertEqual(set(datos['tablas'].keys()), {'Asignaciones', 'Entradas', 'Auditoria'})
        self.assertEqual(len(datos['tablas']['Asignaciones']), 2)
