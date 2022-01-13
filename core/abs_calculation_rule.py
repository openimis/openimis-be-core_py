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
    def get_type(cls):
        return type(cls)._type

    @classmethod
    def set_type(cls, val):
        type(cls)._type = val

    type = property(get_type, set_type)

    @classmethod
    def get_sub_type(cls):
        return type(cls)._sub_type

    @classmethod
    def set_sub_type(cls, val):
        type(cls)._sub_type = val

    sub_type = property(get_sub_type, set_sub_type)

    @classmethod
    def get_from_to(cls):
        return type(cls)._from_to

    @classmethod
    def set_from_to(cls, val):
        type(cls)._from_to = val

    from_to = property(get_from_to, set_from_to)

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
    def active_for_object(cls, instance, context, type, sub_type):
        return

    @classmethod
    @abc.abstractmethod
    def calculate(cls, instance, *args, **kwargs):
        return

    @classmethod
    @abc.abstractmethod
    def get_linked_class(cls, sender, class_name, **kwargs):
        return

    @classmethod
    @abc.abstractmethod
    def convert(cls, instance, convert_to, **kwargs):
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
        if list_class:
            if len(list_class) > 0:
                rule_details = cls.get_rule_details(class_name=list_class[0], sender=sender)
                if rule_details or len(cls.impacted_class_parameter) == 0:
                    if cls.active_for_object(instance=instance, context=context):
                        # add context to kwargs
                        kwargs["context"] = context
                        result = cls.calculate(instance, **kwargs)
                        return result

    @classmethod
    def run_convert(cls, instance, convert_to, **kwargs):
        """
            execute the conversion for the instance with the first
            rule that provide the conversion (see get_convert_from_to)
        """
        convert_from = instance.__class__.__name__
        if convert_from == "Contract":
            convert_from = "ContractContributionPlanDetails"
        list_possible_conversion = cls.get_convert_from_to()
        for possible_conversion in list_possible_conversion:
            if convert_from == possible_conversion['from'] and convert_to == possible_conversion['to']:
                result = cls.convert(instance=instance, convert_to=convert_to, **kwargs)
                return result

    @classmethod
    def get_convert_from_to(cls):
        """
            get the possible conversion, return [calc UUID, from, to]
        """
        list_possible_conversion = []
        for ft in cls.from_to:
            convert_from_to = {'calc_uuid': cls.uuid, 'from': ft['from'], 'to': ft['to']}
            list_possible_conversion.append(convert_from_to)
        return list_possible_conversion
