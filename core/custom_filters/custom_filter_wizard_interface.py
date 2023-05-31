from collections import namedtuple
from typing import List


class CustomFilterWizardInterface:
    def get_type_of_object(self) -> str:
        """
            Get the type of object for which we want to define a specific way of building filters.

            Returns:
                str: The type of the object.
        """
        pass

    def load_definition(self, tuple_type: type, **kwargs) -> List[namedtuple]:
        """
            Load the definition of how to create filters.

            This method retrieves the definition of how to create filters and returns it as a list of named tuples.
            Each named tuple is built with the provided `tuple_type` and has the fields `field`, `filter`, and `value`.

            Example named tuple: <Type>(field=<str>, filter=<str>, value=<str>)
            Example usage: BenefitPlan(field='income', filter='lt, gte, icontains, exact', value='')

            Args:
                tuple_type (type): The type of the named tuple.

            Returns:
                List[namedtuple]: A list of named tuples representing the definition of how to create filters.
        """
        pass
