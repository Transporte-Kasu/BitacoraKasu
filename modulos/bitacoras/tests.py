from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from modulos.finanzas.models import TarifaKilometro
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad

from .models import BitacoraViaje


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
