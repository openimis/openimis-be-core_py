# core/gql/max_length_constraints.py

from graphene.types.generic import GenericScalar
import graphene
from django.apps import apps

try:
    from insuree.models import Insuree
except ImportError:
    Insuree = None


def get_model(model_name):
    """Récupère un modèle à partir de son nom."""
    try:
        return apps.get_model('core', model_name)
    except LookupError:
        return None


MAX_LENGTH_CONSTRAINTS_FIELDS = {
    "admin": {
        "user": {
            "username": ("User", "username"),
            "lastName": ("InteractiveUser", "last_name"),
            "otherNames": ("InteractiveUser", "other_names"),
            "phone": ("InteractiveUser", "phone"),
            "email": ("InteractiveUser", "email"),
        },
    },
}

if Insuree:
    MAX_LENGTH_CONSTRAINTS_FIELDS["insuree"] = {
        "insuree": {
            "uuid": (Insuree, "uuid"),
            "chfId": (Insuree, "chf_id"),
            "lastName": (Insuree, "last_name"),
            "otherNames": (Insuree, "other_names"),
            "marital": (Insuree, "marital"),
            "passport": (Insuree, "passport"),
            "phone": (Insuree, "phone"),
            "email": (Insuree, "email"),
            "currentAddress": (Insuree, "current_address"),
            "geolocation": (Insuree, "geolocation"),
            "status": (Insuree, "status"),
        },
    }


def build_max_length_constraints():
    constraints = {}

    for module_name, forms in MAX_LENGTH_CONSTRAINTS_FIELDS.items():
        module_constraints = {}

        for form_name, fields in forms.items():
            form_constraints = {}

            for field_name, (model_or_name, model_field_name) in fields.items():
                if isinstance(model_or_name, str):
                    model = get_model(model_or_name)
                    if model is None:
                        continue
                else:
                    model = model_or_name

                try:
                    field = model._meta.get_field(model_field_name)
                    if field.max_length:
                        form_constraints[field_name] = field.max_length
                except Exception:
                    continue

            if form_constraints:
                module_constraints[form_name] = form_constraints

        if module_constraints:
            constraints[module_name] = module_constraints

    return constraints


class MaxLengthConstraintsGQLType(graphene.ObjectType):
    """
    Returns max_length constraints used by the frontend to enforce field length
    limits in supported forms.
    """
    constraints = GenericScalar()

    @staticmethod
    def resolve_constraints(root, info):
        return build_max_length_constraints()
