from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from modulos.bitacoras.models import BitacoraViaje, Cliente
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad
from modulos.bitacoras import services_full


def _unidad(numero_economico='ECO-001', tipo='FORANEA'):
    return Unidad.objects.create(
        numero_economico=numero_economico, placa='ABC-123', tipo=tipo,
        año=2020, capacidad_combustible=Decimal('200.00'),
        rendimiento_esperado=Decimal('3.00'),
    )


def _operador(nombre='Juan Pérez', tipo='FORANEO'):
    return Operador.objects.create(nombre=nombre, tipo=tipo)


def _viaje(unidad, operador, *, modalidad='SENCILLO', completado=False,
           cliente=None, cp_destino='40810', contenedor='ABCU1234567'):
    ahora = timezone.now()
    v = BitacoraViaje(
        cliente=cliente, modalidad=modalidad, operador=operador, unidad=unidad,
        contenedor=contenedor, fecha_carga=ahora, fecha_salida=ahora,
        destino='Destino X', cp_destino=cp_destino, completado=completado,
    )
    if completado:
        # BitacoraViaje.save() calcula ingreso a partir de fecha_llegada.
        v.fecha_llegada = ahora
    if modalidad in ('FULL', 'LOCAL_FULL'):
        v.contenedor_2 = 'ZZZU9999999'
    v.save()
    return v


class CapacidadUnidadTests(TestCase):
    def setUp(self):
        self.unidad = _unidad()
        self.op = _operador()

    def test_contenedores_en_curso_cuenta_sencillo_como_uno(self):
        _viaje(self.unidad, self.op, modalidad='SENCILLO')
        self.assertEqual(services_full.contenedores_en_curso(self.unidad), 1)

    def test_contenedores_en_curso_cuenta_full_como_dos(self):
        _viaje(self.unidad, self.op, modalidad='FULL')
        self.assertEqual(services_full.contenedores_en_curso(self.unidad), 2)

    def test_contenedores_en_curso_ignora_completados(self):
        _viaje(self.unidad, self.op, modalidad='SENCILLO', completado=True)
        self.assertEqual(services_full.contenedores_en_curso(self.unidad), 0)

    def test_contenedores_en_curso_respeta_excluir_pk(self):
        v = _viaje(self.unidad, self.op, modalidad='FULL')
        self.assertEqual(
            services_full.contenedores_en_curso(self.unidad, excluir_pk=v.pk), 0)

    def test_unidad_bloqueada_con_full(self):
        _viaje(self.unidad, self.op, modalidad='FULL')
        self.assertTrue(services_full.unidad_bloqueada(self.unidad))

    def test_unidad_bloqueada_con_dos_sencillos(self):
        _viaje(self.unidad, self.op, contenedor='AAAU1111111')
        _viaje(self.unidad, _operador('Otro'), contenedor='BBBU2222222')
        self.assertTrue(services_full.unidad_bloqueada(self.unidad))

    def test_unidad_no_bloqueada_con_un_sencillo(self):
        _viaje(self.unidad, self.op, modalidad='SENCILLO')
        self.assertFalse(services_full.unidad_bloqueada(self.unidad))

    def test_unidades_bloqueadas_ids(self):
        libre = _unidad('ECO-LIBRE')
        _viaje(libre, self.op, modalidad='SENCILLO')
        _viaje(self.unidad, self.op, modalidad='FULL')
        ids = services_full.unidades_bloqueadas_ids()
        self.assertIn(self.unidad.pk, ids)
        self.assertNotIn(libre.pk, ids)

    def test_unidades_bloqueadas_ids_respeta_excluir_pk(self):
        v = _viaje(self.unidad, self.op, modalidad='FULL')
        self.assertEqual(services_full.unidades_bloqueadas_ids(excluir_pk=v.pk), set())


