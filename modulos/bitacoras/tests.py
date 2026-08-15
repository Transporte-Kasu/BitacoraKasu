import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from modulos.finanzas.models import TarifaKilometro
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad

from .models import BitacoraViaje
from config.services.twilio_service import _var_info_carga, _numero_wa_mx, enviar_notificacion_operador


def _crear_unidad(numero_economico='ECO-001'):
    return Unidad.objects.create(
        numero_economico=numero_economico,
        placa='ABC-123',
        tipo='LOCAL',
        año=2020,
        capacidad_combustible=Decimal('200.00'),
        rendimiento_esperado=Decimal('3.00'),
    )


def _crear_operador():
    return Operador.objects.create(nombre='Juan Pérez', tipo='LOCAL')


def _aware(y, m, d, h=8):
    return timezone.make_aware(datetime(y, m, d, h))


class IngresoCalculadoTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad()
        self.operador = _crear_operador()

    def _crear_viaje(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 1),
            fecha_salida=_aware(2026, 6, 1),
            destino='Calle Falsa 123',
            distancia_calculada=Decimal('100.00'),
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    def test_calcula_ingreso_al_completar_viaje_con_tarifa_vigente(self):
        TarifaKilometro.objects.create(valor=Decimal('15.00'), vigente_desde=date(2026, 1, 1))
        viaje = self._crear_viaje(fecha_llegada=_aware(2026, 6, 2))

        viaje.save()

        self.assertEqual(viaje.ingreso_calculado, Decimal('1500.00'))

    def test_ingreso_queda_none_si_no_hay_tarifa_vigente(self):
        viaje = self._crear_viaje(fecha_llegada=_aware(2026, 6, 2))

        viaje.save()

        self.assertIsNone(viaje.ingreso_calculado)

    def test_no_recalcula_ingreso_ya_establecido(self):
        TarifaKilometro.objects.create(valor=Decimal('15.00'), vigente_desde=date(2026, 1, 1))
        viaje = self._crear_viaje(fecha_llegada=_aware(2026, 6, 2), ingreso_calculado=Decimal('999.00'))

        viaje.save()

        self.assertEqual(viaje.ingreso_calculado, Decimal('999.00'))

    def test_viaje_incompleto_no_calcula_ingreso(self):
        TarifaKilometro.objects.create(valor=Decimal('15.00'), vigente_desde=date(2026, 1, 1))
        viaje = self._crear_viaje()

        viaje.save()

        self.assertIsNone(viaje.ingreso_calculado)


class VarInfoCargaTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad()
        self.operador = _crear_operador()

    def _crear_viaje(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 1),
            fecha_salida=_aware(2026, 6, 1),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            tipo_contenedor='40',
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    def test_un_solo_contenedor(self):
        viaje = self._crear_viaje()

        resultado = _var_info_carga(viaje)

        self.assertEqual(
            resultado,
            "Contenedores: MSKU1234567 | Especificaciones: Tipo 40 con peso de 28.05t | Destino Final: BODEGA NORTE, MONTERREY"
        )

    def test_modalidad_full_con_dos_contenedores(self):
        viaje = self._crear_viaje(
            modalidad='FULL',
            contenedor_2='PONU8765436',
            peso_2=Decimal('15.65'),
        )

        resultado = _var_info_carga(viaje)

        self.assertEqual(
            resultado,
            "Contenedores: MSKU1234567 / PONU8765436 | Especificaciones: Tipo 40 (ambos) con pesos de 28.05 y 15.65 respectivamente | Destino Final: BODEGA NORTE, MONTERREY"
        )


class NumeroWaMxTests(TestCase):
    def test_diez_digitos_antepone_codigo_pais(self):
        self.assertEqual(_numero_wa_mx('7531573954'), 'whatsapp:+5217531573954')

    def test_diez_digitos_con_espacios_y_guiones(self):
        self.assertEqual(_numero_wa_mx('753 157 3954'), 'whatsapp:+5217531573954')
        self.assertEqual(_numero_wa_mx('753-157-3954'), 'whatsapp:+5217531573954')

    def test_numero_ya_con_codigo_de_pais_no_se_modifica(self):
        self.assertEqual(_numero_wa_mx('+5217531573954'), 'whatsapp:+5217531573954')


