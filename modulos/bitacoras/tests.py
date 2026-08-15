from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from modulos.finanzas.models import TarifaKilometro
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad

from .models import BitacoraViaje
from config.services.twilio_service import _var_info_carga, _numero_wa_mx


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
