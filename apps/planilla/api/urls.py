from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceViewSet, CompensationViewSet, OpeningBalanceViewSet,
    PayrollConfigViewSet, PayrollDayView, PendingAbsencesView,
)

router = DefaultRouter()
router.register("payroll-config", PayrollConfigViewSet, basename="v2-payroll-config")
router.register("payroll-attendance", AttendanceViewSet, basename="v2-payroll-attendance")
router.register("payroll-compensations", CompensationViewSet, basename="v2-payroll-compensation")
router.register("payroll-opening-balance", OpeningBalanceViewSet, basename="v2-payroll-opening")

urlpatterns = [
    path("payroll/day", PayrollDayView.as_view(), name="v2-payroll-day"),
    path("payroll/pending-absences", PendingAbsencesView.as_view(), name="v2-payroll-pending"),
    *router.urls,
]
