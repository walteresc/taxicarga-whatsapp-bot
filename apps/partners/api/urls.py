from django.urls import path

from . import views

urlpatterns = [
    path("coverage", views.CoverageView.as_view(), name="partners-coverage"),
    path("quotes", views.QuoteView.as_view(), name="partners-quote"),
    path("shipments", views.ShipmentListView.as_view(), name="partners-shipment-list"),
    path("shipments/<str:code>", views.ShipmentDetailView.as_view(), name="partners-shipment-detail"),
    path("shipments/<str:code>/cancel", views.ShipmentCancelView.as_view(), name="partners-shipment-cancel"),
]
