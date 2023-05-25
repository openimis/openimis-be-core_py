from collections import namedtuple
from typing import List


class CustomFilterWizardInterface:
    def get_type_of_object(self) -> str:
        """get the type of object - the actor of such filtering action"""
        pass

    def load_definition(self, tuple_type: type) -> List[namedtuple]:
        """Load the definition of the object in order to retrieve how to create filters"""
        pass
