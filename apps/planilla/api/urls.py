from rest_framework.routers import DefaultRouter

from .views import PayrollConfigViewSet

router = DefaultRouter()
router.register("payroll-config", PayrollConfigViewSet, basename="v2-payroll-config")

urlpatterns = router.urls
