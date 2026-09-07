from rest_framework.routers import DefaultRouter

from .views import CarrierVehicleViewSet, CarrierViewSet

router = DefaultRouter()
router.register("carriers", CarrierViewSet, basename="v2-carrier")
router.register("carrier-vehicles", CarrierVehicleViewSet, basename="v2-carrier-vehicle")

urlpatterns = router.urls
