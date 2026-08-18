import json
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch, MagicMock

import openpyxl
from django.contrib.auth import get_user_model
from django.contrib.messages import constants as message_constants
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from modulos.finanzas.models import TarifaKilometro
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad

from .models import BitacoraViaje, Cliente
from .forms import BitacoraViajeForm
from .excel_parser import _parse_fecha_entrega, parse_confirmacion_excel
from config.services.twilio_service import (
    _var_info_carga,
    _var_info_carga_contenedor,
    _numero_wa_mx,
    _sanitizar_texto,
    enviar_notificacion_bitacora,
    enviar_notificaciones_reparto,
    enviar_notificacion_operador,
    _cuerpo_email,
)


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
            "Servicio DIRECTO ejecutado Custodia: CUSTORESCA | Contacto: LEIZOREK."
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

    @patch('config.services.twilio_service._twilio_client')
    def test_usa_fecha_hora_entrega_real_cuando_esta_presente(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(
            duracion_estimada=411,
            fecha_hora_entrega=_aware(2026, 6, 25, 8),
        )

        resultado = enviar_notificacion_operador(viaje)

        self.assertTrue(resultado['wa_ok'])
        kwargs = mock_messages.create.call_args.kwargs
        variables = json.loads(kwargs['content_variables'])
        self.assertEqual(
            variables['2'],
            "Destino: BODEGA NORTE, MONTERREY | Horario de entrega: 25 jun 2026 08:00"
        )


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


class FechaHoraEntregaModeloTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-400')
        self.operador = _crear_operador()

    def _crear_viaje(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            cp_origen='40812',
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    def test_por_defecto_es_none(self):
        viaje = self._crear_viaje()
        viaje.save()

        viaje_desde_db = BitacoraViaje.objects.get(pk=viaje.pk)

        self.assertIsNone(viaje_desde_db.fecha_hora_entrega)

    def test_se_guarda_y_recupera_correctamente(self):
        viaje = self._crear_viaje(fecha_hora_entrega=_aware(2026, 6, 25, 8))
        viaje.save()

        viaje_desde_db = BitacoraViaje.objects.get(pk=viaje.pk)

        self.assertEqual(
            timezone.localtime(viaje_desde_db.fecha_hora_entrega).strftime('%Y-%m-%d %H:%M'),
            '2026-06-25 08:00'
        )


class ParseFechaEntregaTests(TestCase):
    def test_con_hora(self):
        resultado = _parse_fecha_entrega('25/06/2026    08:00 HRS')
        self.assertEqual(resultado, datetime(2026, 6, 25, 8, 0))

    def test_sin_hora_usa_medianoche(self):
        resultado = _parse_fecha_entrega('25/06/2026')
        self.assertEqual(resultado, datetime(2026, 6, 25, 0, 0))

    def test_vacio_retorna_none(self):
        self.assertIsNone(_parse_fecha_entrega(None))
        self.assertIsNone(_parse_fecha_entrega(''))

    def test_hora_fuera_de_rango_cae_a_medianoche_sin_lanzar_excepcion(self):
        resultado = _parse_fecha_entrega('25/06/2026 24:00 HRS')
        self.assertEqual(resultado, datetime(2026, 6, 25, 0, 0))


def _construir_excel_confirmacion(filas):
    """Construye un .xlsx en memoria con el encabezado esperado por parse_confirmacion_excel."""
    wb = openpyxl.Workbook()
    ws = wb.active
    header = [
        'FECHA ENTREGA / HORARIO', 'CONTENEDOR', 'CUSTODIA', 'DIRECCION CARTA PORTE',
        'DIRECCION DE ENTREGA', 'MODALIDAD', 'CONTACTO BODEGA', 'CODIGO SAT',
        'MERCANCIA', 'UNIDAD MEDIDA', 'CANTIDAD', 'PESOS (KG)', 'PEDIMENTO',
    ]
    ws.append(header)
    for fila in filas:
        ws.append(fila)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class ParseConfirmacionExcelFechaHoraEntregaTests(TestCase):
    def test_expone_fecha_hora_entrega_y_display_con_hora(self):
        archivo = _construir_excel_confirmacion([
            [
                '25/06/2026    08:00 HRS', 'MSKU1234567', 'CUSTORESCA',
                'Dirección carta porte X', 'Bodega Norte CP 90200',
                'SENCILLO', 'Juan', None, 'Caja fuerte', None, None, 28050, 'PED123',
            ],
        ])

        viajes = parse_confirmacion_excel(archivo, '17:00', '08:00', '40')

        self.assertEqual(len(viajes), 1)
        self.assertEqual(viajes[0]['fecha_hora_entrega'], '2026-06-25T08:00')
        self.assertEqual(viajes[0]['fecha_entrega_display'], '25/06/2026 08:00')

    def test_fila_sin_hora_en_la_celda_expone_medianoche(self):
        archivo = _construir_excel_confirmacion([
            [
                '25/06/2026', 'MSKU1234567', 'CUSTORESCA',
                'Dirección carta porte X', 'Bodega Norte CP 90200',
                'SENCILLO', 'Juan', None, 'Caja fuerte', None, None, 28050, 'PED123',
            ],
        ])

        viajes = parse_confirmacion_excel(archivo, '17:00', '08:00', '40')

        self.assertEqual(viajes[0]['fecha_hora_entrega'], '2026-06-25T00:00')
        self.assertEqual(viajes[0]['fecha_entrega_display'], '25/06/2026 00:00')


class CargaMasivaFechaHoraEntregaTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester_carga', password='clave-segura-123')
        self.client.force_login(self.user)
        self.unidad = _crear_unidad(numero_economico='ECO-500')
        self.operador = _crear_operador()

    def _datos_post(self, **overrides):
        datos = {
            'total_viajes': '1',
            'v0_modalidad': 'SENCILLO',
            'v0_contenedor': 'MSKU1234567',
            'v0_peso': '28.05',
            'v0_destino': 'Bodega Norte, Monterrey',
            'v0_cp_destino': '90200',
            'v0_fecha_salida': '2026-06-24T17:00',
            'v0_fecha_carga': '2026-06-24T08:00',
            'v0_tipo_contenedor': '40',
            'v0_operador': str(self.operador.pk),
            'v0_unidad': str(self.unidad.pk),
        }
        datos.update(overrides)
        return datos

    def test_post_con_fecha_hora_entrega_la_persiste(self):
        response = self.client.post(
            reverse('bitacoras:carga_masiva_preview'),
            self._datos_post(v0_fecha_hora_entrega='2026-06-25T08:00'),
        )

        self.assertEqual(response.status_code, 302)
        viaje = BitacoraViaje.objects.get(contenedor='MSKU1234567')
        self.assertEqual(
            timezone.localtime(viaje.fecha_hora_entrega).strftime('%Y-%m-%d %H:%M'),
            '2026-06-25 08:00'
        )

    def test_post_sin_fecha_hora_entrega_guarda_none(self):
        response = self.client.post(
            reverse('bitacoras:carga_masiva_preview'),
            self._datos_post(),
        )

        self.assertEqual(response.status_code, 302)
        viaje = BitacoraViaje.objects.get(contenedor='MSKU1234567')
        self.assertIsNone(viaje.fecha_hora_entrega)


class BitacoraViajeFormFechaHoraEntregaTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-600')
        self.operador = _crear_operador()

    def _datos_base(self, **overrides):
        datos = dict(
            modalidad='SENCILLO',
            operador=self.operador.pk,
            unidad=self.unidad.pk,
            fecha_carga='2026-06-22T08:00',
            fecha_salida='2026-06-22T17:00',
            contenedor='MSKU1234567',
            tipo_contenedor='40',
            peso='28.05',
            cp_origen='40812',
            destino='Bodega Norte, Monterrey',
        )
        datos.update(overrides)
        return datos

    def test_valido_sin_fecha_hora_entrega(self):
        form = BitacoraViajeForm(data=self._datos_base())

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['fecha_hora_entrega'])

    def test_valido_con_fecha_hora_entrega(self):
        form = BitacoraViajeForm(data=self._datos_base(fecha_hora_entrega='2026-06-21T08:00'))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['fecha_hora_entrega'].strftime('%Y-%m-%d %H:%M'),
            '2026-06-21 08:00'
        )

    def test_editar_viaje_existente_preserva_fecha_hora_entrega_en_el_render(self):
        viaje = BitacoraViaje.objects.create(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            cp_origen='40812',
            tipo_contenedor='40',
            fecha_hora_entrega=_aware(2026, 6, 25, 8),
        )
        viaje_desde_db = BitacoraViaje.objects.get(pk=viaje.pk)

        form = BitacoraViajeForm(instance=viaje_desde_db)

        self.assertIn('2026-06-25T08:00', str(form['fecha_hora_entrega']))


