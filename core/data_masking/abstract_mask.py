from abc import ABC


class DataMaskAbs(ABC):
    anon_fields = []
    masking_model = None
    enabled = False

    def apply_mask(self, data):
        for field in self.anon_fields:
            field_parts = field.split('.')
            self._anonymize_nested_field(data, field_parts)
        return data

    def anonymize(self, value):
        if isinstance(value, str):
            result = '***************'
            return result
        elif isinstance(value, (int, float)):
            return 0
        elif isinstance(value, dict):
            return {k: self.anonymize(v) for k, v in value.items()}
        return value

    def _anonymize_nested_field(self, obj, field_parts):
        if len(field_parts) == 1:
            field_name = field_parts[0]
            if hasattr(obj, field_name):
                setattr(obj, field_name, self.anonymize(getattr(obj, field_name)))
                return obj
        else:
            field_name = field_parts[0]
            remaining_parts = field_parts[1:]
            if hasattr(obj, field_name):
                nested_obj = getattr(obj, field_name)
                if isinstance(nested_obj, dict):
                    self._anonymize_dict_field(nested_obj, remaining_parts)
                else:
                    self._anonymize_nested_field(nested_obj, remaining_parts)

    def _anonymize_dict_field(self, dictionary, field_parts):
        if len(field_parts) == 1:
            field_name = field_parts[0]
            if field_name in dictionary:
                dictionary[field_name] = self.anonymize(dictionary[field_name])
        else:
            field_name = field_parts[0]
            remaining_parts = field_parts[1:]
            if field_name in dictionary:
                nested_dict = dictionary[field_name]
                if isinstance(nested_dict, dict):
                    self._anonymize_dict_field(nested_dict, remaining_parts)
