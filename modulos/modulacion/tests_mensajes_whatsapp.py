import datetime
import json
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

    def test_tipo_usa_solo_los_digitos_iniciales_como_en_el_xlsx(self):
        # Debe coincidir con reportes._tipo(): '40HC' -> '40', no el campo crudo.
        mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        _mod(cliente=mazal, contenedor='CSNU6799471', tipo_contenedor='40HC')

        _cliente, texto = construir_mensajes_whatsapp(FECHA)[0]

        self.assertIn('Tipo: 40   Peso:', texto)
        self.assertNotIn('Tipo: 40HC', texto)


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

    def test_boton_vista_previa_comparte_el_input_de_fecha(self):
        # El botón de WhatsApp debe vivir en el MISMO <form> que el input de
        # fecha (vía formaction), no en un <form> hermano con su propio
        # hidden — de lo contrario la fecha editada nunca le llega.
        user = get_user_model().objects.create_user('u4', 'u4@e.com', 'pw')
        self.client.force_login(user)
        resp = self.client.get(reverse('modulacion:reporte_despacho'))
        contenido = resp.content.decode()
        # El form de logout de base.html es el único otro <form> de la página.
        self.assertEqual(contenido.count('<form'), 2)
        self.assertIn(
            f'formaction="{reverse("modulacion:reporte_despacho_whatsapp_preview")}"',
            contenido,
        )


from unittest.mock import MagicMock, patch


class EnviarWhatsappDespachoViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u3', 'u3@e.com', 'pw')
        self.client.force_login(self.user)
        self.mazal = Cliente.objects.create(nombre='MAZAL TOV IMPORTACIONES, SA DE CV')
        self.nol = Cliente.objects.create(nombre='Nolasco SA', alias='NOL')
        _mod(cliente=self.mazal, contenedor='CSNU6799471')
        _mod(cliente=self.nol, contenedor='BBBU3333333')

    def test_requiere_login(self):
        self.client.logout()
        resp = self.client.post(
            reverse('modulacion:reporte_despacho_whatsapp_enviar'), {'fecha': FECHA.isoformat()})
        self.assertEqual(resp.status_code, 302)

    def test_rechaza_get(self):
        resp = self.client.get(
            reverse('modulacion:reporte_despacho_whatsapp_enviar'), {'fecha': FECHA.isoformat()})
        self.assertEqual(resp.status_code, 405)

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='5217531234567')
    @patch('modulos.modulacion.views.enviar_mensaje_despacho')
    def test_envia_un_mensaje_por_grupo_con_el_numero_configurado(self, mock_enviar):
        mock_enviar.return_value = True
        resp = self.client.post(
            reverse('modulacion:reporte_despacho_whatsapp_enviar'), {'fecha': FECHA.isoformat()})
        self.assertRedirects(
            resp, f"{reverse('modulacion:reporte_despacho')}?fecha={FECHA.isoformat()}")
        self.assertEqual(mock_enviar.call_count, 2)
        for llamada in mock_enviar.call_args_list:
            self.assertEqual(llamada.args[1], '5217531234567')

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='5217531234567')
    @patch('modulos.modulacion.views.enviar_mensaje_despacho')
    def test_reporta_fallos_por_cliente(self, mock_enviar):
        mock_enviar.side_effect = [True, False]
        resp = self.client.post(
            reverse('modulacion:reporte_despacho_whatsapp_enviar'), {'fecha': FECHA.isoformat()},
            follow=True)
        mensajes = [str(m) for m in resp.context['messages']]
        self.assertTrue(any('1' in m and 'enviad' in m for m in mensajes))
        self.assertTrue(any('Nolasco SA' in m or 'NOL' in m for m in mensajes))

    @override_settings(WA_PROGRAMA_DESPACHO_NUMERO='')
    @patch('modulos.modulacion.views.enviar_mensaje_despacho')
    def test_sin_numero_configurado_no_envia_nada(self, mock_enviar):
        resp = self.client.post(
            reverse('modulacion:reporte_despacho_whatsapp_enviar'), {'fecha': FECHA.isoformat()},
            follow=True)
        mock_enviar.assert_not_called()
        mensajes = [str(m) for m in resp.context['messages']]
        self.assertTrue(any('WA_PROGRAMA_DESPACHO_NUMERO' in m for m in mensajes))


class EnviarMensajeDespachoTests(TestCase):
    """
    enviar_mensaje_despacho reusa la plantilla Twilio 'alerta_kasu'
    (TWILIO_CONTENT_SID_ALERTA, variable única {{1}}) — no hay plantilla
    propia de Programa de despacho. El destinatario es personal interno,
    no el cliente final.
    """
    @override_settings(TWILIO_CONTENT_SID_ALERTA='HXfake000000000000000000000000',
                        TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_envia_un_solo_mensaje_cuando_cabe_en_el_limite(self, mock_client_fn):
        from config.services.twilio_service import enviar_mensaje_despacho

        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages

        resultado = enviar_mensaje_despacho('Programa de despacho — 11-sep-26\ntexto corto', '+5217531004073')

        self.assertTrue(resultado)
        mock_messages.create.assert_called_once()
        kwargs = mock_messages.create.call_args.kwargs
        self.assertEqual(kwargs['to'], 'whatsapp:+5217531004073')
        self.assertEqual(kwargs['from_'], 'whatsapp:+14155238886')
        self.assertEqual(kwargs['content_sid'], 'HXfake000000000000000000000000')
        variables = json.loads(kwargs['content_variables'])
        self.assertEqual(variables['1'], 'Programa de despacho — 11-sep-26 | texto corto')

    @override_settings(TWILIO_CONTENT_SID_ALERTA='HXfake000000000000000000000000',
                        TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_parte_en_varios_mensajes_cuando_excede_el_limite(self, mock_client_fn):
        from config.services.twilio_service import enviar_mensaje_despacho

        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages

        bloques = [f'Maniobra Nº {i}\n  Contenedor: CSNU{i:07d}\n  ' + ('x' * 300) for i in range(1, 8)]
        texto = '\n\n'.join(['*Programa de despacho — 11-sep-26*'] + bloques + ['_BitacoraKasu_'])

        resultado = enviar_mensaje_despacho(texto, '+5217531004073')

        self.assertTrue(resultado)
        self.assertGreater(mock_messages.create.call_count, 1)
        for llamada in mock_messages.create.call_args_list:
            variables = json.loads(llamada.kwargs['content_variables'])
            self.assertLessEqual(len(variables['1']), 1500)
            self.assertNotIn('\n', variables['1'])

    @override_settings(TWILIO_CONTENT_SID_ALERTA='HXfake000000000000000000000000',
                        TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_si_una_parte_falla_el_resultado_es_falso(self, mock_client_fn):
        from config.services.twilio_service import enviar_mensaje_despacho

        mock_messages = MagicMock()
        mock_messages.create.side_effect = [MagicMock(), Exception('boom')]
        mock_client_fn.return_value.messages = mock_messages

        bloques = [f'Maniobra Nº {i}\n  ' + ('x' * 300) for i in range(1, 8)]
        texto = '\n\n'.join(['*Programa de despacho*'] + bloques + ['_pie_'])

        resultado = enviar_mensaje_despacho(texto, '+5217531004073')

        self.assertFalse(resultado)

    @override_settings(TWILIO_CONTENT_SID_ALERTA='')
    def test_sin_content_sid_configurado_no_envia(self):
        from config.services.twilio_service import enviar_mensaje_despacho

        self.assertFalse(enviar_mensaje_despacho('texto', '+5217531004073'))
