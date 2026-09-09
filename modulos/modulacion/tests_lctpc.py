import base64
from datetime import date, time
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Agencia, ImportacionProgramacionLCTPC, Modulacion, TerminalPortuaria,
)
from .services_graph import (
    CorreoLCTPC, GraphError, descargar_adjunto_xls, listar_correos, obtener_token,
)
from .services_importacion import ResumenImportacion, importar_programaciones_lctpc
from .services_lctpc import (
    ErrorParseoLCTPC, RenglonLCTPC, clasificar, parsear_programacion,
)

FIXTURES = Path(__file__).resolve().parent / 'tests_fixtures' / 'lctpc'
ASUNTO_07 = ('Programacion de contenedores a SPF, por horario preferente, '
             'para el 07 September 2026')


def _leer(nombre):
    return (FIXTURES / nombre).read_bytes()


class ImportacionProgramacionLCTPCModelTests(TestCase):
    def test_graph_message_id_es_unico(self):
        ImportacionProgramacionLCTPC.objects.create(
            graph_message_id='AAA-1', asunto='Programacion ... 07 September 2026',
            fecha_recibido='2026-09-05T14:02:00Z', estado='OK',
        )
        with self.assertRaises(IntegrityError):
            ImportacionProgramacionLCTPC.objects.create(
                graph_message_id='AAA-1', asunto='dup',
                fecha_recibido='2026-09-05T14:02:00Z', estado='OK',
            )

    def test_defaults_de_contadores_y_detalle(self):
        imp = ImportacionProgramacionLCTPC.objects.create(
            graph_message_id='AAA-2', asunto='x',
            fecha_recibido='2026-09-05T14:02:00Z', estado='ERROR',
            mensaje_error='sin adjunto',
        )
        self.assertEqual(imp.total_renglones, 0)
        self.assertEqual(imp.creadas, 0)
        self.assertEqual(imp.detalle, [])

    def test_modulacion_acepta_tipo_y_grupo_cita(self):
        m = Modulacion(contenedor='TEST1234567', tipo_cita='FULL', grupo_cita='abc123')
        # Solo comprobamos que los campos existen y aceptan el valor en memoria.
        self.assertEqual(m.tipo_cita, 'FULL')
        self.assertEqual(m.grupo_cita, 'abc123')


class ParsearProgramacionTests(SimpleTestCase):
    def test_extrae_las_10_filas_con_columnas_correctas(self):
        prog = parsear_programacion(_leer('3ZYM_202609051401.xls'), ASUNTO_07)
        self.assertEqual(len(prog.renglones), 10)
        r0 = prog.renglones[0]
        self.assertEqual(r0.contenedor, 'GXYU5129072')
        self.assertEqual(r0.transportista, '3ZYM')
        self.assertEqual(r0.folio_lctpc, '617210')
        self.assertEqual(r0.registro_inicio, time(1, 30))
        self.assertEqual(r0.registro_fin, time(3, 0))
        self.assertEqual(r0.cita_inicio, time(3, 0))
        self.assertEqual(r0.cita_fin, time(3, 59))

    def test_fecha_mes_en_ingles(self):
        prog = parsear_programacion(_leer('3ZYM_202609051401.xls'), ASUNTO_07)
        self.assertEqual(prog.fecha, date(2026, 9, 7))

    def test_fecha_mes_en_espanol(self):
        # 3ZYM_202609031849.xls: título "... para el 04 Septiembre 2026"
        asunto = 'Programacion de contenedores a SPF, para el 04 Septiembre 2026'
        prog = parsear_programacion(_leer('3ZYM_202609031849.xls'), asunto)
        self.assertEqual(prog.fecha, date(2026, 9, 4))
        self.assertEqual(prog.avisos, [])

    def test_decodifica_iso_8859_1_en_titulo(self):
        # No debe reventar por el carácter 'ó' de "Programación".
        prog = parsear_programacion(_leer('3ZYM_202609041650.xls'),
                                    'Programacion ... para el 05 September 2026')
        self.assertIsNotNone(prog.fecha)

    def test_fecha_asunto_distinta_a_titulo_usa_asunto_y_avisa(self):
        prog = parsear_programacion(
            _leer('3ZYM_202609051401.xls'),
            'Programacion de contenedores a SPF, para el 08 September 2026',
        )
        self.assertEqual(prog.fecha, date(2026, 9, 8))
        self.assertEqual(prog.fecha_titulo_excel, date(2026, 9, 7))
        self.assertTrue(prog.avisos)

    def test_sin_fecha_en_asunto_ni_titulo_levanta_error(self):
        contenido = b'<html><table><tr><th>OTRA</th></tr></table></html>'
        with self.assertRaises(ErrorParseoLCTPC):
            parsear_programacion(contenido, 'asunto sin fecha')

    def test_rango_horario_invalido_levanta_error(self):
        contenido = (
            '<table><thead><tr><th>CONTENEDOR</th><th>TRANSPORTISTA</th>'
            '<th>FOLIO</th><th>VENTANA DE REGISTRO</th><th>HORARIO DE CITA</th>'
            '</tr></thead><tr><td>ABCU1234567</td><td>3ZYM</td><td>1</td>'
            '<td>nope</td><td>03:00-03:59</td></tr></table>'
        ).encode('iso-8859-1')
        with self.assertRaises(ErrorParseoLCTPC):
            parsear_programacion(contenido, 'para el 07 September 2026')


