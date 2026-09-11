from django.urls import path

from . import views

urlpatterns = [
    path("shipments/", views.ShipmentListView.as_view(), name="v2-shipment-list"),
    path("shipments/quote", views.ShipmentQuoteView.as_view(), name="v2-shipment-quote"),
    path("shipments/zones", views.ShipmentZonesView.as_view(), name="v2-shipment-zones"),
    path("shipments/pickup-points", views.PickupPointsView.as_view(), name="v2-pickup-points"),
    path("shipments/pickup-points/<int:pk>", views.PickupPointDetailView.as_view(), name="v2-pickup-point-detail"),
    path("shipments/<str:code>/", views.ShipmentDetailView.as_view(), name="v2-shipment-detail"),
    path("shipments/<str:code>/assign", views.ShipmentAssignView.as_view(), name="v2-shipment-assign"),
    path("shipments/<str:code>/events", views.ShipmentEventsView.as_view(), name="v2-shipment-events"),
    path("shipments/<str:code>/cancel", views.ShipmentCancelView.as_view(), name="v2-shipment-cancel"),
    path("shipments/<str:code>/pod-photo", views.ShipmentPodPhotoView.as_view(), name="v2-shipment-pod-photo"),

    path("routes/", views.RouteListView.as_view(), name="v2-route-list"),
    path("routes/<str:code>/", views.RouteDetailView.as_view(), name="v2-route-detail"),
    path("routes/<str:code>/stops", views.RouteStopsView.as_view(), name="v2-route-stops"),
    path("routes/<str:code>/start", views.RouteStartView.as_view(), name="v2-route-start"),
    path("routes/<str:code>/close", views.RouteCloseView.as_view(), name="v2-route-close"),

    path("cod/pending", views.CodPendingView.as_view(), name="v2-cod-pending"),
    path("cod/to-remit", views.CodToRemitView.as_view(), name="v2-cod-to-remit"),
    path("cod/settlements", views.CodSettlementListView.as_view(), name="v2-cod-settlements"),
    path("cod/settlements/<str:code>", views.CodSettlementDetailView.as_view(), name="v2-cod-settlement"),

    path("portal/carrier/deliveries", views.CarrierDeliveriesView.as_view(), name="v2-carrier-deliveries"),
    path("portal/carrier/route", views.CarrierRouteView.as_view(), name="v2-carrier-route"),
    path("portal/carrier/deliveries/<str:code>/event", views.CarrierDeliveryEventView.as_view(), name="v2-carrier-delivery-event"),

    path("track/<str:token>", views.PublicTrackView.as_view(), name="v2-track"),
]
