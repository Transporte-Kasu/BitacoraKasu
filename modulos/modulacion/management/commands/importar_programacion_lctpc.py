"""
Management command: importar_programacion_lctpc

Lee el buzón de calidad por Microsoft Graph, procesa los correos de
programación de citas de LCTPC no vistos y actualiza/crea Modulaciones.

    python manage.py importar_programacion_lctpc

Pensado para correr desde el scheduler (cada 15 min) y a mano.
"""
from django.core.management.base import BaseCommand

from modulos.modulacion.services_importacion import importar_programaciones_lctpc


class Command(BaseCommand):
    help = 'Importa la programación de citas de LCTPC desde el buzón de calidad.'

    def handle(self, *args, **options):
        r = importar_programaciones_lctpc()
        self.stdout.write(
            'Programación LCTPC: '
            f'{r.correos_procesados} correo(s) procesado(s), '
            f'{r.correos_saltados} saltado(s), '
            f'{r.correos_con_error} con error. '
            f'Modulaciones: {r.creadas} creada(s), {r.actualizadas} actualizada(s) '
            f'({r.ambiguas} ambigua(s)).'
        )
