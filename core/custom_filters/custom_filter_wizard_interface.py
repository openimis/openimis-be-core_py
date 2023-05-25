from typing import List, Tuple


class CustomFilterWizardInterface:
    def get_type_of_object(self) -> type:
        """get the type of object - the actor of such filtering action"""
        pass

    def load_definition(self) -> List[Tuple]:
        """Load the definition of the object in order to retrieve how to create filters"""
        pass
