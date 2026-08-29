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
