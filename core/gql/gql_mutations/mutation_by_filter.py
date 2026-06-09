import json
import logging
from functools import wraps

import django.db.models
from django.db.models import Q
from graphene_django import DjangoObjectType
from core.models.user import User
from typing import Dict
from core.utils import get_current_user


def mutation_on_uuids_from_filter(
    django_object: django.db.models.Model,
    object_gql_type: DjangoObjectType,
    query_filters_field: str = "additional_filters",
    explicit_filters_handlers: Dict[str, str] = None,
    user: User = None,
    return_objects: bool = False,
):
    """
    A decorator for async_mutate allowing use of filters instead of directly specifying the UUID in migrations.
    If data argument of async_mutate don't have 'uuids' key it tries to fetch objects by filters. As result uuids of
    filtered objects are added to data['uuids']. If 'return_objects' value is set to True,
    it adds filtered objects to data['filtered_objects'] instead of adding uuids.

    If in the incoming mutation the uuid's of the objects to be mutated are not specified directly, the decorator uses
    the value of the field of 'query_filters_field' field to build the query which is executed on 'django_object'
    and returns filtered objects uuids are used in mutation. Filters executed on queryset are built from the content
    of the 'object_gql_type' object's Metaclass filter_fields. If incoming filters are containing keys not included
    in the Metaclass, then this filters must be handled by explicit_filters_handlers.


    :param django_object: Django model to be filtered for uuids
    :param object_gql_type: DjangoObjectType with filter_fields in Metaclass,
    which is GQL equivalent to the django_object
    :param query_filters_field: A field from an incoming query that contains filter information. The value referenced
    by this field must be a JSON serialized to string.
    :param explicit_filters_handlers: Additional configured filters, if there are filters in the query that have no
    counterpart in object_gql_type they must be included here. Value of keys should be in django queryset notation.
    Example:
        Additional key 'services' with list of service codes can be included in explicit_filters_handlers
        as { 'services': 'services__service__code__in'...}
    :param return_objects: Optional argument if, set to True instead of adding uuid's do data['uuids'] objects are added
    to data['filtered_objects']
    :return: Queryset<[uuid]> containing with uuids of objects that were received after filtering
    """
    if explicit_filters_handlers is None:
        explicit_filters_handlers = {}

    available_filters = _build_filters_from_gql_filters(
        object_gql_type._meta.filter_fields
    )

    def inner_function(async_mutate):

        @wraps(async_mutate)
        def wrapper(cls, user, **data):
            if not data.get("uuids", None):
                args = json.loads(data[query_filters_field])

                q_filter = map_gql_to_django_filter(
                    args, available_filters, explicit_filters_handlers
                )
                base_query = django_object.objects.filter(*django_object.filter_validity()).filter(
                    q_filter
                )
                if user is None:
                    user = get_current_user()
                base_query = django_object.get_queryset(base_query, user)
                if return_objects:
                    data["filtered_objects"] = base_query
                else:
                    uuids = base_query.values_list("uuid", flat=True).distinct()
                    data["uuids"] = uuids
            return async_mutate(cls, user, **data)

        return wrapper

    return inner_function


