from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AttendanceViewSet, PayrollConfigViewSet, PayrollDayView

router = DefaultRouter()
router.register("payroll-config", PayrollConfigViewSet, basename="v2-payroll-config")
router.register("payroll-attendance", AttendanceViewSet, basename="v2-payroll-attendance")

urlpatterns = [
    path("payroll/day", PayrollDayView.as_view(), name="v2-payroll-day"),
    *router.urls,
]
