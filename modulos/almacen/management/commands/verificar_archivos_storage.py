from django.apps import apps
from django.core.management.base import BaseCommand
from config.storage_backends import MediaStorage, MODELOS_CON_ARCHIVOS


class Command(BaseCommand):
    help = (
        'Verifica que los archivos/imágenes referenciados en la base de datos '
        'existan realmente en el storage (DigitalOcean Spaces o local).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--modelo',
            type=str,
            default=None,
            help='Limitar la verificación a un modelo, formato app_label.ModelName',
        )

    def handle(self, *args, **options):
        storage = MediaStorage()
        filtro = options.get('modelo')

        total_faltantes = 0
        total_revisados = 0

        for app_label, model_name in sorted(MODELOS_CON_ARCHIVOS):
            model = apps.get_model(app_label, model_name)

            if filtro and filtro.lower() != f'{app_label}.{model_name}':
                continue

            campos_archivo = [
                f.name for f in model._meta.fields if hasattr(f, 'upload_to')
            ]
            if not campos_archivo:
                continue

            for campo in campos_archivo:
                qs = model.objects.exclude(**{campo: ''}).exclude(**{f'{campo}__isnull': True})
                etiqueta = f'{model.__name__}.{campo}'

                for obj in qs.iterator():
                    file_field = getattr(obj, campo)
                    if not file_field:
                        continue
                    total_revisados += 1
                    if not storage.exists(file_field.name):
                        total_faltantes += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'✗ {etiqueta} (pk={obj.pk}): {file_field.name} NO existe en storage'
                            )
                        )

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(f'Archivos revisados: {total_revisados}')
        if total_faltantes:
            self.stdout.write(self.style.ERROR(f'Archivos faltantes:  {total_faltantes}'))
        else:
            self.stdout.write(self.style.SUCCESS('Archivos faltantes:  0'))
        self.stdout.write('=' * 60)