def mutation_on_queryset_from_filter(
    django_object: django.db.models.Model,
    object_gql_type: DjangoObjectType,
    query_filters_field: str = "additional_filters",
    explicit_filters_handlers: Dict[str, str] = None,
    queryset_key: str = "queryset",
):
    """
    A decorator for async_mutate similar to @mutation_on_uuids_from_filter but focused on
    querysets rather than materializing uuid lists. This avoids unnecessary DB calls for
    extracting uuids when the mutation logic can work directly with a (lazy) queryset.

    Behavior (when 'uuids' not present in data):
    - Filters from `query_filters_field` (JSON string) are mapped to Django Q objects using the
      GQL type's filter_fields plus any explicit_handlers.
    - If a queryset is already present in data under `queryset_key`, it is *updated* by applying
      the mutation's additional filter criteria on top: `qs = qs.filter(q_filter)`.
      Callers can (and should, for business access flows) pre-apply row security / location
      restrictions / custom base filters and pass the queryset in; the decorator will further
      narrow it according to the user's chosen mutation filters.
    - If *no* queryset is provided under the key, the decorator obtains the base via
      `django_object.get_queryset(django_object.objects, effective_user)`. This means any
      validity handling, ROW_SECURITY, location/region restrictions, or business access logic
      implemented inside the model's get_queryset will be honored *before* the mutation filter
      is applied. The effective user is taken from the wrapper argument or falls back to
      get_current_user().
    - The (possibly security-restricted + additionally filtered) queryset is stored under
      `queryset_key` and the wrapped async_mutate is called.

    This design lets User.get_queryset (and equivalent on other models) be the single source
    of truth for "what rows is this user allowed to see/touch", so mutations using the
    decorator without a pre-supplied queryset automatically benefit from it.

    :param django_object: Django model class
    :param object_gql_type: DjangoObjectType (with Meta.filter_fields)
    :param query_filters_field: Key in data holding the JSON-serialized filter dict (default "additional_filters")
    :param explicit_filters_handlers: Map of filter keys (from incoming args) to Django lookup paths
                                      e.g. {'services': 'services__service__code__in'}
    :param queryset_key: The key in **data to read a possible input queryset from and write the
                         (updated) queryset to. Default: "queryset"
    """
    if explicit_filters_handlers is None:
        explicit_filters_handlers = {}

    available_filters = _build_filters_from_gql_filters(
        object_gql_type._meta.filter_fields
    )

    def inner_function(async_mutate):

        @wraps(async_mutate)
        def wrapper(cls, user, **data):
            if not data.get("uuids", None):
                args = json.loads(data[query_filters_field])

                q_filter = map_gql_to_django_filter(
                    args, available_filters, explicit_filters_handlers
                )

                incoming_qs = data.get(queryset_key)
                
                
                if incoming_qs is None:
                    if user is None:
                        user = get_current_user()
                    incoming_qs = django_object.get_queryset(django_object.objects, user)

            
                # Update the provided queryset with the mutation's filter criteria.
                # This keeps everything lazy and supports pre-scoped querysets
                # (e.g. from user business access restrictions).
                base_query = incoming_qs.filter(q_filter)
                data[queryset_key] = base_query

            return async_mutate(cls, user, **data)

        return wrapper

    return inner_function


def map_gql_to_django_filter(filters: dict, qgl_type_filters, explicit_handlers=None):
    if explicit_handlers is None:
        explicit_handlers = {}

    def __disable_notation(k):
        return k.lower().replace("_", "")

    mapped_filters = []
    for key, param in filters.items():
        try:
            if key in explicit_handlers.keys():
                mapped_filters.append(Q(**{explicit_handlers[key]: param}))
            else:
                filter_key = __disable_notation(key)
                django_filter = next(
                    (
                        gql_key
                        for gql_key in qgl_type_filters
                        if __disable_notation(gql_key) == filter_key
                    )
                )
                mapped_filters.append(Q(**{django_filter: param}))
        except StopIteration:
            error_msg = f"Could not find mapping for filter key {key}, available keys are {qgl_type_filters}"
            logging.error(error_msg)
            raise ValueError(error_msg)

    query_statement = mapped_filters.pop()  # get first query object
    for next_filter in mapped_filters:
        query_statement &= next_filter  # join remaining filters

    return query_statement


def _build_filters_from_gql_filters(filter_fields):
    fields = []
    for field, compare_types in filter_fields.items():
        for compare_type in compare_types:
            if compare_type == "exact":
                fields.append(field)
            else:
                query_filter = f"{field}__{compare_type.lower()}"
                fields.append(query_filter)
    return fields