def _renglon(contenedor, reg_ini):
    return RenglonLCTPC(
        contenedor=contenedor, transportista='3ZYM', folio_lctpc='0',
        registro_inicio=reg_ini, registro_fin=time(9, 0),
        cita_inicio=time(9, 0), cita_fin=time(9, 59),
    )


class ClasificarTests(SimpleTestCase):
    def test_seis_con_misma_hora_dan_tres_full(self):
        rs = [_renglon(f'C{i}', time(1, 30)) for i in range(6)]
        clasificar(rs)
        self.assertTrue(all(r.tipo_cita == 'FULL' for r in rs))
        self.assertEqual(rs[0].grupo_cita, rs[1].grupo_cita)
        self.assertEqual(rs[2].grupo_cita, rs[3].grupo_cita)
        self.assertEqual(rs[4].grupo_cita, rs[5].grupo_cita)
        self.assertEqual(len({rs[0].grupo_cita, rs[2].grupo_cita, rs[4].grupo_cita}), 3)

    def test_cinco_dan_dos_full_y_un_sencillo(self):
        rs = [_renglon(f'C{i}', time(1, 30)) for i in range(5)]
        clasificar(rs)
        self.assertEqual([r.tipo_cita for r in rs],
                         ['FULL', 'FULL', 'FULL', 'FULL', 'SENCILLO'])
        self.assertEqual(rs[4].grupo_cita, '')

    def test_uno_solo_es_sencillo(self):
        rs = [_renglon('C0', time(2, 30))]
        clasificar(rs)
        self.assertEqual(rs[0].tipo_cita, 'SENCILLO')
        self.assertEqual(rs[0].grupo_cita, '')

    def test_archivo_real_da_3_full_y_4_sencillo(self):
        prog = parsear_programacion(_leer('3ZYM_202609051401.xls'), ASUNTO_07)
        clasificar(prog.renglones)
        tipos = [r.tipo_cita for r in prog.renglones]
        self.assertEqual(tipos.count('FULL'), 6)
        self.assertEqual(tipos.count('SENCILLO'), 4)
        # 6 FULL == 3 pares con grupo distinto
        grupos_full = {r.grupo_cita for r in prog.renglones if r.tipo_cita == 'FULL'}
        self.assertEqual(len(grupos_full), 3)


GRAPH_CONF = dict(
    GRAPH_TENANT_ID='t', GRAPH_CLIENT_ID='c', GRAPH_CLIENT_SECRET='s',
    MODULACION_LCTPC_MAILBOX='calidad@transporteskasu.com.mx',
    MODULACION_LCTPC_REMITENTE='atencionspf@lctpc.com.mx',
)


def _resp(status=200, json_data=None, text=''):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data or {}
    r.text = text
    return r


