import functools
from datetime import datetime
from django.db.models import Q
from django.http import JsonResponse
from django.contrib.contenttypes.models import ContentType
from .models import UserBusinessAccess


def check_authentication(access_requirements=None):
    """
    Decorator to check user authentication and business access permissions.

    Args:
        access_requirements: Optional list of [content_type_label, object_id] pairs
                           e.g. [['myapp.mymodel', some_uuid], ['otherapp.othermodel', other_id]]

    Usage:
        @check_authentication()
        def my_view(request): ...

        @check_authentication(access_requirements=[['myapp.mymodel', some_uuid]])
        def my_view(request): ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            # 1. Basic authentication check
            if not getattr(request, 'user', None) or not request.user.is_authenticated:
                return JsonResponse({'error': 'Authentication required'}, status=401)

            # 2. Business access check
            if access_requirements:
                now = datetime.now()
                for content_type_label, object_id in access_requirements:
                    app_label, model_name = content_type_label.rsplit('.', 1)
                    try:
                        ct = ContentType.objects.get(app_label=app_label, model=model_name.lower())
                    except ContentType.DoesNotExist:
                        return JsonResponse({'error': f'Invalid content type: {content_type_label}'}, status=400)

                    has_access = UserBusinessAccess.objects.filter(
                        user=request.user,
                        content_type=ct,
                        object_id=str(object_id),
                        active=True,
                        date_valid_from__lte=now,
                    ).filter(
                        Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=now)
                    ).exists()

                    if not has_access:
                        return JsonResponse({'error': 'Forbidden'}, status=403)

            return func(request, *args, **kwargs)
        return wrapper
    return decorator