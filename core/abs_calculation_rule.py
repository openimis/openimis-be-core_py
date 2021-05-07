import abc


class AbsCalculationRule(object,  metaclass=abc.ABCMeta):

    @classmethod
    def get_version(cls):
        return type(cls)._version

    @classmethod
    def set_version(cls, val):
        type(cls)._version = val

    version = property(get_version, set_version)

    @classmethod
    def get_uuid(cls):
        return type(cls)._uuid

    @classmethod
    def set_uuid(cls, val):
        type(cls)._uuid = val

    uuid = property(get_uuid, set_uuid)

    @classmethod
    def get_calculation_rule_name(cls):
        return type(cls)._calculation_rule_name

    @classmethod
    def set_calculation_rule_name(cls, val):
        type(cls)._calculation_rule_name = val

    calculation_rule_name = property(get_calculation_rule_name, set_calculation_rule_name)

    @classmethod
    def get_description(cls):
        return type(cls)._description

    @classmethod
    def set_description(cls, val):
        type(cls)._description = val

    description = property(get_description, set_description)

    @classmethod
    def get_impacted_class_parameter(cls):
        return type(cls)._impacted_class_parameter

    @classmethod
    def set_impacted_class_parameter(cls, val):
        type(cls)._impacted_class_parameter = val

    impacted_class_parameter = property(get_impacted_class_parameter, set_impacted_class_parameter)

    @classmethod
    @abc.abstractmethod
    def ready(cls):
        return

    @classmethod
    @abc.abstractmethod
    def check_calculation(cls, instance):
        return

    @classmethod
    @abc.abstractmethod
    def active_for_object(cls, instance, context):
        return

    @classmethod
    @abc.abstractmethod
    def calculate(cls, instance, *args):
        return

    @classmethod
    @abc.abstractmethod
    def get_linked_class(cls, sender, class_name, **kwargs):
        return

    @classmethod
    def get_rule_name(cls, sender, class_name, **kwargs):
        for object_class in cls.impacted_class_parameter:
            if object_class["class"] == class_name:
                return cls

    @classmethod
    def get_rule_details(cls, sender, class_name, **kwargs):
        for object_class in cls.impacted_class_parameter:
            if object_class["class"] == class_name:
                return object_class

    @classmethod
    def get_parameters(cls, sender, class_name, instance, **kwargs):
        """
            class_name is the class name of the object where the calculation param need to be added
            instance is where the link with a calculation need to be found,
            like the CPB in case of PH insuree or Contract Details
            return a list only with rule details that matches step 1 and 2
        """
        rule_details = cls.get_rule_details(sender=sender, class_name=class_name)
        if rule_details:
            if cls.check_calculation(instance=instance):
                return rule_details["parameters"] if "parameters" in rule_details else []

    @classmethod
    def run_calculation_rules(cls, sender, instance, user, context, **kwargs):
        """
            this function will send a signal and the rules will
            reply if they have object matching the classname in their list of object
        """
        list_class = cls.get_linked_class(sender=sender, class_name=instance.__class__.__name__)
        if len(list_class) > 0:
            rule_details = cls.get_rule_details(class_name=list_class[0], sender=sender)
            if rule_details:
                if cls.active_for_object(instance=instance, context=context):
                    result = cls.calculate(instance=instance)
                    return result
