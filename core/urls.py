from django.urls import include, path
from rest_framework.routers import DefaultRouter

from core import views

router = DefaultRouter()
router.register(r"users", views.UserViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("fetch_export", views.fetch_export),
    path("scheduled_jobs", views.get_scheduled_jobs),
]
