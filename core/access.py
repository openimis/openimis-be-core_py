import logging
from datetime import datetime

from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import JsonResponse

from core.utils import (
    get_business_access_cache,
    get_content_type_cache,
    get_current_user,
    is_authentication_checked,
    set_authentication_checked,
)
from core.models.user_business_access import UserBusinessAccess

logger = logging.getLogger(__name__)

SERVICE_AUTH_ERROR = {
    "success": False,
    "message": "Authentication required",
    "detail": "PermissionDenied",
}

SERVICE_PERMISSION_ERROR = {
    "success": False,
    "message": "Permissions required",
    "detail": "PermissionDenied",
}

# Shared format for business access checks:
#   [content_type_label, object_id]
#   [content_type_label, object_id, [perm_ids...]]
ACCESS_REQUIREMENT_FORMAT = (
    "List of [content_type_label, object_id] or "
    "[content_type_label, object_id, [perm_ids...]] entries, "
    "where content_type_label is 'app_label.modelname'."
)


def is_core_user(obj):
    """Detect openIMIS core.User without importing User (avoids circular imports)."""
    if obj is None or isinstance(obj, AnonymousUser):
        return False

    meta = getattr(obj, "_meta", None)
    if meta is not None:
        return getattr(meta, "label_lower", None) == "core.user"

    cls = type(obj)
    return (
        cls.__name__ == "User"
        and cls.__module__.endswith(".models.user")
        and hasattr(obj, "has_perms")
    )


def is_authenticated_user(user):
    return is_core_user(user) and getattr(user, "id", None)


def is_http_request(obj):
    return hasattr(obj, "META") and hasattr(obj, "method")


def resolve_user(user_param, args, kwargs):
    if is_core_user(user_param):
        return user_param

    resolved_user = get_current_user()
    if resolved_user:
        return resolved_user
    if callable(user_param):
        resolved = user_param(*args, **kwargs)
        if resolved:
            return resolved
    elif user_param is not None and isinstance(user_param, str) and args:
        resolved = getattr(args[0], user_param, None)
        if resolved:
            return resolved

    if args and hasattr(args[0], "user") and not is_http_request(args[0]):
        instance = args[0]
        if instance.user:
            return instance.user

    return None


def parse_access_requirement(requirement):
    if not requirement or len(requirement) < 2:
        return None, None, None

    content_type_label = requirement[0]
    object_id = requirement[1]
    perms = requirement[2] if len(requirement) > 2 else None
    return content_type_label, object_id, perms


def _content_type_cache_key(content_type_label=None, *, app_label=None, business_object=None):
    if business_object is not None:
        return ("model", business_object.__class__.__module__, business_object.__class__.__name__)
    if isinstance(content_type_label, ContentType):
        return ("pk", content_type_label.pk)
    if content_type_label is None:
        return None

    label = str(content_type_label)
    if app_label:
        return ("label", app_label, label.rsplit(".", 1)[-1].lower())
    if "." in label:
        app_label, model_name = label.rsplit(".", 1)
        return ("label", app_label, model_name.lower())
    return ("model_name", label.lower())


def _business_access_cache_key(user, content_type, object_id):
    user_id = getattr(user, "pk", None) or getattr(user, "id", None)
    return (user_id, content_type.pk, str(object_id))


def resolve_content_type(content_type_label=None, *, app_label=None, business_object=None):
    if business_object is not None:
        cache_key = _content_type_cache_key(business_object=business_object)
    elif isinstance(content_type_label, ContentType):
        return content_type_label
    elif content_type_label is None:
        return None
    else:
        cache_key = _content_type_cache_key(content_type_label, app_label=app_label)

    if cache_key is not None:
        content_type_cache = get_content_type_cache()
        if cache_key in content_type_cache:
            return content_type_cache[cache_key]

    if business_object is not None:
        content_type = ContentType.objects.get_for_model(business_object.__class__)
    elif isinstance(content_type_label, ContentType):
        content_type = content_type_label
    else:
        label = str(content_type_label)
        if app_label:
            model_name = label.rsplit(".", 1)[-1]
            content_type = ContentType.objects.filter(
                app_label=app_label,
                model=model_name.lower(),
            ).first()
        elif "." in label:
            app_label, model_name = label.rsplit(".", 1)
            content_type = ContentType.objects.filter(
                app_label=app_label,
                model=model_name.lower(),
            ).first()
        else:
            content_type = ContentType.objects.filter(model__iexact=label.lower()).first()

    if cache_key is not None and content_type is not None:
        content_type_cache[cache_key] = content_type
    return content_type


