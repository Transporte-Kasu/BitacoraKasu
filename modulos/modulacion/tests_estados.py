from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from modulos.modulacion.models import (
    Agencia, Modulacion, SeguimientoModulacion, TerminalPortuaria,
    TransicionInvalida, TRANSICIONES_MODULACION,
)


def _modulacion(estado='PENDIENTE', **kw):
    return Modulacion.objects.create(
        agencia=Agencia.objects.get_or_create(nombre='LOGINCO')[0],
        terminal_portuaria=TerminalPortuaria.objects.get_or_create(nombre='LCTPC')[0],
        tipo_contenedor='40HC', peso_toneladas=Decimal('18.5'),
        contenedor='ABCU1234567', estado=estado, **kw,
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
