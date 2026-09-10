from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from modulos.modulacion.models import (
    Agencia, Modulacion, SeguimientoModulacion, TerminalPortuaria,
    TransicionInvalida, TRANSICIONES_MODULACION,
)
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad


def _modulacion(estado='PENDIENTE', **kw):
    kw.setdefault('contenedor', 'ABCU1234567')
    kw.setdefault('num_doda', f"DODA-{kw['contenedor']}")
    return Modulacion.objects.create(
        agencia=Agencia.objects.get_or_create(nombre='LOGINCO')[0],
        terminal_portuaria=TerminalPortuaria.objects.get_or_create(nombre='LCTPC')[0],
        tipo_contenedor='40HC', peso_toneladas=Decimal('18.5'),
        estado=estado, **kw,
    )


class TransicionarTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')

    def test_transicion_valida_cambia_estado_y_deja_seguimiento(self):
        m = _modulacion(estado='ASIGNADO')
        m.transicionar('INGRESADO', usuario=self.user, nota='ok')
        m.refresh_from_db()
        self.assertEqual(m.estado, 'INGRESADO')
        seg = SeguimientoModulacion.objects.get(modulacion=m)
        self.assertEqual(seg.estado, 'INGRESADO')
        self.assertEqual(seg.usuario, self.user)
        self.assertEqual(seg.nota, 'ok')

    def test_transicion_invalida_no_cambia_nada(self):
        m = _modulacion(estado='ASIGNADO')
        with self.assertRaises(TransicionInvalida):
            m.transicionar('EN_PATIO_ESPERANZA')
        m.refresh_from_db()
        self.assertEqual(m.estado, 'ASIGNADO')
        self.assertEqual(SeguimientoModulacion.objects.count(), 0)

    def test_en_patio_esperanza_sella_fecha_una_sola_vez(self):
        m = _modulacion(estado='RETENIDO')
        m.transicionar('EN_PATIO_ESPERANZA', usuario=self.user)
        m.refresh_from_db()
        primera = m.fecha_patio_esperanza
        self.assertIsNotNone(primera)
        # volver a entrar (desde otro camino) no re-sella
        m.estado = 'VERIFICACION_EN_TRANSPORTE'
        m.save(update_fields=['estado'])
        m.transicionar('EN_PATIO_ESPERANZA', usuario=self.user)
        m.refresh_from_db()
        self.assertEqual(m.fecha_patio_esperanza, primera)

    def test_retirado_tercero_sella_fecha_retiro(self):
        m = _modulacion(estado='EN_PATIO_ESPERANZA')
        m.transicionar('RETIRADO_TERCERO', usuario=self.user)
        m.refresh_from_db()
        self.assertIsNotNone(m.fecha_retiro)

    def test_mapa_cubre_todos_los_estados(self):
        claves = {c[0] for c in Modulacion.ESTADO_CHOICES}
        self.assertEqual(set(TRANSICIONES_MODULACION), claves)


class AutoAsignadoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')
        self.client.force_login(self.user)
        self.unidad = Unidad.objects.create(
            numero_economico='E-1', tipo='LOCAL', activa=True,
            placa='E1-001', año=2020,
            capacidad_combustible=Decimal('200.00'),
            rendimiento_esperado=Decimal('3.00'),
        )
        self.operador = Operador.objects.create(nombre='Juan', tipo='LOCAL', activo=True)

    def _post_asignar(self, m):
        return self.client.post(
            reverse('modulacion:asignar', args=[m.pk]),
            {'unidad': self.unidad.pk, 'operador': self.operador.pk},
        )

    def test_asignar_unidad_y_operador_promueve_pendiente_a_asignado(self):
        m = _modulacion(estado='PENDIENTE')
        self._post_asignar(m)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'ASIGNADO')
        self.assertIsNotNone(m.fecha_asignacion)
        seg = SeguimientoModulacion.objects.get(modulacion=m)
        self.assertEqual(seg.estado, 'ASIGNADO')
        self.assertEqual(seg.usuario, self.user)

    def test_reasignar_no_cambia_estado_si_ya_avanzo(self):
        m = _modulacion(estado='INGRESADO')
        self._post_asignar(m)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'INGRESADO')
        self.assertEqual(SeguimientoModulacion.objects.filter(modulacion=m).count(), 0)


class RutasExistentesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')
        self.client.force_login(self.user)

    def test_enviar_a_patio_desde_estado_valido_deja_historial(self):
        m = _modulacion(estado='DESADUANAMIENTO_LIBRE')
        self.client.post(reverse('modulacion:enviar_a_patio_esperanza', args=[m.pk]))
        m.refresh_from_db()
        self.assertEqual(m.estado, 'EN_PATIO_ESPERANZA')
        self.assertTrue(SeguimientoModulacion.objects.filter(
            modulacion=m, estado='EN_PATIO_ESPERANZA').exists())

    def test_enviar_a_patio_desde_estado_invalido_no_hace_nada(self):
        m = _modulacion(estado='ASIGNADO')
        resp = self.client.post(
            reverse('modulacion:enviar_a_patio_esperanza', args=[m.pk]), follow=True)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'ASIGNADO')
        self.assertContains(resp, 'no se puede pasar')

    def test_retiro_externo_desde_patio_deja_historial(self):
        m = _modulacion(estado='EN_PATIO_ESPERANZA')
        self.client.post(
            reverse('modulacion:retirar_de_patio', args=[m.pk]),
            {'transportista_externo': 'Fletes SA'},
        )
        m.refresh_from_db()
        self.assertEqual(m.estado, 'RETIRADO_TERCERO')
        self.assertEqual(m.transportista_externo, 'Fletes SA')
        self.assertTrue(SeguimientoModulacion.objects.filter(
            modulacion=m, estado='RETIRADO_TERCERO').exists())


