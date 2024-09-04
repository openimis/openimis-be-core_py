import csv

from django.http import Http404, StreamingHttpResponse
from django.views.decorators.http import require_GET
from isodate import strftime
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import User, ExportableQueryModel
from .scheduler import scheduler
from .serializers import UserSerializer
from django.utils.translation import gettext as _


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


@api_view(['GET'])
@require_GET
def fetch_export(request):
    requested_export = request.query_params.get('export')
    export = ExportableQueryModel.objects.filter(name=requested_export).first()
    if not export:
        raise Http404
    elif export.user != request.user:
        raise PermissionDenied({"message": _("Only user requesting export can fetch request")})
    elif export.is_deleted:
        return Response(data='Export csv file was removed from server.', status=status.HTTP_410_GONE)

    export_file_name = F"export_{export.model}_{strftime(export.create_date, '%d_%m_%Y')}.{export.file_format}"
    if export.file_format == ExportableQueryModel.FileFormat.CSV:
        response = StreamingHttpResponse(
            open(export.content.path, 'rb'),
            content_type="text/csv",
            headers={'Content-Disposition': F'attachment; filename="{export_file_name}"'},
        )
    elif ExportableQueryModel.FileFormat.XLSX:
        response = StreamingHttpResponse(
            open(export.content.path, 'rb'),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={'Content-Disposition': F'attachment; filename="{export_file_name}"'},
        )
    else:
        return Response(data='Unsupported file format.', status=status.HTTP_400_BAD_REQUEST)

    return response

def _serialize_job(job):
    return "name: %s, trigger: %s, next run: %s, handler: %s" % (
        job.name, job.trigger, job.next_run_time, job.func)


@api_view(['GET'])
@require_GET
def get_scheduled_jobs(request):
    return Response([_serialize_job(job) for job in scheduler.get_jobs()])
