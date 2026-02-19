from django.apps import AppConfig


class CombustibleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modulos.combustible'
    verbose_name = 'Gestión de Carga Combustible'

    def ready(self):
        import modulos.combustible.signals  # noqa: F401
