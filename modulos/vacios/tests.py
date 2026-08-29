import itertools
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from modulos.bitacoras.models import BitacoraViaje, Cliente
from modulos.modulacion.models import Agencia, Modulacion, TerminalPortuaria
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad
from modulos.vacios.forms import ReasignarOperadorVacioForm
from modulos.vacios.models import CambioOperadorVacio, Naviera, RetrasoVacio, Vacio


def _cliente(nombre='ACME'):
    return Cliente.objects.get_or_create(nombre=nombre)[0]


def _unidad(numero_economico='ECO-001', tipo='LOCAL'):
    return Unidad.objects.create(
        numero_economico=numero_economico,
        placa=f'P-{numero_economico}',
        tipo=tipo,
        año=2020,
        capacidad_combustible=Decimal('200.00'),
        rendimiento_esperado=Decimal('3.00'),
    )


def _operador(nombre='Juan Pérez', tipo='LOCAL', unidad=None):
    return Operador.objects.create(nombre=nombre, tipo=tipo, unidad_asignada=unidad)


_eco_seq = itertools.count(1)


def _bitacora(**kwargs):
    """BitacoraViaje mínima y válida. Sin fechas de entrega por defecto."""
    ahora = timezone.now()
    n = next(_eco_seq)
    datos = dict(
        cliente=_cliente(),
        operador=kwargs.pop('operador', None) or _operador(f'Op Bitacora {n}', unidad=_unidad(f'ECO-BIT-{n}a')),
        unidad=kwargs.pop('unidad', None) or _unidad(f'ECO-BIT-{n}b'),
        modalidad='SENCILLO',
        contenedor='MSCU1111111',
        fecha_carga=ahora,
        fecha_salida=ahora,
        destino='Bodega 5, Zona Industrial',
    )
    datos.update(kwargs)
    return BitacoraViaje.objects.create(**datos)


class VacioModelTests(TestCase):
    def test_folio_autogenerado(self):
        v = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='MSCU1111111',
            fecha_entrega_cliente=timezone.now(),
        )
        fecha = timezone.localtime(v.fecha_entrega_cliente).strftime('%Y%m%d')
        self.assertEqual(v.folio, f'VAC-{fecha}-001')

    def test_folio_consecutivo_mismo_dia(self):
        ahora = timezone.now()
        v1 = Vacio.objects.create(bitacora_viaje=_bitacora(), contenedor='A', fecha_entrega_cliente=ahora)
        v2 = Vacio.objects.create(bitacora_viaje=_bitacora(), contenedor='B', fecha_entrega_cliente=ahora)
        self.assertTrue(v1.folio.endswith('-001'))
        self.assertTrue(v2.folio.endswith('-002'))

    def test_unique_constraint_bitacora_contenedor(self):
        b = _bitacora()
        Vacio.objects.create(bitacora_viaje=b, numero_contenedor='1', contenedor='A', fecha_entrega_cliente=timezone.now())
        with self.assertRaises(Exception):
            Vacio.objects.create(bitacora_viaje=b, numero_contenedor='1', contenedor='A', fecha_entrega_cliente=timezone.now())

    def test_agencia_email_contacto(self):
        a = Agencia.objects.create(nombre='LOGINCO', email_contacto='avisos@loginco.mx')
        self.assertEqual(Agencia.objects.get(pk=a.pk).email_contacto, 'avisos@loginco.mx')


