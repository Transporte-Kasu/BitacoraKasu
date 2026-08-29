import itertools
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from modulos.bitacoras.models import BitacoraViaje, Cliente
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad
from modulos.vacios.models import CambioOperadorVacio, RetrasoVacio, Vacio
from modulos.reportes.models import ConfiguracionReporte
from modulos.reportes.generadores.vacios import (
    generar_entregas_por_operador,
    generar_retrasos,
)


_contador_bitacora = itertools.count(1)


def _bitacora():
    ahora = timezone.now()
    n = next(_contador_bitacora)
    return BitacoraViaje.objects.create(
        cliente=Cliente.objects.create(nombre='ACME'),
        operador=Operador.objects.create(nombre=f'Base {n}', tipo='LOCAL'),
        unidad=Unidad.objects.create(
            numero_economico=f'ECO-B{n}', placa=f'P-B{n}', tipo='LOCAL', año=2020,
            capacidad_combustible=Decimal('200'), rendimiento_esperado=Decimal('3'),
        ),
        modalidad='SENCILLO', contenedor='C', fecha_carga=ahora, fecha_salida=ahora,
        destino='x',
    )


class EntregasPorOperadorTests(TestCase):
    def test_cuenta_entregas_por_operador_y_semana(self):
        op = Operador.objects.create(nombre='Pedro', tipo='LOCAL')
        entrega = timezone.now() - timedelta(days=2)
        for i in range(3):
            Vacio.objects.create(
                bitacora_viaje=_bitacora(), contenedor=f'C{i}',
                fecha_entrega_cliente=entrega - timedelta(days=10),
                estado='ENTREGADO_NAVIERA', operador=op,
                fecha_entrega_naviera=entrega,
            )
        desde = (timezone.now() - timedelta(days=7)).date()
        hasta = timezone.now().date()
        datos = generar_entregas_por_operador(desde, hasta)
        self.assertEqual(datos['tipo'], 'VACIOS_ENTREGAS_SEMANAL')
        self.assertEqual(datos['resumen']['total_entregados'], 3)
        self.assertEqual(datos['resumen']['operador_top'], 'Pedro')

    def test_incluye_cambios_de_operador_por_causa(self):
        v = Vacio.objects.create(
            bitacora_viaje=_bitacora(), contenedor='C',
            fecha_entrega_cliente=timezone.now(), estado='ASIGNADO',
        )
        CambioOperadorVacio.objects.create(vacio=v, causa='NO_CONFIRMA')
        CambioOperadorVacio.objects.create(vacio=v, causa='NO_CONFIRMA')
        CambioOperadorVacio.objects.create(vacio=v, causa='SE_NIEGA')
        desde = (timezone.now() - timedelta(days=7)).date()
        hasta = timezone.now().date()
        datos = generar_entregas_por_operador(desde, hasta)
        self.assertEqual(datos['resumen']['cambios_operador_total'], 3)
        tabla = datos['tablas']['Cambios de operador por causa']
        por_causa = {f['causa']: f['cantidad'] for f in tabla}
        self.assertEqual(por_causa['Operador no confirma'], 2)

    def test_snapshot_pendientes(self):
        Vacio.objects.create(
            bitacora_viaje=_bitacora(), contenedor='P',
            fecha_entrega_cliente=timezone.now() - timedelta(days=5),
            estado='POR_VACIAR',
        )
        desde = (timezone.now() - timedelta(days=7)).date()
        hasta = timezone.now().date()
        datos = generar_entregas_por_operador(desde, hasta)
        self.assertEqual(datos['resumen']['vacios_pendientes'], 1)
        self.assertEqual(datos['resumen']['vacios_pendientes_mostrados'], 1)
        self.assertEqual(len(datos['tablas']['Aún sin entregar']), 1)


class RetrasosReporteTests(TestCase):
    def test_cuenta_retrasos_por_tipo(self):
        v = Vacio.objects.create(
            bitacora_viaje=_bitacora(), contenedor='C',
            fecha_entrega_cliente=timezone.now(),
        )
        RetrasoVacio.objects.create(vacio=v, tipo='MANIOBRA', motivo='x', fecha_estimada_nueva=date(2026, 9, 1), notificado_agencia=True)
        RetrasoVacio.objects.create(vacio=v, tipo='RETORNO', motivo='y', fecha_estimada_nueva=date(2026, 9, 2))
        desde = (timezone.now() - timedelta(days=7)).date()
        hasta = timezone.now().date()
        datos = generar_retrasos(desde, hasta)
        self.assertEqual(datos['tipo'], 'VACIOS_RETRASOS')
        self.assertEqual(datos['resumen']['total_retrasos'], 2)
        self.assertEqual(datos['resumen']['retrasos_maniobra'], 1)
        self.assertEqual(datos['resumen']['pct_notificados'], 50.0)


class VistaEntregasVaciosTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client.force_login(User.objects.create_user('t', password='x'))

    def test_vista_200_default(self):
        resp = self.client.get(reverse('reportes:entregas_vacios_por_operador'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Entregas de vacíos')

    def test_vista_200_con_rango(self):
        resp = self.client.get(
            reverse('reportes:entregas_vacios_por_operador'),
            {'desde': '2026-08-01', 'hasta': '2026-08-28'},
        )
        self.assertEqual(resp.status_code, 200)


class RegistroReportesTests(TestCase):
    def test_choices_incluyen_vacios(self):
        modulos = dict(ConfiguracionReporte.MODULO_CHOICES)
        tipos = dict(ConfiguracionReporte.TIPO_CHOICES)
        self.assertIn('VACIOS', modulos)
        self.assertIn('VACIOS_ENTREGAS_SEMANAL', tipos)
        self.assertIn('VACIOS_RETRASOS', tipos)

    def test_comando_conoce_los_generadores(self):
        from modulos.reportes.management.commands.generar_reportes import GENERADORES
        self.assertIn('VACIOS_ENTREGAS_SEMANAL', GENERADORES)
        self.assertIn('VACIOS_RETRASOS', GENERADORES)
