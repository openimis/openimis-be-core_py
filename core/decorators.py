import functools

from core.access import guard_user_access, is_http_request


def check_authentication(_func=None, *, user=None, access_requirements=None):
    """
    Decorator to check user authentication and optional business access permissions.

    User resolution order:
      1. explicit ``user`` argument (instance, attribute name, or callable)
      2. ``self.user`` on service instances (falls back to thread-local user)
      3. ``get_current_user()`` thread-local fallback

    ``access_requirements`` format:
      - ``[content_type_label, object_id]``
      - ``[content_type_label, object_id, [perm_ids...]]``
      where ``content_type_label`` is ``app_label.modelname``.
      All listed requirements must be satisfied.

    Usage:
        @check_authentication
        def create(self, obj_data): ...

        @check_authentication(access_requirements=[['myapp.mymodel', some_uuid]])
        def my_view(request): ...

    Authentication is cached per thread for the duration of a request and cleared
    at the next GraphQL/HTTP call by ClearUserContextMiddleware.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for_view = bool(args) and is_http_request(args[0])
            error = guard_user_access(
                user_param=user,
                args=args,
                kwargs=kwargs,
                for_view=for_view,
                access_requirements=access_requirements,
            )
            if error:
                return error
            return fn(*args, **kwargs)

        return wrapper

    if _func is not None:
        return decorator(_func)
    return decorator


def check_permissions(
    permissions,
    _func=None,
    *,
    user=None,
    access_requirements=None,
    list_evaluation_or=True,
):
    """
    Decorator to check role permissions via ``user.has_perms``.

    Uses the same user resolution, thread-local auth cache, and
    ``access_requirements`` format as ``check_authentication``.

    When standard permissions fail, ``access_requirements`` is evaluated as a
    fallback (any matching requirement grants access), matching ``user.has_perms``.

    Usage:
        @check_permissions(ContractConfig.gql_mutation_create_contract_perms)
        def create(self, contract): ...

        @check_permissions(
            ContractConfig.gql_mutation_create_contract_perms,
            access_requirements=[['policyholder.policyholder', policyholder_id]],
        )
        def create(self, contract): ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for_view = bool(args) and is_http_request(args[0])
            error = guard_user_access(
                user_param=user,
                args=args,
                kwargs=kwargs,
                for_view=for_view,
                permissions=permissions,
                access_requirements=access_requirements,
                list_evaluation_or=list_evaluation_or,
            )
            if error:
                return error
            return fn(*args, **kwargs)

        return wrapper

    if _func is not None:
        return decorator(_func)
    return decorator