@override_settings(**GRAPH_CONF)
class ServicesGraphTests(SimpleTestCase):
    def setUp(self):
        # limpiar el cache de token entre pruebas
        import modulos.modulacion.services_graph as g
        g._token_cache.update(valor=None, expira=0.0)

    @patch('modulos.modulacion.services_graph.requests.post')
    def test_obtener_token_devuelve_access_token(self, mock_post):
        mock_post.return_value = _resp(json_data={'access_token': 'ABC', 'expires_in': 3600})
        self.assertEqual(obtener_token(), 'ABC')

    @patch('modulos.modulacion.services_graph.requests.post')
    def test_obtener_token_http_error_levanta_grapherror(self, mock_post):
        mock_post.return_value = _resp(status=401, text='bad secret')
        with self.assertRaises(GraphError):
            obtener_token()

    @override_settings(GRAPH_TENANT_ID='', GRAPH_CLIENT_ID='', GRAPH_CLIENT_SECRET='')
    def test_sin_config_levanta_grapherror(self):
        with self.assertRaises(GraphError):
            obtener_token()

    @patch('modulos.modulacion.services_graph.obtener_token', return_value='TOK')
    @patch('modulos.modulacion.services_graph.requests.get')
    def test_listar_correos_parsea_value(self, mock_get, _tok):
        mock_get.return_value = _resp(json_data={'value': [
            {'id': 'm1', 'subject': 'Programacion ... 07 September 2026',
             'receivedDateTime': '2026-09-05T14:02:00Z'},
        ]})
        correos = listar_correos()
        self.assertEqual(len(correos), 1)
        self.assertIsInstance(correos[0], CorreoLCTPC)
        self.assertEqual(correos[0].id, 'm1')
        self.assertEqual(correos[0].recibido.year, 2026)

    @patch('modulos.modulacion.services_graph.obtener_token', return_value='TOK')
    @patch('modulos.modulacion.services_graph.requests.get')
    def test_descargar_adjunto_xls_decodifica_base64(self, mock_get, _tok):
        contenido = b'<table>hola</table>'
        mock_get.return_value = _resp(json_data={'value': [
            {'@odata.type': '#microsoft.graph.fileAttachment',
             'name': '3ZYM_202609051401.xls',
             'contentBytes': base64.b64encode(contenido).decode()},
        ]})
        self.assertEqual(descargar_adjunto_xls('m1'), contenido)

    @patch('modulos.modulacion.services_graph.obtener_token', return_value='TOK')
    @patch('modulos.modulacion.services_graph.requests.get')
    def test_descargar_sin_xls_levanta_grapherror(self, mock_get, _tok):
        mock_get.return_value = _resp(json_data={'value': [
            {'@odata.type': '#microsoft.graph.fileAttachment', 'name': 'firma.png',
             'contentBytes': 'AAAA'},
        ]})
        with self.assertRaises(GraphError):
            descargar_adjunto_xls('m1')


TERMINAL_LCTPC = 'L.C. Terminal Portuaria de Contenedores, S.A. de C.V.'


def _terminal():
    return TerminalPortuaria.objects.get_or_create(nombre=TERMINAL_LCTPC)[0]


def _modulacion(contenedor, estado='PENDIENTE', terminal=None):
    return Modulacion.objects.create(
        agencia=Agencia.objects.get_or_create(nombre='LOGINCO')[0],
        terminal_portuaria=terminal or _terminal(),
        tipo_contenedor='40HC', peso_toneladas=Decimal('18.5'),
        contenedor=contenedor, estado=estado,
    )


