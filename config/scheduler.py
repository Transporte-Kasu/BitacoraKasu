"""
Scheduler APScheduler unificado para BitacoraKasu.

Registra un único job diario que ejecuta `generar_reportes`.
Ese command consulta la BD (ConfiguracionReporte) y solo envía los reportes
cuyo es_debido() retorne True, evitando duplicados y reportes fuera de fecha.

Iniciado automáticamente desde modulos/reportes/apps.py al arrancar el servidor.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.conf import settings

logger = logging.getLogger(__name__)

# Hora local (America/Mexico_City) a la que se comprueba si hay reportes pendientes
HORA_REVISION = getattr(settings, 'REPORTES_HORA_REVISION', '07:00')


def _ejecutar_reportes():
    """Llama al command generar_reportes para disparar los reportes debidos."""
    try:
        from django.core.management import call_command
        call_command('generar_reportes')
    except Exception:
        logger.exception('Error ejecutando generar_reportes desde el scheduler')


def iniciar_scheduler():
    """Crea e inicia el BackgroundScheduler. Llamar solo una vez al arrancar."""
    partes = HORA_REVISION.split(':')
    hour, minute = int(partes[0]), int(partes[1])

    scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
    scheduler.add_jobstore(DjangoJobStore(), 'default')

    scheduler.add_job(
        func=_ejecutar_reportes,
        trigger='cron',
        hour=hour,
        minute=minute,
        id='generar_reportes_diario',
        replace_existing=True,
        jobstore='default',
        misfire_grace_time=3600,   # tolera hasta 1 hora de retraso (reinicio del servidor)
    )

    scheduler.start()
    logger.info(
        'Scheduler iniciado — generar_reportes revisará reportes pendientes '
        'cada día a las %s (America/Mexico_City)', HORA_REVISION
    )
    return scheduler
