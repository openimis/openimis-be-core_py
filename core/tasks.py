from __future__ import absolute_import, unicode_literals
import json
import logging

from celery import shared_task
from core.models import MutationLog, Language
from django.utils import translation

logger = logging.getLogger(__name__)


@shared_task
def openimis_mutation_async(mutation_id, module, class_name):
    """
    This method is called by the OpenIMISMutation, directly or asynchronously to call the async_mutate method.
    :param mutation_id: ID of the mutation object. We're not passing the whole object because an async call would have
                        to serialize it into the queue.
    :param module: "claim", "insuree"...
    :param class_name: Name of the OpenIMISMutation class whose async_mutate() will be called
    :return: unused, returns "OK"
    """
    mutation = None
    try:
        mutation = MutationLog.objects.get(id=mutation_id)
        # __import__ needs to import the module with .schema to force .schema to load, then .schema.TheRealMutation
        mutation_class = getattr(__import__(f"{module}.schema").schema, class_name)

        if mutation.user and mutation.user.language:
            lang = mutation.user.language
            if isinstance(lang, Language):
                translation.activate(lang.code)
            else:
                translation.activate(lang)
        error_messages = mutation_class.async_mutate(mutation.user, **json.loads(mutation.json_content))
        if not error_messages:
            mutation.mark_as_successful()
        else:
            mutation.mark_as_failed(json.dumps(error_messages))
        return "OK"
    except Exception as exc:
        if mutation:
            mutation.mark_as_failed(str(exc))
        logger.warning(f"Exception while processing mutation id {mutation_id}", exc_info=True)
        raise exc


def openimis_test_batch():
    logger.info("sample batch")


def sample_method(scheduler, sample_param, sample_named=0):
    logger.info("Scheduling our own tasks from here")
    # scheduler.add_job(foo.bar, id="name", minutes=10)