class SencilloApareableTests(TestCase):
    def setUp(self):
        self.unidad = _unidad()
        self.op = _operador()

    def test_devuelve_sencillo_mismo_operador_en_curso(self):
        v = _viaje(self.unidad, self.op, modalidad='SENCILLO')
        self.assertEqual(
            services_full.sencillo_apareable(self.unidad, self.op), v)

    def test_none_si_operador_distinto(self):
        _viaje(self.unidad, self.op, modalidad='SENCILLO')
        self.assertIsNone(
            services_full.sencillo_apareable(self.unidad, _operador('Otro')))

    def test_none_si_completado(self):
        _viaje(self.unidad, self.op, modalidad='SENCILLO', completado=True)
        self.assertIsNone(services_full.sencillo_apareable(self.unidad, self.op))

    def test_none_si_es_full(self):
        _viaje(self.unidad, self.op, modalidad='FULL')
        self.assertIsNone(services_full.sencillo_apareable(self.unidad, self.op))

    def test_respeta_excluir_pk(self):
        v = _viaje(self.unidad, self.op, modalidad='SENCILLO')
        self.assertIsNone(
            services_full.sencillo_apareable(self.unidad, self.op, excluir_pk=v.pk))


class EvaluarFusionTests(TestCase):
    def setUp(self):
        self.unidad = _unidad()
        self.op = _operador()
        self.cli_a = Cliente.objects.create(nombre='Cliente A')
        self.cli_b = Cliente.objects.create(nombre='Cliente B')

    def test_ninguna_si_unidad_libre(self):
        res = services_full.evaluar_fusion(self.unidad, self.op, self.cli_a, '40810')
        self.assertEqual(res['accion'], 'ninguna')

    def test_ninguna_si_faltan_datos(self):
        res = services_full.evaluar_fusion(None, None, None, '')
        self.assertEqual(res['accion'], 'ninguna')

    def test_ofrecer_full_directo_mismo_cliente_y_cp(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810')
        res = services_full.evaluar_fusion(self.unidad, self.op, self.cli_a, '40810')
        self.assertEqual(res['accion'], 'ofrecer_full')
        self.assertEqual(res['tipo_full'], 'directo')

    def test_ofrecer_full_reparto_si_cambia_cliente(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810')
        res = services_full.evaluar_fusion(self.unidad, self.op, self.cli_b, '40810')
        self.assertEqual(res['tipo_full'], 'reparto')

    def test_ofrecer_full_reparto_si_cambia_cp(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810')
        res = services_full.evaluar_fusion(self.unidad, self.op, self.cli_a, '62520')
        self.assertEqual(res['tipo_full'], 'reparto')

    def test_bloqueo_si_operador_distinto(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a)
        res = services_full.evaluar_fusion(
            self.unidad, _operador('Pedro'), self.cli_a, '40810')
        self.assertEqual(res['accion'], 'bloqueo')
        self.assertIn('sencillo', res['mensaje'].lower())

    def test_bloqueo_si_unidad_llena_con_full(self):
        _viaje(self.unidad, self.op, modalidad='FULL')
        res = services_full.evaluar_fusion(
            self.unidad, _operador('Pedro'), self.cli_a, '40810')
        self.assertEqual(res['accion'], 'bloqueo')
        self.assertIn('2 contenedores', res['mensaje'])


class FusionarEnFullTests(TestCase):
    def setUp(self):
        self.unidad = _unidad()
        self.op = _operador()
        self.cli_a = Cliente.objects.create(nombre='Cliente A')
        self.cli_b = Cliente.objects.create(nombre='Cliente B')

    def _datos_segundo(self, **over):
        base = {
            'contenedor': 'bbbu2222222',
            'peso': Decimal('12.00'),
            'sellos': 'S-99',
            'cliente': self.cli_b,
            'cp_destino': '62520',
        }
        base.update(over)
        return base

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_fusion_directa_no_llena_contenedor_2_cliente(self, _maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
                   contenedor='AAAU1111111')
        full = services_full.fusionar_en_full(
            s, self._datos_segundo(cliente=self.cli_a, cp_destino='40810'),
            tipo_full='directo')
        self.assertEqual(full.modalidad, 'FULL')
        self.assertEqual(full.contenedor_2, 'BBBU2222222')
        self.assertEqual(full.peso_2, Decimal('12.00'))
        self.assertEqual(full.sellos_2, 'S-99')
        self.assertFalse(full.reparto)
        self.assertIsNone(full.cliente_2)
        self.assertEqual(full.cp_destino_2, '')

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_fusion_con_reparto_llena_cliente_2_y_cp_2(self, _maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
                   contenedor='AAAU1111111')
        full = services_full.fusionar_en_full(
            s, self._datos_segundo(), tipo_full='reparto')
        self.assertTrue(full.reparto)
        self.assertEqual(full.cliente_2, self.cli_b)
        self.assertEqual(full.cp_destino_2, '62520')

    @patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY': 'x'})
    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_fusion_reparto_recalcula_distancia(self, maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, contenedor='AAAU1111111')
        services_full.fusionar_en_full(s, self._datos_segundo(), tipo_full='reparto')
        maps.assert_called_once()

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_fusion_persiste_en_bd(self, _maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, contenedor='AAAU1111111')
        services_full.fusionar_en_full(s, self._datos_segundo(), tipo_full='reparto')
        s.refresh_from_db()
        self.assertEqual(s.modalidad, 'FULL')
        self.assertEqual(s.contenedor_2, 'BBBU2222222')


class VerificarFullEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='t', password='p')
        self.client.login(username='t', password='p')
        self.url = reverse('bitacoras:verificar_full')
        self.unidad = _unidad()
        self.op = _operador()
        self.cli_a = Cliente.objects.create(nombre='Cliente A')
        self.cli_b = Cliente.objects.create(nombre='Cliente B')

    def test_ninguna_si_unidad_libre(self):
        r = self.client.get(self.url, {
            'unidad': self.unidad.pk, 'operador': self.op.pk,
            'cliente': self.cli_a.pk, 'cp_destino': '40810',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['accion'], 'ninguna')

    def test_ofrecer_full_reparto(self):
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
               contenedor='AAAU1111111')
        r = self.client.get(self.url, {
            'unidad': self.unidad.pk, 'operador': self.op.pk,
            'cliente': self.cli_b.pk, 'cp_destino': '62520',
        })
        data = r.json()
        self.assertEqual(data['accion'], 'ofrecer_full')
        self.assertEqual(data['tipo_full'], 'reparto')
        self.assertEqual(data['sencillo']['contenedor'], 'AAAU1111111')
        self.assertEqual(data['sencillo']['cliente'], 'Cliente A')
        self.assertEqual(data['nuevo']['cliente'], 'Cliente B')

    def test_bloqueo_operador_distinto(self):
        _viaje(self.unidad, _operador('Pedro'), cliente=self.cli_a,
               contenedor='AAAU1111111')
        r = self.client.get(self.url, {
            'unidad': self.unidad.pk, 'operador': self.op.pk,
            'cliente': self.cli_a.pk, 'cp_destino': '40810',
        })
        data = r.json()
        self.assertEqual(data['accion'], 'bloqueo')
        self.assertIn('Pedro', data['mensaje'])

    def test_ninguna_si_faltan_params(self):
        r = self.client.get(self.url, {'unidad': self.unidad.pk})
        self.assertEqual(r.json()['accion'], 'ninguna')

    def test_requiere_login(self):
        self.client.logout()
        r = self.client.get(self.url, {'unidad': self.unidad.pk, 'operador': self.op.pk})
        self.assertEqual(r.status_code, 302)


class BitacoraViajeFormFusionTests(TestCase):
    def setUp(self):
        self.unidad = _unidad()
        self.op = _operador()
        self.cli_a = Cliente.objects.create(nombre='Cliente A')

    def _post(self, **over):
        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        data = {
            'cliente': self.cli_a.pk, 'modalidad': 'SENCILLO',
            'operador': self.op.pk, 'unidad': self.unidad.pk,
            'fecha_carga': ahora, 'fecha_salida': ahora,
            'contenedor': 'AAAU1111111', 'tipo_contenedor': '40',
            'cp_origen': '40812', 'cp_destino': '40810', 'destino': 'X',
        }
        data.update(over)
        return data

    def test_sin_sencillo_previo_es_valido_y_fusion_result_ninguna(self):
        from modulos.bitacoras.forms import BitacoraViajeForm
        form = BitacoraViajeForm(data=self._post())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.fusion_result['accion'], 'ninguna')

    def test_con_sencillo_apareable_sin_confirmar_es_invalido(self):
        from modulos.bitacoras.forms import BitacoraViajeForm
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
               contenedor='BBBU2222222')
        form = BitacoraViajeForm(data=self._post(contenedor='CCCU3333333'))
        self.assertFalse(form.is_valid())

    def test_con_sencillo_apareable_y_confirmar_full_es_valido(self):
        from modulos.bitacoras.forms import BitacoraViajeForm
        _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
               contenedor='BBBU2222222')
        form = BitacoraViajeForm(
            data=self._post(contenedor='CCCU3333333', confirmar_full='1'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.fusion_result['accion'], 'ofrecer_full')

    def test_operador_distinto_es_invalido_incluso_con_confirmar(self):
        from modulos.bitacoras.forms import BitacoraViajeForm
        _viaje(self.unidad, _operador('Pedro'), cliente=self.cli_a,
               contenedor='BBBU2222222')
        form = BitacoraViajeForm(data=self._post(
            contenedor='CCCU3333333', confirmar_full='1'))
        self.assertFalse(form.is_valid())

    def test_unidad_bloqueada_fuera_del_queryset(self):
        from modulos.bitacoras.forms import BitacoraViajeForm
        _viaje(self.unidad, self.op, modalidad='FULL', contenedor='BBBU2222222')
        form = BitacoraViajeForm()
        self.assertNotIn(self.unidad, form.fields['unidad'].queryset)


class BitacoraCreateFusionViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='t', password='p')
        self.client.login(username='t', password='p')
        self.url = reverse('bitacoras:create')
        self.unidad = _unidad()
        self.op = _operador()
        self.cli_a = Cliente.objects.create(nombre='Cliente A')
        self.cli_b = Cliente.objects.create(nombre='Cliente B')

    def _post(self, **over):
        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        data = {
            'cliente': self.cli_a.pk, 'modalidad': 'SENCILLO',
            'operador': self.op.pk, 'unidad': self.unidad.pk,
            'fecha_carga': ahora, 'fecha_salida': ahora,
            'contenedor': 'CCCU3333333', 'tipo_contenedor': '40',
            'cp_origen': '40812', 'cp_destino': '62520', 'destino': 'Y',
        }
        data.update(over)
        return data

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_sin_confirmar_no_fusiona_y_responde_200(self, _maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
                   contenedor='BBBU2222222')
        r = self.client.post(self.url, data=self._post())
        self.assertEqual(r.status_code, 200)  # re-render con error
        s.refresh_from_db()
        self.assertEqual(s.modalidad, 'SENCILLO')
        self.assertEqual(BitacoraViaje.objects.count(), 1)

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_con_confirmar_full_fusiona_y_no_crea_registro(self, _maps):
        s = _viaje(self.unidad, self.op, cliente=self.cli_a, cp_destino='40810',
                   contenedor='BBBU2222222')
        r = self.client.post(self.url, data=self._post(confirmar_full='1'))
        self.assertRedirects(r, reverse('bitacoras:detail', kwargs={'pk': s.pk}))
        s.refresh_from_db()
        self.assertEqual(s.modalidad, 'FULL')
        self.assertEqual(s.contenedor_2, 'CCCU3333333')
        self.assertTrue(s.reparto)
        self.assertEqual(s.cliente_2, self.cli_a)  # cliente del 2º contenedor
        self.assertEqual(s.cp_destino_2, '62520')
        self.assertEqual(BitacoraViaje.objects.count(), 1)

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_unidad_libre_crea_sencillo_normal(self, _maps):
        r = self.client.post(self.url, data=self._post())
        self.assertEqual(BitacoraViaje.objects.count(), 1)
        self.assertEqual(BitacoraViaje.objects.first().modalidad, 'SENCILLO')


class BitacoraUpdateFusionViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='t', password='p')
        self.client.login(username='t', password='p')
        self.unidad = _unidad()
        self.op = _operador()
        self.op2 = _operador('Pedro')
        self.cli_a = Cliente.objects.create(nombre='Cliente A')

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_editar_operador_para_aparear_fusiona_y_borra_editado(self, _maps):
        existente = _viaje(self.unidad, self.op, cliente=self.cli_a,
                           cp_destino='40810', contenedor='AAAU1111111')
        editado = _viaje(self.unidad, self.op2, cliente=self.cli_a,
                         cp_destino='40810', contenedor='BBBU2222222')
        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        url = reverse('bitacoras:update', kwargs={'pk': editado.pk})
        r = self.client.post(url, data={
            'cliente': self.cli_a.pk, 'modalidad': 'SENCILLO',
            'operador': self.op.pk, 'unidad': self.unidad.pk,
            'fecha_carga': ahora, 'fecha_salida': ahora,
            'contenedor': 'BBBU2222222', 'tipo_contenedor': '40',
            'cp_origen': '40812', 'cp_destino': '40810', 'destino': 'Z',
            'confirmar_full': '1',
        })
        self.assertRedirects(r, reverse('bitacoras:detail', kwargs={'pk': existente.pk}))
        existente.refresh_from_db()
        self.assertEqual(existente.modalidad, 'FULL')
        self.assertEqual(existente.contenedor_2, 'BBBU2222222')
        self.assertFalse(BitacoraViaje.objects.filter(pk=editado.pk).exists())

    @patch('modulos.bitacoras.models.BitacoraViaje.calcular_distancia_google')
    def test_editado_con_vacio_asociado_reasigna_al_full_y_no_revienta(self, _maps):
        from modulos.vacios.models import Vacio

        existente = _viaje(self.unidad, self.op, cliente=self.cli_a,
                           cp_destino='40810', contenedor='AAAU1111111')
        editado = _viaje(self.unidad, self.op2, cliente=self.cli_a,
                         cp_destino='40810', contenedor='BBBU2222222')
        # El viaje editado ya registró la entrega -> la señal le crea un Vacío
        # (PROTECT), que hacía reventar el borrado con ProtectedError.
        editado.fecha_hora_entrega = timezone.now()
        editado.save()
        self.assertEqual(Vacio.objects.filter(bitacora_viaje=editado).count(), 1)

        ahora = timezone.now().strftime('%Y-%m-%dT%H:%M')
        url = reverse('bitacoras:update', kwargs={'pk': editado.pk})
        r = self.client.post(url, data={
            'cliente': self.cli_a.pk, 'modalidad': 'SENCILLO',
            'operador': self.op.pk, 'unidad': self.unidad.pk,
            'fecha_carga': ahora, 'fecha_salida': ahora,
            'fecha_hora_entrega': ahora,
            'contenedor': 'BBBU2222222', 'tipo_contenedor': '40',
            'cp_origen': '40812', 'cp_destino': '40810', 'destino': 'Z',
            'confirmar_full': '1',
        })
        self.assertRedirects(r, reverse('bitacoras:detail', kwargs={'pk': existente.pk}))
        existente.refresh_from_db()
        self.assertEqual(existente.modalidad, 'FULL')
        self.assertEqual(existente.contenedor_2, 'BBBU2222222')
        self.assertFalse(BitacoraViaje.objects.filter(pk=editado.pk).exists())
        # El Vacío se conserva, ahora colgado del FULL como contenedor 2.
        vacio = Vacio.objects.get()
        self.assertEqual(vacio.bitacora_viaje_id, existente.pk)
        self.assertEqual(vacio.numero_contenedor, '2')
        self.assertIsNotNone(existente.fecha_hora_entrega_2)


class BitacoraFormModalMarkupTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='t', password='p')
        self.client.login(username='t', password='p')

    def test_form_incluye_modal_y_url_endpoint(self):
        r = self.client.get(reverse('bitacoras:create'))
        self.assertContains(r, 'id="modal-generar-full"')
        self.assertContains(r, '/bitacoras/ajax/verificar-full/')
