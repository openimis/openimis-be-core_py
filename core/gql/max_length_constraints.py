# core/gql/max_length_constraints.py

from graphene.types.generic import GenericScalar
import graphene
from django.apps import apps

# Registered form fields: {module: {form: {gql_field: ("app_label.Model", model_field)}}}.
# Each module registers its own forms, from its AppConfig.ready(). Models are named,
# not imported, and resolved at query time: importing the models of an app that is
# not in INSTALLED_APPS raises RuntimeError (OP-3347).
MAX_LENGTH_CONSTRAINTS_FIELDS = {}
_defaults_registered = False


def register_max_length_fields(module, forms, app_label=None):
    """Register the max_length form fields of a module.

    Skipped when app_label is given and that app is not installed, so a module can
    declare fields for an optional app without importing it.
    """
    if app_label and not apps.is_installed(app_label):
        return
    MAX_LENGTH_CONSTRAINTS_FIELDS.setdefault(module, {}).update(forms)


def _register_default_fields():
    global _defaults_registered
    if _defaults_registered:
        return
    _defaults_registered = True
    register_max_length_fields("admin", {
        "user": {
            "username": ("core.User", "username"),
            "lastName": ("core.InteractiveUser", "last_name"),
            "otherNames": ("core.InteractiveUser", "other_names"),
            "phone": ("core.InteractiveUser", "phone"),
            "email": ("core.InteractiveUser", "email"),
        },
    })


def get_model(model_label):
    """Look up a model from its "app_label.Model" label."""
    try:
        return apps.get_model(model_label)
    except LookupError:
        return None


def build_max_length_constraints():
    _register_default_fields()
    constraints = {}

    for module_name, forms in MAX_LENGTH_CONSTRAINTS_FIELDS.items():
        module_constraints = {}

        for form_name, fields in forms.items():
            form_constraints = {}

            for field_name, (model_label, model_field_name) in fields.items():
                model = get_model(model_label)
                if model is None:
                    continue

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