@override_settings(MODULACION_TERMINAL_LCTPC=TERMINAL_LCTPC)
class ImportarProgramacionesTests(TestCase):
    def setUp(self):
        self.xls = _leer('3ZYM_202609051401.xls')
        self.correo = CorreoLCTPC(id='m1', asunto=ASUNTO_07,
                                  recibido=timezone.now())

    def _patch_graph(self, correos=None, xls=None, list_error=None, dl_error=None):
        correos = [self.correo] if correos is None else correos
        p_list = patch('modulos.modulacion.services_importacion.listar_correos')
        p_dl = patch('modulos.modulacion.services_importacion.descargar_adjunto_xls')
        m_list = p_list.start()
        m_dl = p_dl.start()
        self.addCleanup(p_list.stop)
        self.addCleanup(p_dl.stop)
        m_list.side_effect = list_error
        if not list_error:
            m_list.return_value = correos
        if dl_error:
            m_dl.side_effect = dl_error
        else:
            m_dl.return_value = self.xls if xls is None else xls
        return m_list, m_dl

    def test_crea_stub_cuando_no_hay_modulacion(self):
        self._patch_graph()
        resumen = importar_programaciones_lctpc()
        self.assertEqual(resumen.creadas, 10)
        stub = Modulacion.objects.get(contenedor='GXYU5129072')
        self.assertEqual(stub.origen, 'LCTPC')
        self.assertEqual(stub.peso_toneladas, Decimal('0'))
        self.assertEqual(stub.tipo_contenedor, '')
        self.assertEqual(stub.agencia.nombre, 'POR DEFINIR')
        self.assertEqual(stub.fecha_modulacion_aduana, date(2026, 9, 7))
        self.assertIsNotNone(stub.hora_registro)
        self.assertIn('faltan agencia/cliente/tipo/peso', stub.observaciones)
        self.assertIn('Cita LCTPC 617210', stub.observaciones)

    def test_actualiza_modulacion_existente(self):
        m = _modulacion('GXYU5129072')
        self._patch_graph()
        resumen = importar_programaciones_lctpc()
        m.refresh_from_db()
        self.assertEqual(resumen.actualizadas, 1)
        self.assertEqual(resumen.creadas, 9)
        self.assertEqual(m.fecha_modulacion_aduana, date(2026, 9, 7))
        self.assertEqual(timezone.localtime(m.hora_registro).hour, 1)
        self.assertEqual(timezone.localtime(m.hora_registro).minute, 30)
        self.assertEqual(timezone.localtime(m.hora_ingreso).hour, 3)
        self.assertEqual(m.tipo_cita, 'FULL')
        self.assertTrue(m.grupo_cita)

    def test_hora_registro_es_aware_y_en_la_fecha_de_modulacion(self):
        _modulacion('GXYU5129072')
        self._patch_graph()
        importar_programaciones_lctpc()
        m = Modulacion.objects.get(contenedor='GXYU5129072')
        self.assertIsNotNone(timezone.is_aware(m.hora_registro))
        self.assertEqual(timezone.localtime(m.hora_registro).date(), date(2026, 9, 7))

    def test_correo_ya_procesado_se_salta(self):
        ImportacionProgramacionLCTPC.objects.create(
            graph_message_id='m1', asunto=ASUNTO_07,
            fecha_recibido=timezone.now(), estado='OK',
        )
        self._patch_graph()
        resumen = importar_programaciones_lctpc()
        self.assertEqual(resumen.correos_saltados, 1)
        self.assertEqual(resumen.creadas, 0)

    def test_no_duplica_linea_de_observacion_en_segundo_correo(self):
        m = _modulacion('GXYU5129072')
        self._patch_graph()
        importar_programaciones_lctpc()
        # segundo correo distinto (otro id) con el mismo contenido
        self.correo = CorreoLCTPC(id='m2', asunto=ASUNTO_07, recibido=timezone.now())
        self._patch_graph()
        importar_programaciones_lctpc()
        m.refresh_from_db()
        self.assertEqual(m.observaciones.count('Cita LCTPC 617210'), 1)

    def test_ignora_modulaciones_en_estado_cerrado(self):
        _modulacion('GXYU5129072', estado='ENVIADO_BITACORA')
        self._patch_graph()
        resumen = importar_programaciones_lctpc()
        # como la única candidata está cerrada, se crea stub
        self.assertEqual(resumen.creadas, 10)
        self.assertEqual(
            Modulacion.objects.filter(contenedor='GXYU5129072').count(), 2
        )

    def test_dos_candidatas_activas_marca_ambigua(self):
        _modulacion('GXYU5129072')
        _modulacion('GXYU5129072')
        self._patch_graph()
        resumen = importar_programaciones_lctpc()
        self.assertEqual(resumen.ambiguas, 1)
        imp = ImportacionProgramacionLCTPC.objects.get(graph_message_id='m1')
        self.assertEqual(imp.estado, 'OK_CON_AVISOS')
        resultados = {d['contenedor']: d['resultado'] for d in imp.detalle}
        self.assertEqual(resultados['GXYU5129072'], 'ACTUALIZADA_AMBIGUA')

    def test_correo_sin_adjunto_xls_registra_error_y_sigue(self):
        self._patch_graph(dl_error=GraphError('sin adjunto'))
        resumen = importar_programaciones_lctpc()
        self.assertEqual(resumen.correos_con_error, 1)
        imp = ImportacionProgramacionLCTPC.objects.get(graph_message_id='m1')
        self.assertEqual(imp.estado, 'ERROR')
        self.assertIn('sin adjunto', imp.mensaje_error)

    def test_grapherror_al_listar_no_revienta(self):
        self._patch_graph(list_error=GraphError('token muerto'))
        resumen = importar_programaciones_lctpc()
        self.assertEqual(resumen.correos_procesados, 0)
        self.assertEqual(ImportacionProgramacionLCTPC.objects.count(), 0)

    def test_estado_ok_con_avisos_por_fecha_discrepante(self):
        self.correo = CorreoLCTPC(
            id='m1',
            asunto='Programacion de contenedores a SPF, para el 08 September 2026',
            recibido=timezone.now(),
        )
        self._patch_graph()
        importar_programaciones_lctpc()
        imp = ImportacionProgramacionLCTPC.objects.get(graph_message_id='m1')
        self.assertEqual(imp.estado, 'OK_CON_AVISOS')
        self.assertEqual(imp.fecha_modulacion_aduana, date(2026, 9, 8))