class SanitizarTextoTests(TestCase):
    def test_saltos_de_linea_se_convierten_en_separador_pipe(self):
        resultado = _sanitizar_texto('Custodia: CUSTORESCA\nContacto: LEIZOREK\nMercancía: CAJA FUERTE')

        self.assertEqual(
            resultado,
            'Custodia: CUSTORESCA | Contacto: LEIZOREK | Mercancía: CAJA FUERTE'
        )

    def test_tabs_se_convierten_en_espacio(self):
        resultado = _sanitizar_texto('Custodia:\tCUSTORESCA')

        self.assertEqual(resultado, 'Custodia: CUSTORESCA')

    def test_espacios_multiples_colapsan(self):
        resultado = _sanitizar_texto('Custodia:      CUSTORESCA')

        self.assertEqual(resultado, 'Custodia: CUSTORESCA')

    def test_texto_vacio_o_none_se_retorna_tal_cual(self):
        self.assertEqual(_sanitizar_texto(''), '')
        self.assertIsNone(_sanitizar_texto(None))

    def test_sin_saltos_ni_tabs_no_se_modifica(self):
        resultado = _sanitizar_texto('Bodega Norte, Monterrey')

        self.assertEqual(resultado, 'Bodega Norte, Monterrey')


class VarInfoCargaSaneamientoTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-800')
        self.operador = _crear_operador()

    def test_destino_con_salto_de_linea_se_sanea(self):
        viaje = BitacoraViaje(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 1),
            fecha_salida=_aware(2026, 6, 1),
            destino='Bodega Norte\nMonterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            tipo_contenedor='40',
        )

        resultado = _var_info_carga(viaje)

        self.assertNotIn('\n', resultado)
        self.assertIn('BODEGA NORTE | MONTERREY', resultado)


