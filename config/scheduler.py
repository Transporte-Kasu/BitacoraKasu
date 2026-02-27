"""
Configuración del scheduler APScheduler con django-apscheduler.
Los jobs se registran dinámicamente según REPORTES_CONFIG en settings.py.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.conf import settings

logger = logging.getLogger(__name__)


def _parse_hora(hora_str):
    """Convierte '11:30' en (hour=11, minute=30)."""
    partes = hora_str.split(':')
    return int(partes[0]), int(partes[1])


def _registrar_job(scheduler, nombre, func, cfg):
    """Registra un job según la periodicidad configurada."""
    periodicidad = cfg.get('periodicidad', 'semanal')
    hora_str = cfg.get('hora', '08:00')
    hour, minute = _parse_hora(hora_str)
    dia_semana = cfg.get('dia_semana', 'fri')
    dia_mes = cfg.get('dia_mes', 1)

    kwargs = dict(
        func=func,
        id=nombre,
        replace_existing=True,
        jobstore='default',
    )

    if periodicidad == 'diario':
        scheduler.add_job(
            trigger='cron',
            hour=hour, minute=minute,
            **kwargs
        )
    elif periodicidad == 'semanal':
        scheduler.add_job(
            trigger='cron',
            day_of_week=dia_semana,
            hour=hour, minute=minute,
            **kwargs
        )
    else:  # mensual
        scheduler.add_job(
            trigger='cron',
            day=dia_mes,
            hour=hour, minute=minute,
            **kwargs
        )

    logger.info(f'Job "{nombre}" registrado ({periodicidad}, {hora_str})')


def iniciar_scheduler():
    """Crea e inicia el scheduler en segundo plano. Llamar solo una vez."""
    from config.reportes.almacen import enviar_reporte_almacen
    from config.reportes.combustible import enviar_reporte_combustible

    scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
    scheduler.add_jobstore(DjangoJobStore(), 'default')

    cfg = getattr(settings, 'REPORTES_CONFIG', {})

    _registrar_job(scheduler, 'reporte_almacen', enviar_reporte_almacen, cfg.get('almacen', {}))
    _registrar_job(scheduler, 'reporte_combustible', enviar_reporte_combustible, cfg.get('combustible', {}))

    scheduler.start()
    logger.info('Scheduler de reportes iniciado.')
    return scheduler
