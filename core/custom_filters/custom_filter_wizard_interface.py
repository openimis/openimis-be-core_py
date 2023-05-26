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
        """Load the definition how to create filters"""
        """
            Load the definition how to create filters

            :param tuple_type: the type of tuple
             
            :return: List[namedtuple]
        """
        pass
