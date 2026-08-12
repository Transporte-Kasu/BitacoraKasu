from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from modulos.almacen.models import (
    ProductoAlmacen, SalidaRapidaConsumible, AsignacionDirectaAlmacen,
    AsignacionSalida, ItemAsignacionSalida,
)
from modulos.bitacoras.models import BitacoraViaje
from modulos.combustible.models import Despachador, CargaCombustible
from modulos.operadores.models import Operador
from modulos.taller.models import OrdenTrabajo, PiezaRequerida

from .admin import calcular_reporte_utilidad
from .models import Unidad


def _aware(y, m, d, h=8):
    return timezone.make_aware(datetime(y, m, d, h))


class CalcularReporteUtilidadTests(TestCase):
    def setUp(self):
        self.unidad = Unidad.objects.create(
            numero_economico='ECO-001', placa='ABC-123', tipo='LOCAL', año=2020,
            capacidad_combustible=Decimal('200.00'), rendimiento_esperado=Decimal('3.00'),
        )
        self.operador = Operador.objects.create(nombre='Juan Pérez', tipo='LOCAL')
        self.despachador = Despachador.objects.create(nombre='Pedro López')
        self.user = User.objects.create_user(username='tester')
        self.desde = date(2026, 6, 1)
        self.hasta = date(2026, 6, 30)

    def test_suma_ingreso_de_bitacoras_completadas_en_rango(self):
        BitacoraViaje.objects.create(
            operador=self.operador, unidad=self.unidad, modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 1), fecha_salida=_aware(2026, 6, 1),
            fecha_llegada=_aware(2026, 6, 2), destino='Destino 1',
            ingreso_calculado=Decimal('1500.00'),
        )
        # Fuera de rango: no debe sumarse
        BitacoraViaje.objects.create(
            operador=self.operador, unidad=self.unidad, modalidad='LOCAL',
            fecha_carga=_aware(2026, 7, 1), fecha_salida=_aware(2026, 7, 1),
            fecha_llegada=_aware(2026, 7, 2), destino='Destino 2',
            ingreso_calculado=Decimal('500.00'),
        )

        resultado = calcular_reporte_utilidad(self.desde, self.hasta)

        fila = resultado['filas'][0]
        self.assertEqual(fila['unidad'], self.unidad)
        self.assertEqual(fila['ingresos'], Decimal('1500.00'))

    def test_suma_gasto_combustible_en_rango(self):
        CargaCombustible.objects.create(
            despachador=self.despachador, unidad=self.unidad, cantidad_litros=Decimal('100.00'),
            kilometraje_actual=1000, nivel_combustible_inicial='MEDIO', estado_candado_anterior='NORMAL',
            fecha_hora_inicio=_aware(2026, 6, 10), tipo_flujo='LOCAL', estado='COMPLETADO',
            costo_calculado=Decimal('2500.00'),
        )

        resultado = calcular_reporte_utilidad(self.desde, self.hasta)

        fila = resultado['filas'][0]
        self.assertEqual(fila['gasto_combustible'], Decimal('2500.00'))

    def test_suma_gasto_taller_usando_costo_total_real(self):
        orden = OrdenTrabajo.objects.create(
            unidad=self.unidad, descripcion_problema='Falla motor', kilometraje_ingreso=1000,
            estado='COMPLETADA', fecha_finalizacion=_aware(2026, 6, 15), creada_por=self.user,
            costo_real_mano_obra=Decimal('300.00'),
        )
        PiezaRequerida.objects.create(
            orden_trabajo=orden, nombre_pieza='Filtro', cantidad=Decimal('2'),
            costo_real=Decimal('100.00'), agregada_por=self.user,
        )

        resultado = calcular_reporte_utilidad(self.desde, self.hasta)

        fila = resultado['filas'][0]
        # mano de obra 300 + piezas (2 * 100) = 500
        self.assertEqual(fila['gasto_taller'], Decimal('500.00'))

    def test_suma_gasto_consumibles_de_las_tres_fuentes(self):
        producto = ProductoAlmacen.objects.create(
            categoria='Filtros', sku='SKU-1', descripcion='Filtro de aceite',
            localidad='A1', unidad_medida='Pieza', costo_unitario=Decimal('50.00'), cantidad=Decimal('1000'),
            es_consumible=True,
        )
        SalidaRapidaConsumible.objects.create(
            producto=producto, cantidad=Decimal('2'), entregado_por=self.user,
            solicitante='Juan', unidad=self.unidad, fecha_salida=_aware(2026, 6, 5),
        )
        AsignacionDirectaAlmacen.objects.create(
            producto=producto, unidad=self.unidad, cantidad=Decimal('1'),
            motivo='Reparación rápida', entregado_por=self.user, fecha_asignacion=_aware(2026, 6, 6),
        )
        asignacion = AsignacionSalida.objects.create(
            fecha=date(2026, 6, 7), solicitante='Juan', tipo_destino='UNIDAD',
            unidad=self.unidad, justificacion='Mantenimiento preventivo',
        )
        ItemAsignacionSalida.objects.create(asignacion=asignacion, producto=producto, cantidad=Decimal('3'))

        resultado = calcular_reporte_utilidad(self.desde, self.hasta)

        fila = resultado['filas'][0]
        # (2 + 1 + 3) * 50 = 300
        self.assertEqual(fila['gasto_consumibles'], Decimal('300.00'))

    def test_utilidad_es_ingresos_menos_gasto_total(self):
        BitacoraViaje.objects.create(
            operador=self.operador, unidad=self.unidad, modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 1), fecha_salida=_aware(2026, 6, 1),
            fecha_llegada=_aware(2026, 6, 2), destino='Destino 1',
            ingreso_calculado=Decimal('1500.00'),
        )
        CargaCombustible.objects.create(
            despachador=self.despachador, unidad=self.unidad, cantidad_litros=Decimal('100.00'),
            kilometraje_actual=1000, nivel_combustible_inicial='MEDIO', estado_candado_anterior='NORMAL',
            fecha_hora_inicio=_aware(2026, 6, 10), tipo_flujo='LOCAL', estado='COMPLETADO',
            costo_calculado=Decimal('500.00'),
        )

        resultado = calcular_reporte_utilidad(self.desde, self.hasta)

        fila = resultado['filas'][0]
        self.assertEqual(fila['gasto_total'], Decimal('500.00'))
        self.assertEqual(fila['utilidad'], Decimal('1000.00'))

    def test_no_duplica_piezas_de_taller_con_gasto_consumibles(self):
        """Las piezas contabilizadas en OrdenTrabajo.costo_total_real no deben
        sumarse otra vez como gasto de consumibles, aunque salgan de almacén."""
        producto = ProductoAlmacen.objects.create(
            categoria='Filtros', sku='SKU-2', descripcion='Filtro de aire',
            localidad='A2', unidad_medida='Pieza', costo_unitario=Decimal('80.00'), cantidad=Decimal('1000'),
        )
        orden = OrdenTrabajo.objects.create(
            unidad=self.unidad, descripcion_problema='Cambio de filtro', kilometraje_ingreso=1000,
            estado='COMPLETADA', fecha_finalizacion=_aware(2026, 6, 15), creada_por=self.user,
        )
        PiezaRequerida.objects.create(
            orden_trabajo=orden, producto_almacen=producto, cantidad=Decimal('1'),
            costo_real=Decimal('80.00'), agregada_por=self.user,
        )

        resultado = calcular_reporte_utilidad(self.desde, self.hasta)

        fila = resultado['filas'][0]
        self.assertEqual(fila['gasto_taller'], Decimal('80.00'))
        self.assertEqual(fila['gasto_consumibles'], Decimal('0'))
        self.assertEqual(fila['gasto_total'], Decimal('80.00'))

    def test_cuenta_bitacoras_y_cargas_excluidas_por_falta_de_calculo(self):
        BitacoraViaje.objects.create(
            operador=self.operador, unidad=self.unidad, modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 1), fecha_salida=_aware(2026, 6, 1),
            fecha_llegada=_aware(2026, 6, 2), destino='Sin tarifa vigente',
        )
        CargaCombustible.objects.create(
            despachador=self.despachador, unidad=self.unidad, cantidad_litros=Decimal('50.00'),
            kilometraje_actual=1000, nivel_combustible_inicial='MEDIO', estado_candado_anterior='NORMAL',
            fecha_hora_inicio=_aware(2026, 6, 10), tipo_flujo='LOCAL', estado='COMPLETADO',
        )

        resultado = calcular_reporte_utilidad(self.desde, self.hasta)

        self.assertEqual(resultado['bitacoras_excluidas'], 1)
        self.assertEqual(resultado['cargas_excluidas'], 1)

    def test_totales_generales_suman_todas_las_unidades(self):
        otra_unidad = Unidad.objects.create(
            numero_economico='ECO-002', placa='XYZ-999', tipo='LOCAL', año=2021,
            capacidad_combustible=Decimal('200.00'), rendimiento_esperado=Decimal('3.00'),
        )
        BitacoraViaje.objects.create(
            operador=self.operador, unidad=self.unidad, modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 1), fecha_salida=_aware(2026, 6, 1),
            fecha_llegada=_aware(2026, 6, 2), destino='Destino 1',
            ingreso_calculado=Decimal('1000.00'),
        )
        BitacoraViaje.objects.create(
            operador=self.operador, unidad=otra_unidad, modalidad='LOCAL',
            fecha_carga=_aware(2026, 6, 1), fecha_salida=_aware(2026, 6, 1),
            fecha_llegada=_aware(2026, 6, 2), destino='Destino 2',
            ingreso_calculado=Decimal('2000.00'),
        )

        resultado = calcular_reporte_utilidad(self.desde, self.hasta)

        self.assertEqual(resultado['totales']['ingresos'], Decimal('3000.00'))
        self.assertEqual(len(resultado['filas']), 2)