def has_business_access(user, *, content_type=None, object_id=None, business_object=None, now=None):
    if not user:
        return False

    if business_object is not None:
        content_type = resolve_content_type(business_object=business_object)
        object_id = str(business_object.pk)

    if not content_type or object_id is None:
        return False

    cache_key = _business_access_cache_key(user, content_type, object_id)
    business_access_cache = get_business_access_cache()
    if cache_key in business_access_cache:
        return business_access_cache[cache_key]

    now = now or datetime.now()
    has_access = UserBusinessAccess.objects.filter(
        user=user,
        content_type=content_type,
        object_id=str(object_id),
        active=True,
        date_valid_from__lte=now,
    ).filter(
        Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=now)
    ).exists()
    business_access_cache[cache_key] = has_access
    return has_access


def has_role_perms(user, perm_list, *, list_evaluation_or=True):
    if getattr(user, "is_superuser", False) or not perm_list:
        return True
    if list_evaluation_or:
        return any(user.has_perm(perm) for perm in perm_list)
    return all(user.has_perm(perm) for perm in perm_list)


def satisfies_access_requirement(user, requirement, *, now=None):
    content_type_label, object_id, perms = parse_access_requirement(requirement)
    if not content_type_label:
        return False

    if perms and not has_role_perms(user, perms):
        return False

    app_label, model_name = content_type_label.rsplit(".", 1)
    content_type = resolve_content_type(model_name, app_label=app_label)
    if not content_type:
        logger.error("Invalid content type: %s", content_type_label)
        return False

    return has_business_access(
        user,
        content_type=content_type,
        object_id=object_id,
        now=now,
    )


def evaluate_access_requirements(user, access_requirements, *, match_all=False, now=None):
    if not access_requirements:
        return True

    now = now or datetime.now()
    results = [
        satisfies_access_requirement(user, requirement, now=now)
        for requirement in access_requirements
    ]
    return all(results) if match_all else any(results)


def user_has_permissions(
    user,
    permissions,
    *,
    access_requirements=None,
    list_evaluation_or=True,
):
    if not is_authenticated_user(user):
        return False
    return user.has_perms(
        permissions,
        access_requirements=access_requirements,
        list_evaluation_or=list_evaluation_or,
    )


def authentication_error(for_view=False):
    if for_view:
        return JsonResponse({"error": "Authentication required"}, status=401)
    return SERVICE_AUTH_ERROR


def permission_error(for_view=False):
    if for_view:
        return JsonResponse({"error": "Forbidden"}, status=403)
    return SERVICE_PERMISSION_ERROR


def guard_user_access(
    *,
    user_param,
    args,
    kwargs,
    for_view=False,
    require_auth=True,
    permissions=None,
    access_requirements=None,
    list_evaluation_or=True,
):
    resolved_user = resolve_user(user_param, args, kwargs)

    if require_auth and not is_authentication_checked():
        if not is_authenticated_user(resolved_user):
            return authentication_error(for_view)
        set_authentication_checked()

    if permissions is not None:
        if not user_has_permissions(
            resolved_user,
            permissions,
            access_requirements=access_requirements,
            list_evaluation_or=list_evaluation_or,
        ):
            return permission_error(for_view)
    elif access_requirements:
        if not evaluate_access_requirements(
            resolved_user,
            access_requirements,
            match_all=True,
        ):
            return permission_error(for_view)

    return None
