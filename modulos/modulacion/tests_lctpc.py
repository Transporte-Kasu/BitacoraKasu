from datetime import date

from django.db import IntegrityError
from django.test import TestCase

from .models import ImportacionProgramacionLCTPC, Modulacion


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