class ImportarCommandTests(TestCase):
    @patch('modulos.modulacion.management.commands.importar_programacion_lctpc.importar_programaciones_lctpc')
    def test_command_llama_orquestador_e_imprime_resumen(self, mock_orq):
        mock_orq.return_value = ResumenImportacion(
            correos_procesados=1, creadas=3, actualizadas=7,
        )
        out = StringIO()
        call_command('importar_programacion_lctpc', stdout=out)
        mock_orq.assert_called_once()
        salida = out.getvalue()
        self.assertIn('3', salida)
        self.assertIn('7', salida)

    def test_command_esta_en_skip_commands_del_scheduler(self):
        from modulos.reportes.apps import _SKIP_COMMANDS
        self.assertIn('importar_programacion_lctpc', _SKIP_COMMANDS)


class SchedulerJobLCTPCTests(SimpleTestCase):
    @patch('config.scheduler.BackgroundScheduler')
    def test_iniciar_scheduler_registra_job_lctpc(self, MockSched):
        from config.scheduler import iniciar_scheduler
        iniciar_scheduler()
        inst = MockSched.return_value
        ids = [c.kwargs.get('id') for c in inst.add_job.call_args_list]
        self.assertIn('importar_programacion_lctpc', ids)
        self.assertIn('generar_reportes_diario', ids)  # el job existente sigue


class ImportacionLCTPCViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')
        self.client.force_login(self.user)

    def test_lista_requiere_login(self):
        self.client.logout()
        resp = self.client.get(reverse('modulacion:lctpc_list'))
        self.assertEqual(resp.status_code, 302)

    def test_boton_importar_llama_orquestador_y_redirige(self):
        with patch('modulos.modulacion.views.importar_programaciones_lctpc') as mock_orq:
            mock_orq.return_value = ResumenImportacion(correos_procesados=1, creadas=2)
            resp = self.client.post(reverse('modulacion:lctpc_importar'))
        mock_orq.assert_called_once()
        self.assertRedirects(resp, reverse('modulacion:dashboard'))

    def test_importar_solo_acepta_post(self):
        resp = self.client.get(reverse('modulacion:lctpc_importar'))
        self.assertEqual(resp.status_code, 405)

    def test_detalle_renderiza_filas(self):
        imp = ImportacionProgramacionLCTPC.objects.create(
            graph_message_id='m1', asunto=ASUNTO_07,
            fecha_recibido=timezone.now(), estado='OK', total_renglones=1,
            detalle=[{'contenedor': 'GXYU5129072', 'folio_lctpc': '617210',
                      'resultado': 'CREADA', 'modulacion_id': 1, 'tipo_cita': 'FULL'}],
        )
        resp = self.client.get(reverse('modulacion:lctpc_detail', args=[imp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'GXYU5129072')
        self.assertContains(resp, '617210')
