from django.apps import AppConfig


class VaciosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modulos.vacios'
    verbose_name = 'Vacíos'

    def ready(self):
        import modulos.vacios.signals  # noqa: F401
