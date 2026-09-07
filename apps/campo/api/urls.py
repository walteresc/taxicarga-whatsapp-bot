from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AssistantViewSet, DriverViewSet, PersonnelDirectoryView, PizarraMutationView,
    PizarraView, ScheduleViewSet,
)

router = DefaultRouter()
router.register("drivers", DriverViewSet, basename="v2-driver")
router.register("assistants", AssistantViewSet, basename="v2-assistant")
router.register("schedule", ScheduleViewSet, basename="v2-schedule")

urlpatterns = [
    path("personnel/", PersonnelDirectoryView.as_view(), name="v2-personnel-directory"),
    path("pizarra/", PizarraView.as_view(), name="v2-pizarra"),
    path("pizarra/<str:action>", PizarraMutationView.as_view(), name="v2-pizarra-action"),
    *router.urls,
]
