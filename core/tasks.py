from __future__ import absolute_import, unicode_literals
import json
import logging

from celery import shared_task
from core.models import MutationLog, Language
from core.utils import set_current_user
from django.utils import translation

logger = logging.getLogger(__name__)


def _load_graphql_schema():
    """
    Build the GraphQL schema (GRAPHENE["SCHEMA"]) if this process has not yet.

    Building it calls every module's bind_signals(), which connects the
    mutation signal receivers. The web process builds it on its first
    request; a Celery worker only imports the schema of the mutation's own
    module, so without this the receivers other modules connect to that
    module's signals would silently not run. Failing to build it is an error:
    running the mutation without them would skip their side effects.
    """
    from graphene_django.settings import graphene_settings
    return graphene_settings.SCHEMA


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
        # Set the current user for audit logging
        if mutation.user:
            set_current_user(mutation.user)
        # __import__ needs to import the module with .schema to force .schema to load, then .schema.TheRealMutation
        mutation_class = getattr(__import__(f"{module}.schema").schema, class_name)

        if mutation.user and mutation.user.language:
            lang = mutation.user.language
            if isinstance(lang, Language):
                translation.activate(lang.code)
            else:
                translation.activate(lang)
        # The module's before_mutating receivers run here, in the transaction
        # of async_mutate, rather than in the request that queued this job:
        # see OpenIMISMutation.run_in_transaction. They are bound when the
        # GraphQL schema is built, which a worker does not do on its own.
        _load_graphql_schema()
        signal_data = json.loads(mutation.json_content)
        error_messages = mutation_class.run_in_transaction(
            mutation.user,
            mutation.id,
            signal_data,
            mutation_class.coerce_mutation_data(json.loads(mutation.json_content)),
        )
        if not error_messages:
            mutation.mark_as_successful()
        else:
            logger.debug(f"error :{error_messages}")
            try:
                error = json.dumps(error_messages)
            except Exception:
                error = str(error_messages)
            mutation.safe_mark_as_failed(error)
        return "OK"
    except Exception as exc:
        if mutation:
            mutation.safe_mark_as_failed(str(exc))
        logger.warning(f"Exception while processing mutation id {mutation_id}", exc_info=True)
        raise exc


@shared_task(name="sample_batch")
def openimis_test_batch():
    logger.info("sample batch")


@shared_task(name="sample_scheduling_method")
def sample_method(scheduler, sample_param, sample_named=0):
    logger.info("Scheduling our own tasks from here")
    # scheduler.add_job(foo.bar, id="name", minutes=10)
