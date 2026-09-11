import json

from cryptography.hazmat.primitives.asymmetric import rsa
from django.http import Http404, StreamingHttpResponse
from django.views.decorators.http import require_GET
from isodate import strftime
from jwt.algorithms import RSAAlgorithm
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .auth import keys
from .models import User, ExportableQueryModel
from .scheduler import scheduler
from .serializers import UserSerializer
from django.utils.translation import gettext as _


def check_user_rights(rights):
    class UserWithRights(IsAuthenticated):
        def has_permission(self, request, view):
            return super().has_permission(request, view) and request.user.has_perms(
                rights
            )

    return UserWithRights


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    # If we don't specify the IsAuthenticated, the framework will look for the core.user_view permission and prevent
    # any access from non-admin users
    permission_classes = [IsAuthenticated]

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


@api_view(["GET"])
@require_GET
def get_scheduled_jobs(request):
    return Response([_serialize_job(job) for job in scheduler.get_jobs()])


def _public_key(key):
    """A verification key reaches the mapping either as a key object or as PEM
    text, and PyJWT accepts both. A symmetric secret is neither, and publishing
    one here would disclose it.
    """
    if isinstance(key, rsa.RSAPublicKey):
        return key
    if not isinstance(key, (str, bytes)):
        return None
    try:
        prepared = RSAAlgorithm(RSAAlgorithm.SHA256).prepare_key(key)
    except (ValueError, TypeError):
        return None
    # A private key here is a misconfiguration; drop it rather than publish its
    # public half from a mapping that should only ever hold verification keys.
    return prepared if isinstance(prepared, rsa.RSAPublicKey) else None


def _jwk(kid, public_key):
    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    # to_jwk emits key_ops, which the RFC 7638 thumbprint is not defined over;
    # dropped for the same reason keys.derive_kid drops it.
    jwk.pop("key_ops", None)
    return {**jwk, "kid": kid, "use": "sig", "alg": keys.algorithm()}


@api_view(["GET"])
# Emptied, not just AllowAny: JWTAuthentication is a DRF default, so a malformed
# Authorization header would otherwise 401 an endpoint that must stay public.
@authentication_classes([])
@permission_classes([AllowAny])
def jwks(request):
    published = []
    for kid, key in keys.deployment_keys().items():
        public_key = _public_key(key)
        if public_key is not None:
            published.append(_jwk(kid, public_key))
    return Response({"keys": published})
