import logging
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from core.apps import CoreConfig
from core.services import send_password_expiry_reminders

logger = logging.getLogger(__name__)


def schedule_tasks(scheduler):
    scheduler.add_job(
        send_password_expiry_reminders,
        trigger=CronTrigger(
            hour=CoreConfig.password_expiry_email_reminder_hour,
            minute=CoreConfig.password_expiry_email_reminder_minute,
            timezone=ZoneInfo(CoreConfig.password_expiry_email_reminder_timezone),
        ),
        id="core_password_expiry_email_reminders",
        max_instances=1,
        replace_existing=True,
    )
    logger.info("Scheduled core password expiry email reminders")
