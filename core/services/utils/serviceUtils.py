import json
from typing import Union

from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict
from core.decorators import (  # noqa: F401
    check_authentication,
    check_permissions,
)
from core.service_errors import ServiceError


def model_representation(model):
    uuid_string = str(model.id)
    dict_representation = model_to_dict(model)
    dict_representation["id"], dict_representation["uuid"] = (
        str(uuid_string),
        str(uuid_string),
    )
    return dict_representation


def output_exception(model_name, method, exception):
    # Same payload as before plus a "code" derived from the exception type; see
    # core.service_errors for why the shape is kept and what it unlocks.
    return ServiceError.from_exception(
        exception, message=f"Failed to {method} {model_name}"
    ).as_dict()


def output_result_success(dict_representation):
    return {
        "success": True,
        "message": "Ok",
        "detail": "",
        "data": json.loads(json.dumps(dict_representation, cls=DjangoJSONEncoder)),
    }


def build_delete_instance_payload():
    return {
        "success": True,
        "message": "Ok",
        "detail": "",
    }


def get_generic_type(generic_type: Union[str, ContentType]):
    if isinstance(generic_type, ContentType):
        return generic_type
    return ContentType.objects.get(model__iexact=str(generic_type).lower())
