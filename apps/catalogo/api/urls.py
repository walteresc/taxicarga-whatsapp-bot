from rest_framework.routers import DefaultRouter

from .views import BodyTypeViewSet, VehicleCategoryViewSet, VehicleTypeViewSet

router = DefaultRouter()
router.register("vehicle-types", VehicleTypeViewSet, basename="v2-vehicle-type")
router.register("body-types", BodyTypeViewSet, basename="v2-body-type")
router.register("vehicle-categories", VehicleCategoryViewSet, basename="v2-vehicle-category")

urlpatterns = router.urls
