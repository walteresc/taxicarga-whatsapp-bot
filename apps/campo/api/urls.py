from rest_framework.routers import DefaultRouter

from .views import AssistantViewSet, DriverViewSet

router = DefaultRouter()
router.register("drivers", DriverViewSet, basename="v2-driver")
router.register("assistants", AssistantViewSet, basename="v2-assistant")

urlpatterns = router.urls