class SignalCreacionTests(TestCase):
    def test_crea_un_vacio_al_registrar_entrega(self):
        b = _bitacora()
        self.assertEqual(Vacio.objects.count(), 0)
        b.fecha_hora_entrega = timezone.now()
        b.save()
        self.assertEqual(Vacio.objects.count(), 1)
        v = Vacio.objects.get()
        self.assertEqual(v.numero_contenedor, '1')
        self.assertEqual(v.contenedor, b.contenedor)
        self.assertEqual(v.cliente, b.cliente)
        self.assertEqual(v.estado, 'POR_VACIAR')

    def test_full_con_dos_entregas_crea_dos_vacios(self):
        b = _bitacora(
            modalidad='FULL',
            contenedor='AAAA1111111',
            contenedor_2='BBBB2222222',
            peso_2=Decimal('10.00'),
        )
        b.fecha_hora_entrega = timezone.now()
        b.fecha_hora_entrega_2 = timezone.now()
        b.save()
        self.assertEqual(Vacio.objects.count(), 2)
        self.assertEqual(
            set(Vacio.objects.values_list('numero_contenedor', flat=True)),
            {'1', '2'},
        )
        v2 = Vacio.objects.get(numero_contenedor='2')
        self.assertEqual(v2.contenedor, 'BBBB2222222')

    def test_es_idempotente(self):
        b = _bitacora()
        b.fecha_hora_entrega = timezone.now()
        b.save()
        b.save()
        b.observaciones = 'otra edición'
        b.save()
        self.assertEqual(Vacio.objects.count(), 1)

    def test_sin_fecha_entrega_no_crea_vacio(self):
        _bitacora()
        self.assertEqual(Vacio.objects.count(), 0)

    def test_autollena_agencia_desde_modulacion(self):
        agencia = Agencia.objects.create(nombre='LOGINCO', email_contacto='a@b.mx')
        terminal = TerminalPortuaria.objects.create(nombre='TIMSA')
        b = _bitacora()
        Modulacion.objects.create(
            agencia=agencia,
            terminal_portuaria=terminal,
            tipo_contenedor='40HC',
            peso_toneladas=Decimal('18.00'),
            contenedor='MSCU1111111',
            bitacora_viaje=b,
        )
        b.fecha_hora_entrega = timezone.now()
        b.save()
        self.assertEqual(Vacio.objects.get().agencia, agencia)


from modulos.vacios.services import operadores_libres


class VistasLecturaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('tester', password='x')
        self.client.force_login(self.user)
        self.vacio = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='MSCU1111111',
            fecha_entrega_cliente=timezone.now(),
        )

    def test_dashboard_200(self):
        resp = self.client.get(reverse('vacios:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Vacíos')

    def test_lista_200_y_muestra_folio(self):
        resp = self.client.get(reverse('vacios:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.vacio.folio)

    def test_lista_filtra_por_mes_de_entrega(self):
        viejo = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='OLD',
            fecha_entrega_cliente=timezone.now() - timedelta(days=90),
        )
        resp = self.client.get(reverse('vacios:list'))  # mes/año actual por defecto
        self.assertContains(resp, self.vacio.folio)
        self.assertNotContains(resp, viejo.folio)

    def test_detalle_200(self):
        resp = self.client.get(reverse('vacios:detail', kwargs={'pk': self.vacio.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.vacio.contenedor)

    def test_requiere_login(self):
        self.client.logout()
        resp = self.client.get(reverse('vacios:list'))
        self.assertEqual(resp.status_code, 302)


class OperadoresLibresTests(TestCase):
    def test_incluye_local_activo_sin_ocupacion(self):
        op = _operador('Libre')
        self.assertIn(op, list(operadores_libres()))

    def test_excluye_no_local_y_inactivo(self):
        foraneo = _operador('Foráneo', tipo='FORANEO')
        inactivo = _operador('Inactivo')
        inactivo.activo = False
        inactivo.save()
        libres = list(operadores_libres())
        self.assertNotIn(foraneo, libres)
        self.assertNotIn(inactivo, libres)

    def test_excluye_ocupado_en_modulacion_activa(self):
        op = _operador('EnModulacion')
        Modulacion.objects.create(
            agencia=Agencia.objects.create(nombre='LOGINCO'),
            terminal_portuaria=TerminalPortuaria.objects.create(nombre='TIMSA'),
            tipo_contenedor='40HC',
            peso_toneladas=Decimal('18.00'),
            contenedor='X',
            operador=op,
            estado='EN_PATIO_ESPERANZA',
        )
        self.assertNotIn(op, list(operadores_libres()))

    def test_excluye_ocupado_en_vacio_asignado(self):
        op = _operador('EnVacio')
        Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='A',
            fecha_entrega_cliente=timezone.now(),
            estado='ASIGNADO',
            operador=op,
        )
        self.assertNotIn(op, list(operadores_libres()))

    def test_excluye_ocupado_en_bitacora_en_curso(self):
        op = _operador('EnBitacora', unidad=_unidad('ECO-X'))
        _bitacora(operador=op, unidad=op.unidad_asignada)  # completado=False por defecto
        self.assertNotIn(op, list(operadores_libres()))


class TransicionesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('t', password='x')
        self.client.force_login(self.user)
        self.unidad = _unidad('ECO-100')
        self.operador = _operador('Op Libre', unidad=self.unidad)
        self.vacio = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='C1',
            fecha_entrega_cliente=timezone.now(),
        )

    def _post(self, name, **data):
        return self.client.post(reverse(name, kwargs={'pk': self.vacio.pk}), data)

    def test_retorno_a_patio(self):
        resp = self._post('vacios:registrar_retorno_patio')
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.estado, 'EN_PATIO_ESPERANZA')
        self.assertIsNotNone(self.vacio.fecha_retorno_patio)
        self.assertEqual(resp.status_code, 302)

    def test_retorno_a_patio_rechazado_si_no_por_vaciar(self):
        self.vacio.estado = 'ASIGNADO'
        self.vacio.save()
        self._post('vacios:registrar_retorno_patio')
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.estado, 'ASIGNADO')

    def test_asignar_unidad_operador(self):
        self.vacio.estado = 'EN_PATIO_ESPERANZA'
        self.vacio.save()
        self._post('vacios:asignar', unidad=self.unidad.pk, operador=self.operador.pk)
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.estado, 'ASIGNADO')
        self.assertEqual(self.vacio.operador, self.operador)
        self.assertIsNotNone(self.vacio.fecha_asignacion)

    def test_fecha_asignacion_no_se_resella(self):
        self.vacio.estado = 'EN_PATIO_ESPERANZA'
        self.vacio.save()
        self._post('vacios:asignar', unidad=self.unidad.pk, operador=self.operador.pk)
        self.vacio.refresh_from_db()
        primera = self.vacio.fecha_asignacion
        otra = _operador('Op 2', unidad=_unidad('ECO-200'))
        self.client.post(
            reverse('vacios:reasignar_operador', kwargs={'pk': self.vacio.pk}),
            {'unidad_entrante': otra.unidad_asignada.pk, 'operador_entrante': otra.pk, 'causa': 'NO_CONFIRMA'},
        )
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.fecha_asignacion, primera)

    def test_reasignar_crea_historial(self):
        self.vacio.estado = 'ASIGNADO'
        self.vacio.unidad = self.unidad
        self.vacio.operador = self.operador
        self.vacio.save()
        nueva_unidad = _unidad('ECO-300')
        nuevo_operador = _operador('Op Nuevo', unidad=nueva_unidad)
        self.client.post(
            reverse('vacios:reasignar_operador', kwargs={'pk': self.vacio.pk}),
            {'unidad_entrante': nueva_unidad.pk, 'operador_entrante': nuevo_operador.pk,
             'causa': 'SE_NIEGA', 'motivo': 'no quiso'},
        )
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.operador, nuevo_operador)
        self.assertEqual(self.vacio.unidad, nueva_unidad)
        cambio = CambioOperadorVacio.objects.get()
        self.assertEqual(cambio.operador_saliente, self.operador)
        self.assertEqual(cambio.operador_entrante, nuevo_operador)
        self.assertEqual(cambio.causa, 'SE_NIEGA')

    def test_salida_y_entrega_a_naviera(self):
        self.vacio.estado = 'ASIGNADO'
        self.vacio.save()
        self._post('vacios:registrar_salida_naviera')
        self.vacio.refresh_from_db()
        self.assertIsNotNone(self.vacio.fecha_salida_naviera)
        self.assertEqual(self.vacio.estado, 'ASIGNADO')
        self._post('vacios:registrar_entrega_naviera')
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.estado, 'ENTREGADO_NAVIERA')
        self.assertIsNotNone(self.vacio.fecha_entrega_naviera)

    def test_editar_datos_naviera_y_compromiso(self):
        naviera = Naviera.objects.create(nombre='MSC')
        resp = self.client.post(
            reverse('vacios:update', kwargs={'pk': self.vacio.pk}),
            {'naviera': naviera.pk, 'fecha_compromiso_naviera': '2026-09-15T10:00', 'observaciones': 'ok'},
        )
        self.assertEqual(resp.status_code, 302)
        self.vacio.refresh_from_db()
        self.assertEqual(self.vacio.naviera, naviera)


