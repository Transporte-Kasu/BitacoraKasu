import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from modulos.bitacoras.models import BitacoraViaje, Cliente
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad

from .models import Agencia, Modulacion, TerminalPortuaria


def _crear_agencia(nombre='LOGINCO'):
    return Agencia.objects.get_or_create(nombre=nombre)[0]


def _crear_terminal(nombre='TIMSA'):
    return TerminalPortuaria.objects.get_or_create(nombre=nombre)[0]


def _crear_modulacion(**kwargs):
    datos = {
        'agencia': _crear_agencia(),
        'terminal_portuaria': _crear_terminal(),
        'tipo_contenedor': '40HC',
        'peso_toneladas': Decimal('18.50'),
        'contenedor': 'MSCU1234567',
    }
    datos.update(kwargs)
    return Modulacion.objects.create(**datos)


def _crear_unidad(numero_economico='ECO-001', tipo='LOCAL'):
    return Unidad.objects.create(
        numero_economico=numero_economico,
        placa='ABC-123',
        tipo=tipo,
        año=2020,
        capacidad_combustible=Decimal('200.00'),
        rendimiento_esperado=Decimal('3.00'),
    )


def _crear_operador(nombre='Juan Pérez', tipo='LOCAL'):
    return Operador.objects.create(nombre=nombre, tipo=tipo)


class ModulacionModelTests(TestCase):
    def test_folio_autogenerado(self):
        modulacion = _crear_modulacion()
        fecha = timezone.now().strftime('%Y%m%d')
        self.assertEqual(modulacion.folio, f'MOD-{fecha}-001')

    def test_folio_consecutivo_mismo_dia(self):
        _crear_modulacion(contenedor='AAAU1111111')
        segunda = _crear_modulacion(contenedor='BBBU2222222')
        fecha = timezone.now().strftime('%Y%m%d')
        self.assertEqual(segunda.folio, f'MOD-{fecha}-002')

    def test_unique_constraint_doda_contenedor(self):
        _crear_modulacion(num_doda='D-0001', contenedor='MSCU1234567')
        with self.assertRaises(Exception):
            _crear_modulacion(num_doda='D-0001', contenedor='MSCU1234567')

    def test_multiples_manuales_sin_doda_no_chocan(self):
        _crear_modulacion(num_doda='', contenedor='AAAU1111111')
        segunda = _crear_modulacion(num_doda='', contenedor='BBBU2222222')
        self.assertIsNotNone(segunda.pk)

    def test_reintenta_folio_si_colisiona_justo_antes_del_insert(self):
        """Reproduce, sin threads reales, la condición de carrera que motivó
        el fix: dos requests concurrentes a recibir_modulacion (posible con
        --workers 1 --threads 4, ver Procfile) pueden calcular el mismo
        consecutivo si el SELECT con lock de una de ellas no alcanza a ver
        todavía la fila que la otra insertó justo antes. Se fuerza esa
        condición mockeando select_for_update() para que la PRIMERA llamada
        devuelva un queryset vacío (como si el folio ya existente aún no
        fuera visible), lo que hace que el primer intento calcule '001' de
        nuevo y choque con el unique constraint de folio — la segunda llamada
        (el reintento) usa el select_for_update() real, ve el '001' ya
        confirmado y calcula '002' correctamente."""
        fecha = timezone.now().strftime('%Y%m%d')
        primera = _crear_modulacion(contenedor='AAAU1111111')
        self.assertEqual(primera.folio, f'MOD-{fecha}-001')

        original_select_for_update = QuerySet.select_for_update
        llamadas = {'n': 0}

        def select_for_update_con_stale_read_una_vez(self, *args, **kwargs):
            llamadas['n'] += 1
            qs = original_select_for_update(self, *args, **kwargs)
            return qs.none() if llamadas['n'] == 1 else qs

        with patch.object(QuerySet, 'select_for_update', select_for_update_con_stale_read_una_vez):
            segunda = _crear_modulacion(contenedor='BBBU2222222')

        self.assertEqual(segunda.folio, f'MOD-{fecha}-002')
        self.assertEqual(llamadas['n'], 2)
        self.assertEqual(Modulacion.objects.filter(folio=f'MOD-{fecha}-001').count(), 1)

    def test_folio_usa_fecha_recepcion_explicita_no_la_de_hoy(self):
        """Un reintento masivo de historial atrasado manda fecha_recepcion
        explícita (la fecha real del DODA) — el folio debe agruparse por esa
        fecha, no por el día en que corrió el reintento. Sin esto, cientos de
        DODAs viejas reenviadas de golpe quedarían todas bajo el folio de
        hoy."""
        vieja = timezone.make_aware(datetime(2025, 11, 20))
        modulacion = _crear_modulacion(fecha_recepcion=vieja)
        self.assertEqual(modulacion.folio, 'MOD-20251120-001')


