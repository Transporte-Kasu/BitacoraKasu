from django.apps import AppConfig


class TallerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modulos.taller'
    verbose_name = 'Gestión de Taller'

    def ready(self):
        import modulos.taller.signals