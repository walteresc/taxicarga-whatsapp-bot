from rest_framework.routers import DefaultRouter

from .views import MaintenanceViewSet, VehicleViewSet

router = DefaultRouter()
router.register("vehicles", VehicleViewSet, basename="v2-vehicle")
router.register("maintenance", MaintenanceViewSet, basename="v2-maintenance")

urlpatterns = router.urls