class BadgeClassTests(TestCase):
    def test_badge_class_por_estado(self):
        casos = {
            'PENDIENTE': 'gray', 'ASIGNADO': 'indigo', 'INGRESADO': 'blue',
            'DESADUANAMIENTO_LIBRE': 'green', 'RECONOCIMIENTO_ADUANAL': 'red',
            'RETENIDO': 'amber', 'VERIFICACION_EN_TRANSPORTE': 'purple',
            'EN_PATIO_ESPERANZA': 'green', 'ENVIADO_BITACORA': 'blue',
            'RETIRADO_TERCERO': 'gray',
        }
        for estado, color in casos.items():
            m = Modulacion(estado=estado)
            self.assertIn(color, m.badge_class, estado)


class AtencionClientesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')
        self.client.force_login(self.user)

    def test_requiere_login(self):
        self.client.logout()
        resp = self.client.get(reverse('modulacion:atencion_clientes'))
        self.assertEqual(resp.status_code, 302)

    def test_lista_solo_estados_en_seguimiento(self):
        _modulacion(estado='PENDIENTE', contenedor='PEND1111111')
        m_seg = _modulacion(estado='INGRESADO', contenedor='INGR2222222')
        _modulacion(estado='ENVIADO_BITACORA', contenedor='ENVB3333333')
        resp = self.client.get(reverse('modulacion:atencion_clientes'))
        self.assertContains(resp, 'INGR2222222')
        self.assertNotContains(resp, 'PEND1111111')
        self.assertNotContains(resp, 'ENVB3333333')

    def test_muestra_botones_de_transiciones_validas(self):
        _modulacion(estado='INGRESADO', contenedor='INGR2222222')
        resp = self.client.get(reverse('modulacion:atencion_clientes'))
        # INGRESADO -> DESADUANAMIENTO_LIBRE | RECONOCIMIENTO_ADUANAL
        self.assertContains(resp, 'Desaduanamiento libre (verde)')
        self.assertContains(resp, 'Reconocimiento aduanal (rojo)')

    def test_avanzar_valido_mueve_y_deja_historial(self):
        m = _modulacion(estado='INGRESADO')
        resp = self.client.post(
            reverse('modulacion:avanzar_estado', args=[m.pk]),
            {'nuevo_estado': 'DESADUANAMIENTO_LIBRE', 'nota': 'verde'},
        )
        self.assertRedirects(resp, reverse('modulacion:atencion_clientes'))
        m.refresh_from_db()
        self.assertEqual(m.estado, 'DESADUANAMIENTO_LIBRE')
        seg = SeguimientoModulacion.objects.get(modulacion=m)
        self.assertEqual(seg.nota, 'verde')
        self.assertEqual(seg.usuario, self.user)

    def test_avanzar_invalido_no_cambia_nada(self):
        m = _modulacion(estado='INGRESADO')
        resp = self.client.post(
            reverse('modulacion:avanzar_estado', args=[m.pk]),
            {'nuevo_estado': 'EN_PATIO_ESPERANZA'}, follow=True,
        )
        m.refresh_from_db()
        self.assertEqual(m.estado, 'INGRESADO')
        self.assertContains(resp, 'no se puede pasar')

    def test_avanzar_solo_post(self):
        m = _modulacion(estado='INGRESADO')
        resp = self.client.get(reverse('modulacion:avanzar_estado', args=[m.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_filtro_por_estado(self):
        _modulacion(estado='INGRESADO', contenedor='INGR2222222')
        _modulacion(estado='RETENIDO', contenedor='RETE4444444')
        resp = self.client.get(reverse('modulacion:atencion_clientes'), {'estado': 'RETENIDO'})
        self.assertContains(resp, 'RETE4444444')
        self.assertNotContains(resp, 'INGR2222222')


class ListaYDetalleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('u', 'u@e.com', 'pw')
        self.client.force_login(self.user)

    def test_lista_usa_badge_class_para_estados_nuevos(self):
        _modulacion(estado='RECONOCIMIENTO_ADUANAL', contenedor='RECO5555555')
        resp = self.client.get(reverse('modulacion:list'))
        self.assertContains(resp, 'RECO5555555')
        self.assertContains(resp, 'bg-red-100')          # badge_class de RECONOCIMIENTO_ADUANAL
        self.assertContains(resp, 'Reconocimiento aduanal (rojo)')

    def test_detalle_muestra_linea_de_tiempo(self):
        m = _modulacion(estado='ASIGNADO')
        m.transicionar('INGRESADO', usuario=self.user, nota='ingresó a las 8')
        resp = self.client.get(reverse('modulacion:detail', args=[m.pk]))
        self.assertContains(resp, 'Ingresado')
        self.assertContains(resp, 'ingresó a las 8')

    def test_detalle_muestra_botones_de_transicion(self):
        m = _modulacion(estado='INGRESADO')
        resp = self.client.get(reverse('modulacion:detail', args=[m.pk]))
        self.assertContains(resp, 'Desaduanamiento libre (verde)')
        self.assertContains(resp, 'Reconocimiento aduanal (rojo)')


class AdminSeguimientoTests(TestCase):
    def test_admin_de_seguimiento_es_solo_lectura(self):
        from modulos.modulacion.admin import SeguimientoModulacionAdmin
        adm = SeguimientoModulacionAdmin(SeguimientoModulacion, admin.site)
        self.assertFalse(adm.has_add_permission(None))
        self.assertFalse(adm.has_change_permission(None))
        self.assertFalse(adm.has_delete_permission(None))