@override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
class EnviarNotificacionBitacoraObservacionesTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-900')
        self.operador = _crear_operador()
        self.cliente = Cliente.objects.create(nombre='Acme S.A.', celular='+5217531234567', activo=True)

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
    def test_observaciones_multilinea_no_rompe_content_variables(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje()

        resultado = enviar_notificacion_bitacora(viaje, self.cliente)

        self.assertTrue(resultado['wa_ok'])
        kwargs = mock_messages.create.call_args.kwargs
        variables = json.loads(kwargs['content_variables'])
        self.assertNotIn('\n', variables['3'])
        self.assertEqual(
            variables['3'],
            'Servicio DIRECTO ejecutado Custodia: CUSTORESCA | Contacto: LEIZOREK.'
        )

    def test_cuerpo_email_conserva_saltos_de_linea_reales_en_observaciones(self):
        viaje = self._crear_viaje()
        variables = {
            '1': _var_info_carga(viaje),
            '2': 'Unidad: ECO-900 (Placas ABC-123) | Operador: Juan Pérez  | Salida: 22 jun 2026 17:00',
            '3': 'Servicio DIRECTO ejecutado Custodia: CUSTORESCA | Contacto: LEIZOREK.',
        }

        cuerpo = _cuerpo_email(viaje, variables)

        self.assertIn('Custodia: CUSTORESCA\nContacto: LEIZOREK', cuerpo)


class RepartoValidacionModeloTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-950')
        self.operador = _crear_operador()
        self.cliente = Cliente.objects.create(nombre='Cliente Uno', celular='+5217531234567')
        self.cliente_2 = Cliente.objects.create(nombre='Cliente Dos', celular='+5217539876543')

    def _crear_viaje_full(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='FULL',
            fecha_carga=_aware(2026, 6, 1),
            fecha_salida=_aware(2026, 6, 1),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            contenedor_2='PONU8765436',
            peso_2=Decimal('15.65'),
            cp_destino='64000',
            reparto=True,
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    def test_reparto_sin_cp_destino_2_es_invalido(self):
        viaje = self._crear_viaje_full(cp_destino_2='')

        with self.assertRaises(ValidationError) as ctx:
            viaje.clean()

        self.assertIn('cp_destino_2', ctx.exception.message_dict)

    def test_reparto_con_cp_destino_2_igual_a_cp_destino_es_valido(self):
        viaje = self._crear_viaje_full(cp_destino_2='64000')

        viaje.clean()  # no debe lanzar

    def test_reparto_con_cliente_2_y_fecha_hora_entrega_2_se_guardan(self):
        viaje = self._crear_viaje_full(
            cp_destino_2='64010',
            cliente=self.cliente,
            cliente_2=self.cliente_2,
            fecha_hora_entrega=_aware(2026, 6, 2, 10),
            fecha_hora_entrega_2=_aware(2026, 6, 2, 15),
        )
        viaje.full_clean()
        viaje.save()

        viaje_desde_db = BitacoraViaje.objects.get(pk=viaje.pk)
        self.assertEqual(viaje_desde_db.cliente_2, self.cliente_2)
        self.assertEqual(viaje_desde_db.fecha_hora_entrega_2, _aware(2026, 6, 2, 15))

    def test_reparto_sin_cliente_2_ni_fecha_hora_entrega_2_es_valido(self):
        viaje = self._crear_viaje_full(cp_destino_2='64010')

        viaje.clean()  # no debe lanzar — ambos campos son opcionales


class BitacoraViajeAdminRepartoTests(TestCase):
    """
    Regresión: el ModelForm que construye el admin para BitacoraViaje debe
    incluir cp_destino_2. Si no lo incluye, BitacoraViaje.clean() sigue
    exigiendo ese campo cuando reparto=True (Model.full_clean() llama a
    clean() sin filtrar por exclude), pero como el ModelForm del admin no
    tiene ese campo declarado, BaseForm.add_error() revienta con un
    ValueError ("'X' has no field named 'cp_destino_2'") en vez de mostrar
    un error de validación normal. Ver fieldset 'Destino' en admin.py.
    """

    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-970')
        self.operador = _crear_operador()

    def _get_admin_form_class(self):
        from django.contrib import admin as django_admin

        admin_instance = django_admin.site._registry[BitacoraViaje]
        # get_form necesita un `request` con `.user` (usado por
        # get_readonly_fields / has_change_permission); un MagicMock basta
        # porque aquí solo nos interesa la clase de formulario resultante.
        return admin_instance.get_form(MagicMock())

    def _datos_full_reparto(self, **overrides):
        # El admin renderiza los DateTimeField del modelo con el widget
        # SplitDateTimeField propio del admin (AdminSplitDateTime), que
        # espera dos subcampos (fecha y hora) en vez de un solo string.
        datos = {
            'modalidad': 'FULL',
            'operador': self.operador.pk,
            'unidad': self.unidad.pk,
            'fecha_carga_0': '2026-06-22',
            'fecha_carga_1': '08:00',
            'fecha_salida_0': '2026-06-22',
            'fecha_salida_1': '17:00',
            'contenedor': 'MSKU1234567',
            'peso': '28.05',
            'contenedor_2': 'PONU8765436',
            'peso_2': '15.65',
            'cp_origen': '40812',
            'cp_destino': '64000',
            'destino': 'Bodega Norte, Monterrey',
            'reparto': True,
        }
        datos.update(overrides)
        return datos

    def test_form_del_admin_incluye_cp_destino_2(self):
        form_class = self._get_admin_form_class()

        self.assertIn('cp_destino_2', form_class.base_fields)

    def test_form_del_admin_reparto_sin_cp_destino_2_no_revienta(self):
        form_class = self._get_admin_form_class()
        form = form_class(data=self._datos_full_reparto(cp_destino_2=''))

        # No debe lanzar ValueError: debe comportarse como una validación
        # normal, con el error reportado en el campo correspondiente.
        is_valid = form.is_valid()

        self.assertFalse(is_valid)
        self.assertIn('cp_destino_2', form.errors)

    def test_form_del_admin_reparto_con_cp_destino_2_es_valido(self):
        form_class = self._get_admin_form_class()
        form = form_class(data=self._datos_full_reparto(cp_destino_2='64010'))

        self.assertTrue(form.is_valid(), form.errors)


class BitacoraViajeFormRepartoValidacionTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-960')
        self.operador = _crear_operador()
        self.cliente = Cliente.objects.create(nombre='Cliente Uno', celular='+5217531234567')

    def _datos_full_reparto(self, **overrides):
        datos = dict(
            modalidad='FULL',
            operador=self.operador.pk,
            unidad=self.unidad.pk,
            fecha_carga='2026-06-22T08:00',
            fecha_salida='2026-06-22T17:00',
            contenedor='MSKU1234567',
            tipo_contenedor='40',
            peso='28.05',
            contenedor_2='PONU8765436',
            peso_2='15.65',
            cp_origen='40812',
            cp_destino='64000',
            destino='Bodega Norte, Monterrey',
            reparto=True,
        )
        datos.update(overrides)
        return datos

    def test_reparto_sin_cp_destino_2_es_invalido(self):
        form = BitacoraViajeForm(data=self._datos_full_reparto(cp_destino_2=''))

        self.assertFalse(form.is_valid())
        self.assertIn('cp_destino_2', form.errors)

    def test_reparto_con_cp_destino_2_es_valido(self):
        form = BitacoraViajeForm(data=self._datos_full_reparto(cp_destino_2='64010'))

        self.assertTrue(form.is_valid(), form.errors)

    def test_reparto_cliente_2_y_fecha_hora_entrega_2_son_opcionales(self):
        form = BitacoraViajeForm(data=self._datos_full_reparto(cp_destino_2='64010'))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['cliente_2'])
        self.assertIsNone(form.cleaned_data['fecha_hora_entrega_2'])

    def test_reparto_con_cliente_2_y_fecha_hora_entrega_2_presentes(self):
        form = BitacoraViajeForm(data=self._datos_full_reparto(
            cp_destino_2='64010',
            cliente_2=self.cliente.pk,
            fecha_hora_entrega_2='2026-06-23T09:00',
        ))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['cliente_2'], self.cliente)


