from collections import namedtuple
from typing import List


class CustomFilterWizardInterface:
    def get_type_of_object(self) -> str:
        """
            Get the type of object from which we want to define
            specific way of building filters

            :return: str
        """
        pass

    def load_definition(self, tuple_type: type) -> List[namedtuple]:
        """
            Load the definition how to create filters. The output is simply the list
            of named tuple (from collections package). Such named tuple is built in such way:
            <Type>(field=<str>, filter=<str>, value=<str>) for example:
            BenefitPlan(field='income', filter='lt, gte, icontains, exact', value='')

            :param tuple_type: the type of tuple
             
            :return: List[namedtuple]
        """
        pass
