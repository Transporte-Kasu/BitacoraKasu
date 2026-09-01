from decimal import Decimal

from django.test import TestCase
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