@override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
class EnviarNotificacionesRepartoTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad(numero_economico='ECO-970')
        self.operador = Operador.objects.create(
            nombre='Kevin Márquez', tipo='LOCAL', telefono='7531573954'
        )
        self.cliente = Cliente.objects.create(nombre='Cliente Uno', celular='+5217531111111', email='uno@acme.mx')
        self.cliente_2 = Cliente.objects.create(nombre='Cliente Dos', celular='+5217532222222', email='dos@acme.mx')

    def _crear_viaje(self, **overrides):
        defaults = dict(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='FULL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            contenedor_2='PONU8765436',
            peso_2=Decimal('15.65'),
            tipo_contenedor='40',
            cp_destino='64000',
            cp_destino_2='64010',
            reparto=True,
            cliente=self.cliente,
        )
        defaults.update(overrides)
        return BitacoraViaje(**defaults)

    def test_var_info_carga_contenedor_usa_datos_propios(self):
        viaje = self._crear_viaje()

        self.assertEqual(
            _var_info_carga_contenedor(viaje, 1),
            "Contenedor: MSKU1234567 | Especificaciones: Tipo 40 con peso de 28.05t | Destino Final: CP 64000"
        )
        self.assertEqual(
            _var_info_carga_contenedor(viaje, 2),
            "Contenedor: PONU8765436 | Especificaciones: Tipo 40 con peso de 15.65t | Destino Final: CP 64010"
        )

    @patch('config.services.twilio_service._twilio_client')
    def test_mismo_cliente_recibe_dos_notificaciones_independientes(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje()  # cliente_2 no asignado

        resultado = enviar_notificaciones_reparto(viaje)

        self.assertTrue(resultado['contenedor_1']['wa_ok'])
        self.assertTrue(resultado['contenedor_2']['wa_ok'])
        self.assertEqual(mock_messages.create.call_count, 2)

        llamadas = mock_messages.create.call_args_list
        destinos = {json.loads(c.kwargs['content_variables'])['1'] for c in llamadas}
        self.assertIn('Contenedor: MSKU1234567', ''.join(destinos))
        self.assertIn('Contenedor: PONU8765436', ''.join(destinos))
        for c in llamadas:
            self.assertEqual(c.kwargs['to'], 'whatsapp:+5217531111111')

    @patch('config.services.twilio_service._twilio_client')
    def test_cliente_2_distinto_recibe_su_propio_mensaje(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(cliente_2=self.cliente_2)

        resultado = enviar_notificaciones_reparto(viaje)

        self.assertTrue(resultado['contenedor_1']['wa_ok'])
        self.assertTrue(resultado['contenedor_2']['wa_ok'])
        llamadas = mock_messages.create.call_args_list
        destinatarios = {c.kwargs['to'] for c in llamadas}
        self.assertEqual(destinatarios, {'whatsapp:+5217531111111', 'whatsapp:+5217532222222'})

    @patch('config.services.twilio_service._twilio_client')
    def test_fecha_hora_entrega_2_vacia_usa_fecha_hora_entrega(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(fecha_hora_entrega=_aware(2026, 6, 23, 9))

        enviar_notificaciones_reparto(viaje)

        llamadas = mock_messages.create.call_args_list
        var2s = [json.loads(c.kwargs['content_variables'])['2'] for c in llamadas]
        self.assertTrue(all('Entrega: 23 jun 2026 09:00' in v for v in var2s))

    @patch('config.services.twilio_service._twilio_client')
    def test_fecha_hora_entrega_2_presente_se_usa_para_contenedor_2(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(
            fecha_hora_entrega=_aware(2026, 6, 23, 9),
            fecha_hora_entrega_2=_aware(2026, 6, 23, 15),
        )

        enviar_notificaciones_reparto(viaje)

        llamadas = mock_messages.create.call_args_list
        variables_por_llamada = [json.loads(c.kwargs['content_variables']) for c in llamadas]
        var2_contenedor_1 = next(v['2'] for v in variables_por_llamada if 'MSKU1234567' in v['1'])
        var2_contenedor_2 = next(v['2'] for v in variables_por_llamada if 'PONU8765436' in v['1'])
        self.assertIn('Entrega: 23 jun 2026 09:00', var2_contenedor_1)
        self.assertIn('Entrega: 23 jun 2026 15:00', var2_contenedor_2)

    @patch('config.services.twilio_service._twilio_client')
    def test_sin_cliente_en_contenedor_1_no_envia_esa_notificacion(self, mock_client_fn):
        mock_messages = MagicMock()
        mock_client_fn.return_value.messages = mock_messages
        viaje = self._crear_viaje(cliente=None, cliente_2=self.cliente_2)

        resultado = enviar_notificaciones_reparto(viaje)

        self.assertIsNone(resultado['contenedor_1'])
        self.assertTrue(resultado['contenedor_2']['wa_ok'])
        self.assertEqual(mock_messages.create.call_count, 1)


class NotificarClienteRepartoViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='tester2', password='clave-segura-123')
        self.client.force_login(self.user)

        self.unidad = _crear_unidad(numero_economico='ECO-980')
        self.operador = Operador.objects.create(
            nombre='Kevin Márquez', tipo='LOCAL', telefono='7531573954'
        )
        self.cliente = Cliente.objects.create(nombre='Cliente Uno', celular='+5217531111111')
        self.cliente_2 = Cliente.objects.create(nombre='Cliente Dos', celular='+5217532222222')
        self.viaje = BitacoraViaje.objects.create(
            operador=self.operador,
            unidad=self.unidad,
            modalidad='FULL',
            fecha_carga=_aware(2026, 6, 22, 8),
            fecha_salida=_aware(2026, 6, 22, 17),
            destino='Bodega Norte, Monterrey',
            contenedor='MSKU1234567',
            peso=Decimal('28.05'),
            contenedor_2='PONU8765436',
            peso_2=Decimal('15.65'),
            cp_destino='64000',
            cp_destino_2='64010',
            reparto=True,
            cliente=self.cliente,
            cliente_2=self.cliente_2,
        )

    @override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_reparto_notifica_a_los_dos_clientes(self, mock_client_fn):
        mock_client_fn.return_value.messages = MagicMock()

        response = self.client.post(
            reverse('bitacoras:notificar_cliente', args=[self.viaje.pk]), follow=True
        )

        self.assertEqual(mock_client_fn.return_value.messages.create.call_count, 2)
        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('Cliente Uno' in m and 'Cliente Dos' in m for m in mensajes))

    def test_reparto_sin_ningun_cliente_asignado_muestra_error(self):
        self.viaje.cliente = None
        self.viaje.cliente_2 = None
        self.viaje.save()

        with patch('config.services.twilio_service._twilio_client') as mock_client_fn:
            response = self.client.post(
                reverse('bitacoras:notificar_cliente', args=[self.viaje.pk]), follow=True
            )
            mock_client_fn.assert_not_called()

        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('no tiene cliente asignado' in m for m in mensajes))

    @override_settings(TWILIO_CONTENT_SID_BITACORA='HXfake000000000000000000000000', TWILIO_WHATSAPP_FROM='whatsapp:+14155238886')
    @patch('config.services.twilio_service._twilio_client')
    def test_sin_reparto_sigue_notificando_a_un_solo_cliente(self, mock_client_fn):
        mock_client_fn.return_value.messages = MagicMock()
        self.viaje.reparto = False
        self.viaje.save()

        response = self.client.post(
            reverse('bitacoras:notificar_cliente', args=[self.viaje.pk]), follow=True
        )

        self.assertEqual(mock_client_fn.return_value.messages.create.call_count, 1)
        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('Cliente Uno' in m and 'WhatsApp enviado' in m for m in mensajes))

    @override_settings(TWILIO_CONTENT_SID_BITACORA='')
    @patch('config.services.twilio_service._twilio_client')
    def test_reparto_ambas_notificaciones_fallan_muestra_error(self, mock_client_fn):
        response = self.client.post(
            reverse('bitacoras:notificar_cliente', args=[self.viaje.pk]), follow=True
        )

        mock_client_fn.assert_not_called()

        mensajes = list(response.context['messages'])
        self.assertTrue(any('no se pudo enviar' in str(m) for m in mensajes))
        self.assertTrue(
            all(m.level != message_constants.SUCCESS for m in mensajes),
            f"No debe mostrarse un mensaje de éxito cuando ambas notificaciones fallan: {[str(m) for m in mensajes]}",
        )
        self.assertTrue(any(m.level == message_constants.ERROR for m in mensajes))
