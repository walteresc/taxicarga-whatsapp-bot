from django.urls import path

from .reports_views import BenchmarkReportView, SalesReportView

urlpatterns = [
    path("reports/benchmark", BenchmarkReportView.as_view(), name="v2-report-benchmark"),
    path("reports/sales", SalesReportView.as_view(), name="v2-report-sales"),
]
