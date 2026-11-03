from django.http import Http404, StreamingHttpResponse
from django.views.decorators.http import require_GET
from isodate import strftime
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import User, ExportableQueryModel
from .scheduler import scheduler
from .serializers import UserSerializer
from django.utils.translation import gettext as _


def check_user_rights(rights):
    """Permission class requiring `rights` on top of authentication.

    `rights` may be a list, or a zero-argument callable returning one. The
    callable form exists for module-level decorators: `CoreConfig` cannot be
    imported at the top of this file (circular import), and a decorator is
    evaluated at import time, so the right has to be looked up on each request
    instead of being captured.
    """

    class UserWithRights(IsAuthenticated):
        def has_permission(self, request, view):
            wanted = rights() if callable(rights) else rights
            return super().has_permission(request, view) and request.user.has_perms(
                wanted
            )

    return UserWithRights


def _core_right(attr):
    """Late lookup of a `CoreConfig` right, for use in module-level decorators."""

    def resolve():
        from core.apps import CoreConfig

        return getattr(CoreConfig, attr)

    return resolve


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    # The right depends on the action. `IsAuthenticated` alone - what used to be
    # here - opened a full ModelViewSet on `core.User` to every authenticated
    # account: the list of all accounts for reading, and above all a PATCH on
    # one's own row, `is_superuser` being serialised as writable. That was a
    # direct privilege escalation, bypassing what `UpdateUserMutation` protects on
    # the GraphQL side.
    #
    # `current_user` stays open to any authenticated caller: it only returns the
    # caller's own row, and the frontend uses it on every login.
    _ACTION_RIGHTS = {
        "list": "gql_query_users_perms",
        "retrieve": "gql_query_users_perms",
        "create": "gql_mutation_create_users_perms",
        "update": "gql_mutation_update_users_perms",
        "partial_update": "gql_mutation_update_users_perms",
        "destroy": "gql_mutation_delete_users_perms",
    }

    def get_permissions(self):
        from core.apps import CoreConfig

        right_attr = self._ACTION_RIGHTS.get(getattr(self, "action", None))
        if right_attr is None:
            return [IsAuthenticated()]
        return [check_user_rights(getattr(CoreConfig, right_attr))()]

    @action(detail=False)
    def current_user(self, request):
        serializer = self.get_serializer(request.user, many=False)
        return Response(serializer.data)


@api_view(["GET"])
@require_GET
def fetch_export(request):
    requested_export = request.query_params.get("export")
    export = ExportableQueryModel.objects.filter(name=requested_export).first()
    if not export:
        raise Http404
    elif export.user != request.user:
        raise PermissionDenied(
            {"message": _("Only user requesting export can fetch request")}
        )
    elif export.is_deleted:
        return Response(
            data="Export csv file was removed from server.", status=status.HTTP_410_GONE
        )

    export_file_name = f"export_{export.model}_{strftime(export.create_date, '%d_%m_%Y')}.{export.file_format}"
    if export.file_format == ExportableQueryModel.FileFormat.CSV:
        response = StreamingHttpResponse(
            open(export.content.path, "rb"),
            content_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{export_file_name}"'
            },
        )
    elif ExportableQueryModel.FileFormat.XLSX:
        response = StreamingHttpResponse(
            open(export.content.path, "rb"),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{export_file_name}"'
            },
        )
    else:
        return Response(
            data="Unsupported file format.", status=status.HTTP_400_BAD_REQUEST
        )

    return response


def _serialize_job(job):
    return "name: %s, trigger: %s, next run: %s, handler: %s" % (
        job.name,
        job.trigger,
        job.next_run_time,
        job.func,
    )


# New right (900201). The endpoint had no `permission_classes` at all, and the
# assembly defines no `DEFAULT_PERMISSION_CLASSES`: so it resolved to `AllowAny`.
# An anonymous caller got the name, the trigger, the next run and the **handler
# import path** of every scheduled job.
@api_view(["GET"])
@require_GET
@permission_classes([check_user_rights(_core_right("gql_query_scheduled_jobs_perms"))])
def get_scheduled_jobs(request):
    return Response([_serialize_job(job) for job in scheduler.get_jobs()])
