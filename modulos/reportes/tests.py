from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from modulos.reportes.models import ConfiguracionReporte
from modulos.reportes.generadores.flota import generar_vigencias_flota
from modulos.equipos.models import Equipo
from modulos.dollys.models import Dolly
from modulos.caja_seca.models import CajaSeca


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
