from django.test import TestCase

from modulos.bitacoras.forms import ClienteForm
from modulos.bitacoras.models import Cliente


class ClienteAliasTests(TestCase):
    def test_etiqueta_usa_alias_si_hay(self):
        c = Cliente(nombre='Transportes Moya SA', alias='MOY')
        self.assertEqual(c.etiqueta, 'MOY')

    def test_etiqueta_cae_al_nombre_si_no_hay_alias(self):
        c = Cliente(nombre='Nolasco SA')
        self.assertEqual(c.etiqueta, 'Nolasco SA')

    def test_form_guarda_alias(self):
        form = ClienteForm(data={
            'nombre': 'Zeta SA', 'alias': 'ZEEV', 'email': '', 'celular': '',
            'activo': True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        cliente = form.save()
        self.assertEqual(cliente.alias, 'ZEEV')
