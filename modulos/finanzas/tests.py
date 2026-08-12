from datetime import date
from decimal import Decimal

from django.test import TestCase

from .models import TarifaKilometro, RecepcionPipa, PrecioDieselMensual


class TarifaKilometroVigenteEnTests(TestCase):
    def test_devuelve_la_tarifa_activa_mas_reciente_hasta_la_fecha(self):
        TarifaKilometro.objects.create(valor=Decimal('10.00'), vigente_desde=date(2026, 1, 1))
        mas_reciente = TarifaKilometro.objects.create(valor=Decimal('12.50'), vigente_desde=date(2026, 6, 1))

        resultado = TarifaKilometro.vigente_en(date(2026, 7, 1))

        self.assertEqual(resultado, mas_reciente)

    def test_ignora_tarifas_futuras(self):
        vigente = TarifaKilometro.objects.create(valor=Decimal('10.00'), vigente_desde=date(2026, 1, 1))
        TarifaKilometro.objects.create(valor=Decimal('99.00'), vigente_desde=date(2026, 12, 1))

        resultado = TarifaKilometro.vigente_en(date(2026, 6, 1))

        self.assertEqual(resultado, vigente)

    def test_ignora_tarifas_inactivas(self):
        TarifaKilometro.objects.create(valor=Decimal('12.50'), vigente_desde=date(2026, 6, 1), activo=False)
        anterior = TarifaKilometro.objects.create(valor=Decimal('10.00'), vigente_desde=date(2026, 1, 1))

        resultado = TarifaKilometro.vigente_en(date(2026, 7, 1))

        self.assertEqual(resultado, anterior)

    def test_devuelve_none_si_no_hay_tarifa_previa(self):
        TarifaKilometro.objects.create(valor=Decimal('10.00'), vigente_desde=date(2026, 6, 1))

        resultado = TarifaKilometro.vigente_en(date(2026, 1, 1))

        self.assertIsNone(resultado)


class RecepcionPipaPrecioLitroTests(TestCase):
    def test_precio_litro_es_costo_total_entre_litros(self):
        pipa = RecepcionPipa.objects.create(
            fecha=date(2026, 6, 15),
            litros=Decimal('1000.00'),
            costo_total=Decimal('25000.00'),
        )

        self.assertEqual(pipa.precio_litro, Decimal('25.00'))


class PrecioDieselMensualRecalculoTests(TestCase):
    def test_signal_crea_renglon_mensual_al_guardar_una_pipa(self):
        RecepcionPipa.objects.create(
            fecha=date(2026, 6, 15),
            litros=Decimal('1000.00'),
            costo_total=Decimal('25000.00'),
        )

        renglon = PrecioDieselMensual.objects.get(anio=2026, mes=6)
        self.assertEqual(renglon.litros_totales, Decimal('1000.00'))
        self.assertEqual(renglon.costo_total, Decimal('25000.00'))
        self.assertEqual(renglon.precio_promedio_litro, Decimal('25.0000'))

    def test_promedio_ponderado_con_varias_pipas_en_el_mismo_mes(self):
        RecepcionPipa.objects.create(fecha=date(2026, 6, 5), litros=Decimal('1000.00'), costo_total=Decimal('25000.00'))
        RecepcionPipa.objects.create(fecha=date(2026, 6, 20), litros=Decimal('500.00'), costo_total=Decimal('14000.00'))

        renglon = PrecioDieselMensual.objects.get(anio=2026, mes=6)
        # (25000 + 14000) / (1000 + 500) = 26.0
        self.assertEqual(renglon.litros_totales, Decimal('1500.00'))
        self.assertEqual(renglon.precio_promedio_litro, Decimal('26.0000'))

    def test_recalcula_al_borrar_una_pipa(self):
        p1 = RecepcionPipa.objects.create(fecha=date(2026, 6, 5), litros=Decimal('1000.00'), costo_total=Decimal('25000.00'))
        RecepcionPipa.objects.create(fecha=date(2026, 6, 20), litros=Decimal('500.00'), costo_total=Decimal('14000.00'))

        p1.delete()

        renglon = PrecioDieselMensual.objects.get(anio=2026, mes=6)
        self.assertEqual(renglon.litros_totales, Decimal('500.00'))
        self.assertEqual(renglon.precio_promedio_litro, Decimal('28.0000'))

    def test_borra_el_renglon_mensual_si_ya_no_quedan_pipas_ese_mes(self):
        pipa = RecepcionPipa.objects.create(fecha=date(2026, 6, 5), litros=Decimal('1000.00'), costo_total=Decimal('25000.00'))

        pipa.delete()

        self.assertFalse(PrecioDieselMensual.objects.filter(anio=2026, mes=6).exists())

    def test_recalcula_el_mes_anterior_al_mover_una_pipa_de_mes(self):
        pipa = RecepcionPipa.objects.create(fecha=date(2026, 6, 5), litros=Decimal('1000.00'), costo_total=Decimal('25000.00'))

        pipa.fecha = date(2026, 7, 5)
        pipa.save()

        self.assertFalse(PrecioDieselMensual.objects.filter(anio=2026, mes=6).exists())
        renglon_julio = PrecioDieselMensual.objects.get(anio=2026, mes=7)
        self.assertEqual(renglon_julio.litros_totales, Decimal('1000.00'))


class PrecioDieselMensualVigenteEnTests(TestCase):
    def test_devuelve_el_renglon_del_mismo_mes(self):
        RecepcionPipa.objects.create(fecha=date(2026, 6, 5), litros=Decimal('1000.00'), costo_total=Decimal('25000.00'))

        resultado = PrecioDieselMensual.vigente_en(date(2026, 6, 20))

        self.assertEqual(resultado.anio, 2026)
        self.assertEqual(resultado.mes, 6)

    def test_carry_forward_a_mes_anterior_sin_pipas_ese_mes(self):
        RecepcionPipa.objects.create(fecha=date(2026, 4, 5), litros=Decimal('1000.00'), costo_total=Decimal('20000.00'))
        # Mayo no tiene ninguna pipa

        resultado = PrecioDieselMensual.vigente_en(date(2026, 5, 15))

        self.assertEqual(resultado.anio, 2026)
        self.assertEqual(resultado.mes, 4)

    def test_devuelve_none_si_no_hay_ningun_mes_previo_con_datos(self):
        RecepcionPipa.objects.create(fecha=date(2026, 6, 5), litros=Decimal('1000.00'), costo_total=Decimal('25000.00'))

        resultado = PrecioDieselMensual.vigente_en(date(2026, 1, 1))

        self.assertIsNone(resultado)
