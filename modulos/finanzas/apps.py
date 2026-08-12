from django.apps import AppConfig


class FinanzasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modulos.finanzas'
    verbose_name = 'Finanzas'

    def ready(self):
        import modulos.finanzas.signals  # noqa: F401
