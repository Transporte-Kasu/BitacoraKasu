from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from modulos.finanzas.models import RecepcionPipa
from modulos.unidades.models import Unidad

from .models import Despachador, CargaCombustible


def _crear_unidad(numero_economico='ECO-001'):
    return Unidad.objects.create(
        numero_economico=numero_economico,
        placa='ABC-123',
        tipo='LOCAL',
        año=2020,
        capacidad_combustible=Decimal('200.00'),
        rendimiento_esperado=Decimal('3.00'),
    )


def _crear_despachador():
    return Despachador.objects.create(nombre='Pedro López')


def _aware(y, m, d, h=8):
    return timezone.make_aware(datetime(y, m, d, h))


class CostoCalculadoTests(TestCase):
    def setUp(self):
        self.unidad = _crear_unidad()
        self.despachador = _crear_despachador()

    def _crear_carga(self, **overrides):
        defaults = dict(
            despachador=self.despachador,
            unidad=self.unidad,
            cantidad_litros=Decimal('100.00'),
            kilometraje_actual=1000,
            nivel_combustible_inicial='MEDIO',
            estado_candado_anterior='NORMAL',
            fecha_hora_inicio=_aware(2026, 6, 1),
            tipo_flujo='LOCAL',
        )
        defaults.update(overrides)
        return CargaCombustible(**defaults)

    def test_calcula_costo_al_completar_carga_con_precio_mensual_vigente(self):
        RecepcionPipa.objects.create(fecha=date(2026, 6, 1), litros=Decimal('1000.00'), costo_total=Decimal('25000.00'))
        carga = self._crear_carga(estado='COMPLETADO')

        carga.save()

        self.assertEqual(carga.costo_calculado, Decimal('2500.00'))

    def test_costo_queda_none_si_no_hay_precio_vigente(self):
        carga = self._crear_carga(estado='COMPLETADO')

        carga.save()

        self.assertIsNone(carga.costo_calculado)

    def test_no_recalcula_costo_ya_establecido(self):
        RecepcionPipa.objects.create(fecha=date(2026, 6, 1), litros=Decimal('1000.00'), costo_total=Decimal('25000.00'))
        carga = self._crear_carga(estado='COMPLETADO', costo_calculado=Decimal('999.00'))

        carga.save()

        self.assertEqual(carga.costo_calculado, Decimal('999.00'))

    def test_carga_no_completada_no_calcula_costo(self):
        RecepcionPipa.objects.create(fecha=date(2026, 6, 1), litros=Decimal('1000.00'), costo_total=Decimal('25000.00'))
        carga = self._crear_carga(estado='EN_PROCESO')

        carga.save()

        self.assertIsNone(carga.costo_calculado)
