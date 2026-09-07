from rest_framework.routers import DefaultRouter

from .views import CarrierDriverViewSet, CarrierVehicleViewSet, CarrierViewSet

router = DefaultRouter()
router.register("carriers", CarrierViewSet, basename="v2-carrier")
router.register("carrier-vehicles", CarrierVehicleViewSet, basename="v2-carrier-vehicle")
router.register("carrier-drivers", CarrierDriverViewSet, basename="v2-carrier-driver")

urlpatterns = router.urls
