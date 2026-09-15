import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from modulos.bitacoras.models import Cliente
from modulos.modulacion.mensajes_whatsapp import construir_mensajes_whatsapp
from modulos.modulacion.models import Agencia, Modulacion, TerminalPortuaria

FECHA = datetime.date(2026, 9, 11)


def _aware(y, mo, d, h, mi):
    return timezone.make_aware(datetime.datetime(y, mo, d, h, mi))


def _mod(**kw):
    kw.setdefault('agencia', Agencia.objects.get_or_create(nombre='LOGINCO')[0])
    kw.setdefault(
        'terminal_portuaria',
        TerminalPortuaria.objects.get_or_create(
            nombre='L.C. Terminal', defaults={'nombre_corto': 'LCTPC'})[0],
    )
    kw.setdefault('tipo_contenedor', '40HC')
    kw.setdefault('peso_toneladas', Decimal('0.00'))
    kw.setdefault('contenedor', 'CSNU6799471')
    kw.setdefault('fecha_modulacion_aduana', FECHA)
    return Modulacion.objects.create(**kw)


class ConstruirMensajesWhatsappTests(TestCase):
    def test_un_mensaje_por_cliente_excluye_sin_cliente(self):
        mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        nol = Cliente.objects.create(nombre='Nolasco SA', alias='NOL')
        _mod(cliente=mazal, contenedor='CSNU6799471')
        _mod(cliente=mazal, contenedor='CSLU6002657')
        _mod(cliente=nol, contenedor='BBBU3333333')
        _mod(cliente=None, contenedor='DDDU5555555')

        mensajes = construir_mensajes_whatsapp(FECHA)

        self.assertEqual(len(mensajes), 2)
        clientes_enviados = [c for c, _texto in mensajes]
        self.assertEqual(clientes_enviados, [mazal, nol])

    def test_contenido_del_mensaje_trae_encabezado_y_maniobras(self):
        mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        _mod(cliente=mazal, contenedor='CSNU6799471',
             hora_registro=_aware(2026, 9, 11, 10, 30),
             hora_ingreso=_aware(2026, 9, 11, 12, 0))
        _mod(cliente=mazal, contenedor='CSLU6002657')

        mensajes = construir_mensajes_whatsapp(FECHA)
        _cliente, texto = mensajes[0]

        self.assertIn('11-sep-26', texto)
        self.assertIn('MAZAL TOV IMPORTACIONES, SA DE CV', texto)
        self.assertIn('2 maniobra(s)', texto)
        self.assertIn('Maniobra Nº 1', texto)
        self.assertIn('Maniobra Nº 2', texto)
        self.assertIn('Contenedor: CSNU6799471', texto)
        self.assertIn('Contenedor: CSLU6002657', texto)
        self.assertIn('Registro:', texto)
        self.assertIn('CITA PENDIENTE', texto)  # el segundo contenedor no tiene horas

    def test_sin_clientes_en_la_fecha_devuelve_lista_vacia(self):
        self.assertEqual(construir_mensajes_whatsapp(FECHA), [])


from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse


class PrevisualizarWhatsappDespachoViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')

    def test_requiere_login(self):
        resp = self.client.get(reverse('modulacion:reporte_despacho_whatsapp_preview'))
        self.assertEqual(resp.status_code, 302)

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='5217531234567')
    def test_muestra_un_bloque_por_mensaje(self):
        self.client.force_login(self.user)
        mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        _mod(cliente=mazal, contenedor='CSNU6799471')
        resp = self.client.get(
            reverse('modulacion:reporte_despacho_whatsapp_preview'), {'fecha': FECHA.isoformat()})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'MAZAL TOV IMPORTACIONES, SA DE CV')
        self.assertContains(resp, 'Maniobra Nº 1')
        self.assertContains(resp, 'Confirmar y enviar')

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='')
    def test_sin_numero_configurado_deshabilita_envio(self):
        self.client.force_login(self.user)
        mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        _mod(cliente=mazal, contenedor='CSNU6799471')
        resp = self.client.get(
            reverse('modulacion:reporte_despacho_whatsapp_preview'), {'fecha': FECHA.isoformat()})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'WA_PROGRAMA_DESPACHO_NUMERO')
        self.assertNotContains(resp, 'Confirmar y enviar')

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='5217531234567')
    def test_sin_grupos_muestra_aviso(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse('modulacion:reporte_despacho_whatsapp_preview'), {'fecha': FECHA.isoformat()})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No hay maniobras con cliente asignado')


class ReporteDespachoBotonWhatsappTests(TestCase):
    def test_boton_vista_previa_presente(self):
        user = get_user_model().objects.create_user('u2', 'u2@e.com', 'pw')
        self.client.force_login(user)
        resp = self.client.get(reverse('modulacion:reporte_despacho'))
        self.assertContains(resp, reverse('modulacion:reporte_despacho_whatsapp_preview'))
