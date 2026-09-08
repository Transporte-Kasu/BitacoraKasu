from datetime import date, time
from pathlib import Path

from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase

from .models import ImportacionProgramacionLCTPC, Modulacion
from .services_lctpc import ErrorParseoLCTPC, parsear_programacion

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