class ReasignarFallbackTests(TestCase):
    """Fix round 1: fallback explícito de operador_entrante + aviso en la UI."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('rf', password='x')
        self.client.force_login(self.user)
        self.vacio = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='RF1',
            fecha_entrega_cliente=timezone.now(),
            estado='ASIGNADO',
        )

    def _ocupa_todos_los_locales(self):
        """Deja sin operadores LOCAL libres: un Vacío ASIGNADO por cada uno."""
        for op in list(operadores_libres()):
            Vacio.objects.create(
                bitacora_viaje=_bitacora(),
                contenedor=f'OCU-{op.pk}',
                fecha_entrega_cliente=timezone.now(),
                estado='ASIGNADO',
                operador=op,
            )

    def test_flag_false_y_queryset_solo_libres_cuando_hay_operador_libre(self):
        libre = _operador('Operador Libre RF')
        form = ReasignarOperadorVacioForm(vacio=self.vacio)
        self.assertFalse(form.sin_operadores_libres)
        qs = form.fields['operador_entrante'].queryset
        self.assertIn(libre, list(qs))
        self.assertEqual(set(qs), set(operadores_libres()))

    def test_flag_true_y_fallback_a_todos_los_locales_activos(self):
        _operador('Operador Libre RF')
        self._ocupa_todos_los_locales()
        self.assertFalse(operadores_libres().exists())
        form = ReasignarOperadorVacioForm(vacio=self.vacio)
        self.assertTrue(form.sin_operadores_libres)
        self.assertEqual(
            set(form.fields['operador_entrante'].queryset),
            set(Operador.objects.filter(tipo='LOCAL', activo=True)),
        )

    def test_detalle_muestra_aviso_ambar_sin_operadores_libres(self):
        self._ocupa_todos_los_locales()
        self.assertFalse(operadores_libres().exists())
        resp = self.client.get(reverse('vacios:detail', kwargs={'pk': self.vacio.pk}))
        self.assertContains(resp, 'No hay operadores libres.')

    def test_detalle_sin_aviso_cuando_hay_operador_libre(self):
        _operador('Operador Libre RF')
        resp = self.client.get(reverse('vacios:detail', kwargs={'pk': self.vacio.pk}))
        self.assertNotContains(resp, 'No hay operadores libres.')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RetrasoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('t', password='x')
        self.client.force_login(self.user)
        self.agencia = Agencia.objects.create(nombre='LOGINCO', email_contacto='avisos@loginco.mx')
        self.vacio = Vacio.objects.create(
            bitacora_viaje=_bitacora(),
            contenedor='C1',
            fecha_entrega_cliente=timezone.now(),
            agencia=self.agencia,
        )

    def test_registrar_retraso_crea_evento_y_notifica(self):
        mail.outbox = []
        resp = self.client.post(
            reverse('vacios:registrar_retraso', kwargs={'pk': self.vacio.pk}),
            {'tipo': 'MANIOBRA', 'motivo': 'grúa descompuesta', 'fecha_estimada_nueva': '2026-09-20'},
        )
        self.assertEqual(resp.status_code, 302)
        self.vacio.refresh_from_db()
        self.assertTrue(self.vacio.tiene_retraso)
        retraso = RetrasoVacio.objects.get()
        self.assertEqual(retraso.tipo, 'MANIOBRA')
        self.assertTrue(retraso.notificado_agencia)
        self.assertIsNotNone(retraso.fecha_notificacion)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('avisos@loginco.mx', mail.outbox[0].to)

    def test_sin_email_agencia_guarda_pero_no_notifica(self):
        self.agencia.email_contacto = ''
        self.agencia.save()
        mail.outbox = []
        self.client.post(
            reverse('vacios:registrar_retraso', kwargs={'pk': self.vacio.pk}),
            {'tipo': 'RETORNO', 'motivo': 'tráfico', 'fecha_estimada_nueva': '2026-09-21'},
        )
        retraso = RetrasoVacio.objects.get()
        self.assertFalse(retraso.notificado_agencia)
        self.assertEqual(len(mail.outbox), 0)

    def test_reenviar_aviso(self):
        retraso = RetrasoVacio.objects.create(
            vacio=self.vacio, tipo='MANIOBRA', motivo='x',
            fecha_estimada_nueva=date(2026, 9, 20),
        )
        mail.outbox = []
        resp = self.client.post(reverse('vacios:reenviar_aviso_retraso', kwargs={'pk': self.vacio.pk, 'rid': retraso.pk}))
        self.assertEqual(resp.status_code, 302)
        retraso.refresh_from_db()
        self.assertTrue(retraso.notificado_agencia)
        self.assertEqual(len(mail.outbox), 1)

    def test_notificar_retraso_agencia_devuelve_bool(self):
        from modulos.vacios.notificaciones import notificar_retraso_agencia
        retraso = RetrasoVacio.objects.create(
            vacio=self.vacio, tipo='RETORNO', motivo='x',
            fecha_estimada_nueva=date(2026, 9, 22),
        )
        self.assertIs(notificar_retraso_agencia(retraso), True)
        self.vacio.agencia = None
        self.vacio.save()
        retraso2 = RetrasoVacio.objects.create(
            vacio=self.vacio, tipo='RETORNO', motivo='y',
            fecha_estimada_nueva=date(2026, 9, 23),
        )
        self.assertIs(notificar_retraso_agencia(retraso2), False)
