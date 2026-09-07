from rest_framework.routers import DefaultRouter

from .views import CustomerViewSet

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="v2-customer")

urlpatterns = router.urls
