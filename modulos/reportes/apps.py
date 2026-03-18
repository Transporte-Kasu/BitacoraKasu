import sys

from django.apps import AppConfig

# Comandos de management que NO deben iniciar el scheduler
_SKIP_COMMANDS = {
    'migrate', 'makemigrations', 'createsuperuser', 'collectstatic',
    'test', 'shell', 'dbshell', 'check', 'loaddata', 'dumpdata',
    'generar_reportes', 'inspectdb', 'showmigrations', 'sqlmigrate',
    'flush', 'help',
}


class ReportesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modulos.reportes'
    verbose_name = 'Reportes Programados'

    def ready(self):
        """Inicia el BackgroundScheduler cuando arranca el servidor web."""
        # Evitar iniciar en management commands que no son el servidor
        if len(sys.argv) > 1 and sys.argv[1] in _SKIP_COMMANDS:
            return

        # Evitar doble arranque en el reloader de runserver (proceso hijo)
        import os
        if os.environ.get('RUN_MAIN') == 'true':
            return

        try:
            from config.scheduler import iniciar_scheduler
            iniciar_scheduler()
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                'No se pudo iniciar el scheduler de reportes'
            )
