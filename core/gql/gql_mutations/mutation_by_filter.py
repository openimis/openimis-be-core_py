import json
import logging
from functools import wraps

import django.db.models
from django.db.models import Q
from graphene_django import DjangoObjectType
from typing import Dict


def mutation_on_uuids_from_filter(django_object: django.db.models.Model,
                                  object_gql_type: DjangoObjectType,
                                  query_filters_field: str = 'additional_filters',
                                  explicit_filters_handlers: Dict[str, str] = None,
                                  return_objects: bool = False):
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

    available_filters = _build_filters_from_gql_filters(object_gql_type._meta.filter_fields)

    def inner_function(async_mutate):

        @wraps(async_mutate)
        def wrapper(cls, user, **data):
            if not data.get('uuids', None):
                args = json.loads(data[query_filters_field])

                q_filter = map_gql_to_django_filter(args, available_filters, explicit_filters_handlers)
                base_query = django_object \
                    .objects \
                    .filter(validity_to=None) \
                    .filter(q_filter) \

                if return_objects:
                    data['filtered_objects'] = base_query
                else:
                    uuids = base_query.values_list('uuid', flat=True).distinct()
                    data['uuids'] = uuids
            async_mutate(cls, user, **data)
        return wrapper
    return inner_function


def map_gql_to_django_filter(filters: dict, qgl_type_filters, explicit_handlers=None):
    if explicit_handlers is None:
        explicit_handlers = {}

    def __disable_notation(k):
        return k.lower().replace('_', '')

    mapped_filters = []
    for key, param in filters.items():
        try:
            if key in explicit_handlers.keys():
                mapped_filters.append(Q(**{explicit_handlers[key]: param}))
            else:
                filter_key = __disable_notation(key)
                django_filter = next((gql_key for gql_key in qgl_type_filters
                                      if __disable_notation(gql_key) == filter_key))
                mapped_filters.append(Q(**{django_filter: param}))
        except StopIteration as s:
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
            if compare_type == 'exact':
                fields.append(field)
            else:
                query_filter = F"{field}__{compare_type.lower()}"
                fields.append(query_filter)
    return fields


def mutation_on_uuids_from_filter_business_model(django_object: django.db.models.Model,
                                                 object_gql_type: DjangoObjectType,
                                                 query_filters_field: str = 'extended_filters',
                                                 explicit_filters_handlers: Dict[str, str] = None,
                                                 return_objects: bool = False):
    """
    dedicated extended mutation from filter decorator dedicated for BusinessHistoryModel entities (used for example
    in Formal Sector entities). See doc string for mutation_on_uuids_from_filter to read more how this works.
    """

    if explicit_filters_handlers is None:
        explicit_filters_handlers = {}

    available_filters = _build_filters_from_gql_filters(object_gql_type._meta.filter_fields)

    def inner_function(async_mutate):
        @wraps(async_mutate)
        def wrapper(cls, user, **data):
            # check if uuids exists as a substring in one of the key
            key_values_match = [key for key, value in data.items() if 'uuids' in key]
            uuids_exists = False
            # check also if list of uuids contains any uuids if uuids key exists
            for key in key_values_match:
                if key in data:
                    if len(data[key]) > 0:
                        uuids_exists = True
            if not uuids_exists:
                args = json.loads(data[query_filters_field])
                #for contract entities
                # TODO: need to "pop" based on a section "advanced_search"
                amount_to = None
                amount_from = None
                if 'amountFrom' in args:
                    amount_from = args['amountFrom']
                    args.pop("amountFrom")
                if 'amountTo' in args:
                    amount_to = args['amountTo']
                    args.pop("amountTo")
                # remove validity filter if applied
                if 'dateValidFrom_Gte' in args:
                    args.pop("dateValidFrom_Gte")
                if 'dateValidTo_Lte' in args:
                    args.pop("dateValidTo_Lte")
                # remove isDeleted if applied
                if 'is_deleted' in args:
                    args.pop("is_deleted")

                q_filter = map_gql_to_django_filter(args, available_filters, explicit_filters_handlers)
                from core import datetime
                now = datetime.datetime.now()

                base_query = django_object \
                    .objects \
                    .filter(
                        Q(date_valid_from__lte=now),
                        Q(date_valid_to=None) | Q(date_valid_to__gte=now),
                        Q(is_deleted=False)
                    ) \
                    .filter(q_filter) \

                # if mutation is related to contract entities
                # TODO check type of amount filter to check if we can send signal
                # TODO: need to send signal for the "pop" based on a search section "advanced_search" (signal should have the advances_search section and the object name)
                #  (to be implemented in the future) to contract module
                if django_object.__name__ == 'Contract':
                    if amount_from or amount_to:
                        base_query = base_query.filter(_append_filter_amount(amount_from, amount_to))

                if return_objects:
                    data['filtered_objects'] = base_query
                else:
                    uuids = base_query.values_list('id', flat=True).distinct()
                    data['uuids'] = uuids
            async_mutate(cls, user, **data)
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
             Q(amount_notified__lte=amount_to, state__in=status_notified) |
             Q(amount_rectified__lte=amount_to, state__in=status_rectified) |
             Q(amount_due__lte=amount_to, state__in=status_due)
        )

    # scenario - only amount_from set
    if amount_from and not amount_to:
        return (
            Q(amount_notified__gte=amount_from, state__in=status_notified) |
            Q(amount_rectified__gte=amount_from, state__in=status_rectified) |
            Q(amount_due__gte=amount_from, state__in=status_due)
        )

    # scenario - both filters set
    if amount_from and amount_to:
        return (
            Q(amount_notified__gte=amount_from, amount_notified__lte=amount_to, state__in=status_notified) |
            Q(amount_rectified__gte=amount_from, amount_rectified__lte=amount_to, state__in=status_rectified) |
            Q(amount_due__gte=amount_from, amount_due__lte=amount_to, state__in=status_due)
        )
