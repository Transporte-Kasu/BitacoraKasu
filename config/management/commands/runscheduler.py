"""
Comando de gestión para ejecutar el scheduler de reportes automáticos.

Uso:
    python manage.py runscheduler

En producción (DigitalOcean App Platform), agregar al Procfile como worker:
    worker: python manage.py runscheduler
"""
import logging

from django.core.management.base import BaseCommand
from apscheduler.schedulers.blocking import BlockingScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.conf import settings

logger = logging.getLogger(__name__)


def _parse_hora(hora_str):
    partes = hora_str.split(':')
    return int(partes[0]), int(partes[1])


def _registrar_job(scheduler, nombre, func, cfg):
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
        scheduler.add_job(trigger='cron', hour=hour, minute=minute, **kwargs)
    elif periodicidad == 'semanal':
        scheduler.add_job(trigger='cron', day_of_week=dia_semana, hour=hour, minute=minute, **kwargs)
    else:
        scheduler.add_job(trigger='cron', day=dia_mes, hour=hour, minute=minute, **kwargs)

    logger.info(f'  Job "{nombre}": {periodicidad} a las {hora_str}')


class Command(BaseCommand):
    help = 'Inicia el scheduler de reportes automáticos (proceso bloqueante).'

    def handle(self, *args, **options):
        from config.reportes.almacen import enviar_reporte_almacen
        from config.reportes.combustible import enviar_reporte_combustible

        self.stdout.write(self.style.SUCCESS('Iniciando scheduler de reportes BitacoraKasu...'))

        scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_jobstore(DjangoJobStore(), 'default')

        cfg = getattr(settings, 'REPORTES_CONFIG', {})

        _registrar_job(scheduler, 'reporte_almacen', enviar_reporte_almacen, cfg.get('almacen', {}))
        _registrar_job(scheduler, 'reporte_combustible', enviar_reporte_combustible, cfg.get('combustible', {}))

        self.stdout.write('Jobs registrados:')
        for job in scheduler.get_jobs():
            self.stdout.write(f'  - {job.id} — próxima ejecución: {job.next_run_time}')

        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write(self.style.WARNING('Scheduler detenido.'))
