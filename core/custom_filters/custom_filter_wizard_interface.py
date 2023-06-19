from collections import namedtuple
from django.db.models.query import QuerySet
from typing import List


class CustomFilterWizardInterface:
    """
        Interface responsible for delivering signatures of methods for
        building custom filters for a particular kind of object.

        Constants:
            FILTERS_BASED_ON_FIELD_TYPE: kind of mapper to indicate what kind of filters should be used
            depends on the type of the particular field.
    """

    FILTERS_BASED_ON_FIELD_TYPE = {
        "string": ["iexact", "istartswith", "icontains"],
        "integer": ["exact", "lt", "lte", "gt", "gte"],
        "decimal": ["exact", "lt", "lte", "gt", "gte"],
        "date": ["exact", "lt", "lte", "gt", "gte"],
        "boolean": ["exact"],
    }

    def get_type_of_object(self) -> str:
        """
        Get the type of object for which we want to define a specific way of building filters.

        :return: The type of the object.
        :rtype: str
        """
        pass

    def load_definition(self, tuple_type: type, **kwargs) -> List[namedtuple]:
        """
        Load the definition of how to create filters.

        This method retrieves the definition of how to create filters and returns it as a list of named tuples.
        Each named tuple is built with the provided `tuple_type` and has the fields `field`, `filter`, and `value`.

        Example named tuple: <Type>(field=<str>, filter=<str>, value=<str>)
        Example usage: BenefitPlan(field='income', filter='lt, gte, icontains, exact', value='')

        :param tuple_type: The type of the named tuple.
        :type tuple_type: type

        :return: A list of named tuples representing the definition of how to create filters.
        :rtype: List[namedtuple]
        """
        pass

    def apply_filter_to_queryset(self, custom_filters: List[namedtuple], query: QuerySet, relation=None):
        """
        Apply custom filters to a queryset.

        :param custom_filters: List of named tuples representing custom filters.
        :type custom_filters: List[namedtuple]

        :param query: The original queryset with filters.
        :type query: django.db.models.query.QuerySet

        :param relation: The optional argument which defines the relation field in queryset for example 'beneficiary'
        :type relation: str or None

        :return: The updated queryset with additional filters applied.
        :rtype: django.db.models.query.QuerySet
        """
        pass
