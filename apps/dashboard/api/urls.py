from django.urls import path

from .reports_views import BenchmarkReportView, OutsourcingReportView, SalesReportView
from .users_views import RoleListView, UserDetailView, UserListView

urlpatterns = [
    path("reports/benchmark", BenchmarkReportView.as_view(), name="v2-report-benchmark"),
    path("reports/sales", SalesReportView.as_view(), name="v2-report-sales"),
    path("reports/outsourcing", OutsourcingReportView.as_view(), name="v2-report-outsourcing"),

    path("roles/", RoleListView.as_view(), name="v2-role-list"),
    path("users/", UserListView.as_view(), name="v2-user-list"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="v2-user-detail"),
]
