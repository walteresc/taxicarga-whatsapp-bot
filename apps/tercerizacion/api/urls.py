from django.urls import path
from rest_framework.routers import DefaultRouter

from . import negociacion_views as neg
from .views import CarrierDriverViewSet, CarrierVehicleViewSet, CarrierViewSet

router = DefaultRouter()
router.register("carriers", CarrierViewSet, basename="v2-carrier")
router.register("carrier-vehicles", CarrierVehicleViewSet, basename="v2-carrier-vehicle")
router.register("carrier-drivers", CarrierDriverViewSet, basename="v2-carrier-driver")

urlpatterns = router.urls + [
    path("negotiations/", neg.NegotiationListView.as_view(), name="v2-negotiation-list"),
    path("negotiations/<int:pk>/", neg.NegotiationDetailView.as_view(), name="v2-negotiation-detail"),
    path("negotiations/<int:pk>/messages", neg.NegotiationMessagesView.as_view(), name="v2-negotiation-messages"),
    path("negotiations/messages/<int:pk>/respond", neg.NegotiationRespondView.as_view(), name="v2-negotiation-respond"),
    path("negotiations/<int:pk>/pause", neg.NegotiationPauseView.as_view(), name="v2-negotiation-pause"),
    path("negotiations/<int:pk>/resume", neg.NegotiationResumeView.as_view(), name="v2-negotiation-resume"),
    path("negotiations/<int:pk>/close", neg.NegotiationCloseView.as_view(), name="v2-negotiation-close"),
]
