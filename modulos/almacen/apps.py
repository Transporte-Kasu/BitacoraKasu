from django.apps import AppConfig


class AlmacenConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modulos.almacen'
    verbose_name = 'Almacén'

    def ready(self):
        import modulos.almacen.signals  # noqa
