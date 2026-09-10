from django.urls import path

from . import views

urlpatterns = [
    path("shipments/", views.ShipmentListView.as_view(), name="v2-shipment-list"),
    path("shipments/quote", views.ShipmentQuoteView.as_view(), name="v2-shipment-quote"),
    path("shipments/zones", views.ShipmentZonesView.as_view(), name="v2-shipment-zones"),
    path("shipments/<str:code>/", views.ShipmentDetailView.as_view(), name="v2-shipment-detail"),
    path("shipments/<str:code>/assign", views.ShipmentAssignView.as_view(), name="v2-shipment-assign"),
    path("shipments/<str:code>/events", views.ShipmentEventsView.as_view(), name="v2-shipment-events"),
    path("shipments/<str:code>/cancel", views.ShipmentCancelView.as_view(), name="v2-shipment-cancel"),

    path("portal/carrier/deliveries", views.CarrierDeliveriesView.as_view(), name="v2-carrier-deliveries"),
    path("portal/carrier/deliveries/<str:code>/event", views.CarrierDeliveryEventView.as_view(), name="v2-carrier-delivery-event"),

    path("track/<str:token>", views.PublicTrackView.as_view(), name="v2-track"),
]
