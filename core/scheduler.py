import logging

from apscheduler.schedulers.background import BackgroundScheduler
# from apscheduler.executors.pool import ProcessPoolExecutor, ThreadPoolExecutor
from core import get_scheduler_method_ref
from django_apscheduler.jobstores import register_events  # , register_job

from django.conf import settings

logger = logging.getLogger(__name__)

# Create scheduler to run in a thread inside the application process
scheduler = BackgroundScheduler(settings.SCHEDULER_CONFIG)


def start():
    if settings.DEBUG:
        # Hook into the apscheduler logger
        logging.basicConfig()
        logging.getLogger('apscheduler').setLevel(logging.DEBUG)

    if settings.SCHEDULER_JOBS:
        for job in settings.SCHEDULER_JOBS:
            logger.debug("Scheduling job %s", job["method"])
            method = get_scheduler_method_ref(job["method"])
            scheduler.add_job(*([method] + job.get("args", [])), **(job.get("kwargs", {})))

    if settings.SCHEDULER_CUSTOM:
        for job in settings.SCHEDULER_CUSTOM:
            logger.debug("Calling custom scheduler %s", job["method"])
            method = get_scheduler_method_ref(job["method"])
            method(*([scheduler] + job.get("args", [])), **(job.get("kwargs", {})))

    # Add the scheduled jobs to the Django admin interface
    register_events(scheduler)

    scheduler.start()