class RecibirModulacionApiTests(TestCase):
    def setUp(self):
        self.url = reverse('modulacion:api_recibir')
        self.payload = {
            'agencia': 'LOGINCO',
            'terminal_portuaria': 'TIMSA',
            'tipo_contenedor': '40HC',
            'peso_toneladas': '18.50',
            'contenedor': 'mscu1234567',
            'cliente': 'Cliente Demo',
            'num_pedimento': '25 12 3456 1234567',
            'num_doda': 'D-0001',
        }

    def _post(self, payload, token='secreto-test'):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Token {token}' if token else '',
        )

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_sin_token_devuelve_401(self):
        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')
        self.assertEqual(response.status_code, 401)

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_token_incorrecto_devuelve_401(self):
        response = self._post(self.payload, token='otro-token')
        self.assertEqual(response.status_code, 401)

    @override_settings(BITACORAKASU_API_TOKEN='')
    def test_token_no_configurado_devuelve_401(self):
        response = self._post(self.payload, token='cualquiera')
        self.assertEqual(response.status_code, 401)

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_payload_incompleto_devuelve_400(self):
        incompleto = dict(self.payload)
        del incompleto['contenedor']
        response = self._post(incompleto)
        self.assertEqual(response.status_code, 400)

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_payload_valido_crea_modulacion_y_catalogos(self):
        response = self._post(self.payload)
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        modulacion = Modulacion.objects.get(pk=data['id'])
        self.assertEqual(modulacion.contenedor, 'MSCU1234567')
        self.assertEqual(modulacion.origen, 'HAL9MIL')
        self.assertEqual(modulacion.estado, 'PENDIENTE')
        self.assertEqual(modulacion.agencia.nombre, 'LOGINCO')
        self.assertEqual(modulacion.terminal_portuaria.nombre, 'TIMSA')
        self.assertEqual(modulacion.cliente.nombre, 'Cliente Demo')
        self.assertTrue(Agencia.objects.filter(nombre='LOGINCO').exists())
        self.assertTrue(Cliente.objects.filter(nombre='Cliente Demo').exists())

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_reenvio_mismo_doda_contenedor_es_idempotente(self):
        primera = self._post(self.payload)
        self.assertEqual(primera.status_code, 201)

        segunda = self._post(self.payload)
        self.assertEqual(segunda.status_code, 200)
        data = json.loads(segunda.content)
        self.assertTrue(data.get('duplicado'))
        self.assertEqual(Modulacion.objects.count(), 1)

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_reutiliza_catalogos_existentes(self):
        agencia = _crear_agencia('LOGINCO')
        self._post(self.payload)
        self.assertEqual(Agencia.objects.filter(nombre='LOGINCO').count(), 1)
        modulacion = Modulacion.objects.latest('id')
        self.assertEqual(modulacion.agencia_id, agencia.id)

    def test_get_no_permitido(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_fecha_doda_valida_se_usa_como_fecha_recepcion_y_folio(self):
        payload = dict(self.payload, fecha_doda='2025-11-20')
        response = self._post(payload)
        self.assertEqual(response.status_code, 201)

        modulacion = Modulacion.objects.get(pk=json.loads(response.content)['id'])
        self.assertEqual(modulacion.fecha_recepcion.date(), datetime(2025, 11, 20).date())
        self.assertEqual(modulacion.folio, 'MOD-20251120-001')

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_fecha_doda_ausente_usa_fecha_actual(self):
        response = self._post(self.payload)
        self.assertEqual(response.status_code, 201)

        modulacion = Modulacion.objects.get(pk=json.loads(response.content)['id'])
        self.assertEqual(modulacion.fecha_recepcion.date(), timezone.now().date())

    @override_settings(BITACORAKASU_API_TOKEN='secreto-test')
    def test_fecha_doda_invalida_se_ignora_y_no_rompe_el_alta(self):
        payload = dict(self.payload, fecha_doda='no-es-una-fecha')
        response = self._post(payload)
        self.assertEqual(response.status_code, 201)

        modulacion = Modulacion.objects.get(pk=json.loads(response.content)['id'])
        self.assertEqual(modulacion.fecha_recepcion.date(), timezone.now().date())


class ModulacionViewsAuthTests(TestCase):
    def setUp(self):
        self.modulacion = _crear_modulacion()

    def test_lista_requiere_login(self):
        response = self.client.get(reverse('modulacion:list'))
        self.assertEqual(response.status_code, 302)

    def test_detalle_requiere_login(self):
        response = self.client.get(reverse('modulacion:detail', kwargs={'pk': self.modulacion.pk}))
        self.assertEqual(response.status_code, 302)


class ModulacionListViewFilterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='tester', password='pass12345')
        self.client.login(username='tester', password='pass12345')

    def test_solo_muestra_con_doda_del_mes_y_anio_actual(self):
        con_doda_mes_actual = _crear_modulacion(num_doda='D-0001', contenedor='AAAU1111111')
        _crear_modulacion(num_doda='', contenedor='BBBU2222222')

        mes_pasado = _crear_modulacion(num_doda='D-0002', contenedor='CCCU3333333')
        fecha_vieja = timezone.now().replace(year=timezone.now().year - 1)
        Modulacion.objects.filter(pk=mes_pasado.pk).update(fecha_recepcion=fecha_vieja)

        response = self.client.get(reverse('modulacion:list'))
        modulaciones = list(response.context['modulaciones'])

        self.assertIn(con_doda_mes_actual, modulaciones)
        self.assertEqual(len(modulaciones), 1)

    def test_permite_filtrar_por_mes_y_anio_explicito(self):
        mod = _crear_modulacion(num_doda='D-0003', contenedor='DDDU4444444')
        fecha_vieja = timezone.now().replace(year=timezone.now().year - 1)
        Modulacion.objects.filter(pk=mod.pk).update(fecha_recepcion=fecha_vieja)

        response = self.client.get(reverse('modulacion:list'), {
            'mes': fecha_vieja.month,
            'anio': fecha_vieja.year,
        })
        modulaciones = list(response.context['modulaciones'])
        self.assertIn(mod, modulaciones)


class EnviarABitacoraViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='tester', password='pass12345')
        self.client.login(username='tester', password='pass12345')

        self.cliente = Cliente.objects.create(nombre='Cliente Demo')
        # El flujo es lineal: solo se envía a Bitácora desde Patio Esperanza.
        self.modulacion = _crear_modulacion(cliente=self.cliente, estado='EN_PATIO_ESPERANZA')
        # El viaje generado es foráneo (modalidad SENCILLO): operador y unidad foráneos.
        self.operador = _crear_operador(tipo='FORANEO')
        self.unidad = _crear_unidad(tipo='FORANEA')

    def test_get_muestra_formulario(self):
        url = reverse('modulacion:enviar_a_bitacora', kwargs={'pk': self.modulacion.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'operador')

    def test_listas_solo_muestran_operador_y_unidad_foraneos(self):
        operador_local = _crear_operador(nombre='Local López', tipo='LOCAL')
        unidad_local = _crear_unidad(numero_economico='ECO-LOC-1', tipo='LOCAL')

        url = reverse('modulacion:enviar_a_bitacora', kwargs={'pk': self.modulacion.pk})
        form = self.client.get(url).context['form']

        operadores = list(form.fields['operador'].queryset)
        unidades = list(form.fields['unidad'].queryset)
        self.assertIn(self.operador, operadores)
        self.assertNotIn(operador_local, operadores)
        self.assertIn(self.unidad, unidades)
        self.assertNotIn(unidad_local, unidades)

    def test_post_crea_bitacora_sencillo_foranea_y_liga_modulacion(self):
        url = reverse('modulacion:enviar_a_bitacora', kwargs={'pk': self.modulacion.pk})
        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        response = self.client.post(url, data={
            'operador': self.operador.pk,
            'unidad': self.unidad.pk,
            'fecha_carga': ahora,
            'fecha_salida': ahora,
            'destino': 'Calle Falsa 123',
            'cp_destino': '',
        })

        self.modulacion.refresh_from_db()
        self.assertEqual(self.modulacion.estado, 'ENVIADO_BITACORA')
        self.assertIsNotNone(self.modulacion.bitacora_viaje)

        bitacora = self.modulacion.bitacora_viaje
        self.assertEqual(bitacora.modalidad, 'SENCILLO')
        self.assertEqual(bitacora.contenedor, self.modulacion.contenedor)
        self.assertEqual(bitacora.peso, self.modulacion.peso_toneladas)
        self.assertEqual(bitacora.tipo_contenedor, '40')
        self.assertEqual(bitacora.cliente, self.cliente)
        self.assertEqual(bitacora.operador, self.operador)
        self.assertEqual(bitacora.unidad, self.unidad)
        self.assertRedirects(response, reverse('bitacoras:detail', kwargs={'pk': bitacora.pk}))

    def test_post_incompleto_no_crea_bitacora(self):
        url = reverse('modulacion:enviar_a_bitacora', kwargs={'pk': self.modulacion.pk})
        response = self.client.post(url, data={'operador': self.operador.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BitacoraViaje.objects.count(), 0)
        self.modulacion.refresh_from_db()
        self.assertEqual(self.modulacion.estado, 'EN_PATIO_ESPERANZA')

    def test_guardia_redirige_si_no_esta_en_patio_esperanza(self):
        otra = _crear_modulacion(estado='MODULADO', contenedor='ZZZU9999999')
        url = reverse('modulacion:enviar_a_bitacora', kwargs={'pk': otra.pk})

        get_resp = self.client.get(url)
        self.assertRedirects(get_resp, reverse('modulacion:detail', kwargs={'pk': otra.pk}))

        post_resp = self.client.post(url, data={
            'operador': self.operador.pk,
            'unidad': self.unidad.pk,
            'fecha_carga': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'fecha_salida': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'destino': 'Calle Falsa 123',
        })
        self.assertRedirects(post_resp, reverse('modulacion:detail', kwargs={'pk': otra.pk}))
        self.assertEqual(BitacoraViaje.objects.count(), 0)


class PatioEsperanzaFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='tester2', password='pass12345')
        self.client.login(username='tester2', password='pass12345')
        self.modulacion = _crear_modulacion()

    def test_enviar_a_patio_esperanza_cambia_estado_y_sella_fecha(self):
        url = reverse('modulacion:enviar_a_patio_esperanza', kwargs={'pk': self.modulacion.pk})
        self.client.post(url)
        self.modulacion.refresh_from_db()
        self.assertEqual(self.modulacion.estado, 'EN_PATIO_ESPERANZA')
        self.assertIsNotNone(self.modulacion.fecha_patio_esperanza)

        # Reenviar no re-sella la fecha original.
        fecha_original = self.modulacion.fecha_patio_esperanza
        self.modulacion.estado = 'MODULADO'
        self.modulacion.save(update_fields=['estado'])
        self.client.post(url)
        self.modulacion.refresh_from_db()
        self.assertEqual(self.modulacion.fecha_patio_esperanza, fecha_original)

    def test_retirar_de_patio_modo_kasu_redirige_a_enviar_bitacora(self):
        self.modulacion.estado = 'EN_PATIO_ESPERANZA'
        self.modulacion.save()

        url = reverse('modulacion:retirar_de_patio', kwargs={'pk': self.modulacion.pk})
        response = self.client.post(url, data={'modo': 'kasu'})
        self.assertRedirects(
            response,
            reverse('modulacion:enviar_a_bitacora', kwargs={'pk': self.modulacion.pk}),
        )

    def test_retirar_de_patio_modo_tercero(self):
        self.modulacion.estado = 'EN_PATIO_ESPERANZA'
        self.modulacion.save()

        url = reverse('modulacion:retirar_de_patio', kwargs={'pk': self.modulacion.pk})
        self.client.post(url, data={'transportista_externo': 'Transportes Beta'})

        self.modulacion.refresh_from_db()
        self.assertEqual(self.modulacion.estado, 'RETIRADO_TERCERO')
        self.assertEqual(self.modulacion.transportista_externo, 'Transportes Beta')
        self.assertIsNotNone(self.modulacion.fecha_retiro)
        self.assertIsNone(self.modulacion.bitacora_viaje)


class AsignarUnidadOperadorViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='tester-asig', password='pass12345')
        self.client.login(username='tester-asig', password='pass12345')

        self.modulacion = _crear_modulacion()
        self.unidad = _crear_unidad(numero_economico='ECO-LOC-1', tipo='LOCAL')
        self.operador_ligado = _crear_operador(nombre='Operador Ligado', tipo='LOCAL')
        self.operador_ligado.unidad_asignada = self.unidad
        self.operador_ligado.save()
        self.operador_otro = _crear_operador(nombre='Operador Otro', tipo='LOCAL')
        self.url = reverse('modulacion:asignar', kwargs={'pk': self.modulacion.pk})

    def test_requiere_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_get_muestra_formulario_y_mapa_unidad_operador(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        mapa = json.loads(response.context['unidad_operador_map'])
        self.assertEqual(mapa, {str(self.unidad.pk): self.operador_ligado.pk})

    def test_mapa_excluye_operadores_no_local_o_inactivos_o_sin_unidad(self):
        foraneo = _crear_operador(nombre='Foraneo', tipo='FORANEO')
        foraneo.unidad_asignada = _crear_unidad(numero_economico='ECO-FOR-1', tipo='FORANEA')
        foraneo.save()
        inactivo = _crear_operador(nombre='Inactivo', tipo='LOCAL')
        inactivo.unidad_asignada = _crear_unidad(numero_economico='ECO-LOC-9', tipo='LOCAL')
        inactivo.activo = False
        inactivo.save()

        response = self.client.get(self.url)
        mapa = json.loads(response.context['unidad_operador_map'])
        self.assertEqual(list(mapa.keys()), [str(self.unidad.pk)])

    def test_form_querysets_filtran_local_activos(self):
        _crear_unidad(numero_economico='ECO-FOR-2', tipo='FORANEA')
        _crear_operador(nombre='Foraneo 2', tipo='FORANEO')
        response = self.client.get(self.url)
        form = response.context['form']
        for unidad in form.fields['unidad'].queryset:
            self.assertEqual(unidad.tipo, 'LOCAL')
            self.assertTrue(unidad.activa)
        for operador in form.fields['operador'].queryset:
            self.assertEqual(operador.tipo, 'LOCAL')
            self.assertTrue(operador.activo)

    def test_post_asigna_unidad_operador_y_sella_fecha(self):
        antes = timezone.now()
        response = self.client.post(self.url, data={
            'unidad': self.unidad.pk,
            'operador': self.operador_ligado.pk,
        })
        self.assertRedirects(
            response, reverse('modulacion:detail', kwargs={'pk': self.modulacion.pk})
        )
        self.modulacion.refresh_from_db()
        self.assertEqual(self.modulacion.unidad, self.unidad)
        self.assertEqual(self.modulacion.operador, self.operador_ligado)
        self.assertIsNotNone(self.modulacion.fecha_asignacion)
        self.assertGreaterEqual(self.modulacion.fecha_asignacion, antes)

    def test_reasignar_solo_operador_conserva_unidad_y_fecha(self):
        self.client.post(self.url, data={
            'unidad': self.unidad.pk,
            'operador': self.operador_ligado.pk,
        })
        self.modulacion.refresh_from_db()
        fecha_original = self.modulacion.fecha_asignacion

        self.client.post(self.url, data={
            'unidad': self.unidad.pk,
            'operador': self.operador_otro.pk,
        })
        self.modulacion.refresh_from_db()
        self.assertEqual(self.modulacion.operador, self.operador_otro)
        self.assertEqual(self.modulacion.unidad, self.unidad)
        self.assertEqual(self.modulacion.fecha_asignacion, fecha_original)

    def test_post_sin_operador_no_asigna(self):
        response = self.client.post(self.url, data={'unidad': self.unidad.pk})
        self.assertEqual(response.status_code, 200)
        self.modulacion.refresh_from_db()
        self.assertIsNone(self.modulacion.operador_id)
        self.assertIsNone(self.modulacion.fecha_asignacion)
