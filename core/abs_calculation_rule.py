import abc


class AbsCalculationRule(object,  metaclass=abc.ABCMeta):

    def __init__(self, status):
        self.status = status

    def get_version(self):
        return type(self)._version

    def set_version(self, val):
        type(self)._version = val

    version = property(get_version, set_version)

    def get_uuid(self):
        return type(self)._uuid

    def set_uuid(self, val):
        type(self)._uuid = val

    uuid = property(get_uuid, set_uuid)

    def get_calculation_rule_name(self):
        return type(self)._calculation_rule_name

    def set_calculation_rule_name(self, val):
        type(self)._calculation_rule_name = val

    calculation_rule_name = property(get_calculation_rule_name, set_calculation_rule_name)

    def get_description(self):
        return type(self)._description

    def set_description(self, val):
        type(self)._description = val

    description = property(get_description, set_description)

    def get_impacted_class_parameter(self):
        return type(self)._impacted_class_parameter

    def set_impacted_class_parameter(self, val):
        type(self)._impacted_class_parameter = val

    impacted_class_parameter = property(get_impacted_class_parameter, set_impacted_class_parameter)

    @abc.abstractmethod
    def ready(self):
        return

    @abc.abstractmethod
    def check_calculation(self, instance):
        return

    @abc.abstractmethod
    def active_for_object(self, object_class, context):
        return

    @abc.abstractmethod
    def calculate_event(self, sender, instance, user, **kwargs):
        return

    @abc.abstractmethod
    def calculate(self, instance, *args):
        return

    @abc.abstractmethod
    def get_linked_class(self, list_class_names):
        return

    def get_rule_details(self, class_name):
        for object_class in self.impacted_class_parameter:
            if object_class["class"] == class_name:
                return object_class

    def get_parameters(self, class_name, instance):
        """
            class_name is the class name of the object where the calculation param need to be added
            instance is where the link with a calculation need to be found,
            like the CPB in case of PH insuree or Contract Details
            return a list only with rule details that matches step 1 and 2
        """
        rule_details = self.get_rule_details(class_name=class_name)
        if rule_details:
            if self.check_calculation(instance=instance):
                return rule_details["parameters"] if "parameters" in rule_details else []

    def run_calculation_rules(self, instance, context):
        """
            this function will send a signal and the rules will
            reply if they have object matching the classname in their list of object
        """
        self.ready()
        rule_details = self.get_rule_details(class_name=instance.__class__)
        if self.active_for_object(object_class=rule_details, context=context):
            self.calculate(instance=instance)