def mutation_on_uuids_from_filter_business_model(
    django_object: django.db.models.Model,
    object_gql_type: DjangoObjectType,
    query_filters_field: str = "extended_filters",
    explicit_filters_handlers: Dict[str, str] = None,
    return_objects: bool = False,
):
    """
    dedicated extended mutation from filter decorator dedicated for BusinessHistoryModel entities (used for example
    in Formal Sector entities). See doc string for mutation_on_uuids_from_filter to read more how this works.
    """

    if explicit_filters_handlers is None:
        explicit_filters_handlers = {}

    available_filters = _build_filters_from_gql_filters(
        object_gql_type._meta.filter_fields
    )

    def inner_function(async_mutate):
        @wraps(async_mutate)
        def wrapper(cls, user, **data):
            # check if uuids exists as a substring in one of the key
            key_values_match = [key for key, value in data.items() if "uuids" in key]
            uuids_exists = False
            # check also if list of uuids contains any uuids if uuids key exists
            for key in key_values_match:
                if key in data:
                    if len(data[key]) > 0:
                        uuids_exists = True
            if not uuids_exists:
                args = json.loads(data[query_filters_field])
                # for contract entities
                # TODO: need to "pop" based on a section "advanced_search"
                amount_to = None
                amount_from = None
                if "amountFrom" in args:
                    amount_from = args["amountFrom"]
                    args.pop("amountFrom")
                if "amountTo" in args:
                    amount_to = args["amountTo"]
                    args.pop("amountTo")
                # remove validity filter if applied
                if "dateValidFrom_Gte" in args:
                    args.pop("dateValidFrom_Gte")
                if "dateValidTo_Lte" in args:
                    args.pop("dateValidTo_Lte")
                # remove isDeleted if applied
                if "is_deleted" in args:
                    args.pop("is_deleted")

                q_filter = map_gql_to_django_filter(
                    args, available_filters, explicit_filters_handlers
                )
                from core import datetime

                now = datetime.datetime.now()

                base_query = django_object.objects.filter(
                    Q(date_valid_from__lte=now),
                    Q(date_valid_to=None) | Q(date_valid_to__gte=now),
                    Q(is_deleted=False),
                ).filter(q_filter)
                # if mutation is related to contract entities
                # TODO check type of amount filter to check if we can send signal
                # TODO: need to send signal for the "pop" based on a
                #  search section "advanced_search" (signal should have the advances_search section and the object name)
                #  (to be implemented in the future) to contract module
                if django_object.__name__ == "Contract":
                    if amount_from or amount_to:
                        base_query = base_query.filter(
                            _append_filter_amount(amount_from, amount_to)
                        )

                if return_objects:
                    data["filtered_objects"] = base_query
                else:
                    uuids = base_query.values_list("id", flat=True).distinct()
                    data["uuids"] = uuids
            return async_mutate(cls, user, **data)

        return wrapper

    return inner_function


def _append_filter_amount(amount_from, amount_to):
    # TODO make a signal to contract module to not break modular approach and
    #  not repeat the same code from contract module

    status_notified = [1, 2]
    status_rectified = [4, 11, 3]
    status_due = [5, 6, 7, 8, 9, 10]

    # scenario - only amount_to set
    if not amount_from and amount_to:
        return (
            Q(amount_notified__lte=amount_to, state__in=status_notified)
            | Q(amount_rectified__lte=amount_to, state__in=status_rectified)
            | Q(amount_due__lte=amount_to, state__in=status_due)
        )

    # scenario - only amount_from set
    if amount_from and not amount_to:
        return (
            Q(amount_notified__gte=amount_from, state__in=status_notified)
            | Q(amount_rectified__gte=amount_from, state__in=status_rectified)
            | Q(amount_due__gte=amount_from, state__in=status_due)
        )

    # scenario - both filters set
    if amount_from and amount_to:
        return (
            Q(
                amount_notified__gte=amount_from,
                amount_notified__lte=amount_to,
                state__in=status_notified,
            )
            | Q(
                amount_rectified__gte=amount_from,
                amount_rectified__lte=amount_to,
                state__in=status_rectified,
            )
            | Q(
                amount_due__gte=amount_from,
                amount_due__lte=amount_to,
                state__in=status_due,
            )
        )