@override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
class EnviarNotificacionOperadorTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad()
        self.operador = Operador.objects.create(
            nombre='Kevin Márquez', tipo='LOCAL', telefono='7531573954'
        )

    def _crear_viaje(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            tipo_contenedor='40',
            observaciones='Custodia: CUSTORESCA\nContacto: LEIZOREK',
            reparto=False,
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    @patch('config.services.twilio_service._twilio_client')
    def test_envia_wa_con_horario_calculado_desde_duracion(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(duracion_estimada=411)

        resultado = enviar_notificacion_operador(viaje)

        self.assertTrue(resultado['wa_ok'])
        mock_messages.create.assert_called_once()
        kwargs = mock_messages.create.call_args.kwargs
        self.assertEqual(kwargs['to'], 'whatsapp:+5217531573954')
        self.assertEqual(kwargs['from_'], 'whatsapp:+14155238886')
        self.assertEqual(kwargs['content_sid'], 'HXfake000000000000000000000000')

        variables = json.loads(kwargs['content_variables'])
        self.assertEqual(
            variables['2'],
            "Destino: BODEGA NORTE, MONTERREY | Horario de entrega: 22 jun 2026 23:51"
        )
        self.assertEqual(
            variables['3'],
            "Servicio DIRECTO ejecutado Custodia: CUSTORESCA\nContacto: LEIZOREK."
        )

    @patch('config.services.twilio_service._twilio_client')
    def test_sin_duracion_estimada_usa_fecha_salida_como_fallback(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(duracion_estimada=None)

        resultado = enviar_notificacion_operador(viaje)

        self.assertTrue(resultado['wa_ok'])
        kwargs = mock_messages.create.call_args.kwargs
        variables = json.loads(kwargs['content_variables'])
        self.assertEqual(
            variables['2'],
            "Destino: BODEGA NORTE, MONTERREY | Horario de entrega: 22 jun 2026 17:00"
        )

    def test_sin_telefono_no_envia_y_retorna_wa_ok_false(self):
        self.operador.telefono = ''
        self.operador.save()
        viaje = self._crear_viaje(duracion_estimada=411)

        resultado = enviar_notificacion_operador(viaje)

        self.assertFalse(resultado['wa_ok'])

    @override_settings(TWILIO_CONTENT_SID_BITACORA='')
    def test_sin_content_sid_configurado_no_envia_y_retorna_wa_ok_false(self):
        viaje = self._crear_viaje(duracion_estimada=411)

        resultado = enviar_notificacion_operador(viaje)

        self.assertFalse(resultado['wa_ok'])

    @patch('config.services.twilio_service._twilio_client')
    def test_excepcion_de_twilio_no_se_propaga(self, mock_client_fn):
        mock_client_fn.return_value.messages.create.side_effect = Exception('boom')
        viaje = self._crear_viaje(duracion_estimada=411)

        resultado = enviar_notificacion_operador(viaje)

        self.assertFalse(resultado['wa_ok'])

    @patch('config.services.twilio_service._twilio_client')
    def test_horario_de_entrega_usa_hora_local_no_utc(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = BitacoraViaje.objects.create(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            tipo_contenedor='40',
            duracion_estimada=411,
        )
        viaje_desde_db = BitacoraViaje.objects.get(pk=viaje.pk)

        resultado = enviar_notificacion_operador(viaje_desde_db)

        self.assertTrue(resultado['wa_ok'])
        kwargs = mock_messages.create.call_args.kwargs
        variables = json.loads(kwargs['content_variables'])
        self.assertIn('22 jun 2026 23:51', variables['2'])


class NotificarOperadorViewTests(TestCase):
    def setUp(self):
        # bitacoras:detail (redirect target) requiere login (LoginRequiredMixin).
        self.user = get_user_model().objects.create_user(username='tester', password='clave-segura-123')
        self.client.force_login(self.user)

        self.unidad = _crear_unidad()
        self.operador = Operador.objects.create(
            nombre='Kevin Márquez', tipo='LOCAL', telefono='7531573954'
        )
        self.viaje = BitacoraViaje.objects.create(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
        )

    @override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_post_exitoso_redirige_con_mensaje_de_exito(self, mock_client_fn):
        mock_client_fn.return_value.messages = MagicMock()

        response = self.client.post(reverse('bitacoras:notificar_operador', args=[self.viaje.pk]))

        self.assertRedirects(response, reverse('bitacoras:detail', args=[self.viaje.pk]))

    @override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_post_exitoso_incluye_mensaje_de_exito_en_response(self, mock_client_fn):
        mock_client_fn.return_value.messages = MagicMock()

        response = self.client.post(
            reverse('bitacoras:notificar_operador', args=[self.viaje.pk]), follow=True
        )

        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('Kevin Márquez' in m and 'WhatsApp enviado' in m for m in mensajes))

    def test_post_sin_telefono_muestra_mensaje_de_error_y_no_llama_twilio(self):
        self.operador.telefono = ''
        self.operador.save()

        with patch('config.services.twilio_service._twilio_client') as mock_client_fn:
            response = self.client.post(
                reverse('bitacoras:notificar_operador', args=[self.viaje.pk]), follow=True
            )
            mock_client_fn.assert_not_called()

        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('No se pudo enviar' in m for m in mensajes))
