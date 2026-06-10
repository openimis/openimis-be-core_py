import functools
from datetime import datetime

from django.db.models import Model
from django.http import JsonResponse
from django.contrib.contenttypes.models import ContentType

from .models import UserBusinessAccess


def _resolve_content_type(model):
    if isinstance(model, ContentType):
        return model
    if isinstance(model, type) and issubclass(model, Model):
        return ContentType.objects.get_for_model(model)
    if isinstance(model, str):
        app_label, model_name = model.rsplit('.', 1)
        return ContentType.objects.get(app_label=app_label, model=model_name.lower())
    raise ValueError(f'Invalid model: {model!r}')


def _normalize_ids(ids):
    if ids is None:
        return []
    if isinstance(ids, (list, tuple, set)):
        return [str(object_id) for object_id in ids if object_id is not None]
    return [str(ids)]


def _normalize_link_type(link_type):
    if link_type in (None, ''):
        return None
    if isinstance(link_type, (list, tuple, set)):
        values = [str(value) for value in link_type if value not in (None, '')]
        return values or None
    return str(link_type)


def _parse_business_requirement(requirement):
    """
    Parse a business requirement into (model, object_ids, link_type).

    Supported shapes:
      - [Model, [ids], link_type?]
      - {'model': Model, 'ids': [ids], 'link_type': link_type?}
      - ['app.model', object_id]  (legacy)
    """
    if isinstance(requirement, dict):
        model = requirement.get('model')
        ids = _normalize_ids(requirement.get('ids'))
        link_type = _normalize_link_type(requirement.get('link_type'))
        return model, ids, link_type

    if not isinstance(requirement, (list, tuple)) or len(requirement) < 2:
        raise ValueError(f'Invalid business requirement: {requirement!r}')

    model = requirement[0]
    second = requirement[1]

    # Legacy: ['app.model', object_id]
    if len(requirement) == 2 and not isinstance(second, (list, tuple, set)):
        return model, _normalize_ids(second), None

    ids = _normalize_ids(second)
    link_type = _normalize_link_type(requirement[2]) if len(requirement) >= 3 else None
    return model, ids, link_type


def _user_has_business_access(user, model, object_ids, link_type=None, validity=None):
    if not object_ids:
        return False

    now = validity or datetime.now()
    try:
        content_type = _resolve_content_type(model)
    except ContentType.DoesNotExist:
        return None
    except ValueError:
        return None

    queryset = UserBusinessAccess.objects.filter(
        user=user,
        content_type=content_type,
        object_id__in=object_ids,
        **UserBusinessAccess.filter_validity(validity=now),
    ).filter(
        UserBusinessAccess.filter_validity_q(validity=now)
    )

    if link_type is not None:
        if isinstance(link_type, list):
            queryset = queryset.filter(link_type__in=link_type)
        else:
            queryset = queryset.filter(link_type=link_type)

    return queryset.exists()


def check_authentication(business_requirements=None, access_requirements=None):
    """
    Decorator to check user authentication and business access permissions.

    Args:
        business_requirements: Optional list of business access rules. Each rule is either:
            - [Model, [ids], link_type?]
            - {'model': Model, 'ids': [ids], 'link_type': link_type?}
          where Model is a Django model class or 'app.model' label, ids is a list of
          object identifiers, and link_type is an optional UserBusinessAccess link_type.
          The user must satisfy every rule (AND). For each rule, access to any id is enough (OR).
        access_requirements: Deprecated alias for business_requirements.

    Usage:
        @check_authentication()
        def my_view(request): ...

        @check_authentication(business_requirements=[[HealthFacility, [hf_uuid], 'ca']])
        def my_view(request): ...
    """
    requirements = (
        business_requirements
        if business_requirements is not None
        else access_requirements
    )

    def decorator(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            # 1. Basic authentication check
            if not getattr(request, 'user', None) or not request.user.is_authenticated:
                return JsonResponse({'error': 'Authentication required'}, status=401)
            # 2. Business access check
            if requirements:
                for requirement in requirements:
                    try:
                        model, object_ids, link_type = _parse_business_requirement(requirement)
                    except ValueError as exc:
                        return JsonResponse({'error': str(exc)}, status=400)

                    has_access = _user_has_business_access(
                        request.user,
                        model,
                        object_ids,
                        link_type=link_type,
                    )
                    if has_access is None:
                        return JsonResponse({'error': f'Invalid content type: {model}'}, status=400)
                    if not has_access:
                        return JsonResponse({'error': 'Forbidden'}, status=403)

            return func(request, *args, **kwargs)
        return wrapper
    return decorator