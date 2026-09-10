from django.urls import path
from rest_framework.routers import DefaultRouter

from . import liquidaciones_views as liqv
from . import negociacion_views as neg
from . import portal_views as portal
from . import publicaciones_views as pubv
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

    path("outsourcing/settings", pubv.OutsourcingSettingsView.as_view(), name="v2-outsourcing-settings"),
    path("outsourcing/commission-tiers", pubv.CommissionTiersView.as_view(), name="v2-commission-tiers"),
    path("outsourcing/commission-tiers/<int:pk>", pubv.CommissionTierDetailView.as_view(), name="v2-commission-tier-detail"),

    path("settlements/", liqv.SettlementListView.as_view(), name="v2-settlement-list"),
    path("settlements/summary", liqv.SettlementSummaryView.as_view(), name="v2-settlement-summary"),
    path("settlements/<int:pk>/", liqv.SettlementDetailView.as_view(), name="v2-settlement-detail"),
    path("settlements/<int:pk>/settle", liqv.SettlementSettleView.as_view(), name="v2-settlement-settle"),
    path("settlements/<int:pk>/void", liqv.SettlementVoidView.as_view(), name="v2-settlement-void"),

    path("publications/", pubv.PublicationListView.as_view(), name="v2-publication-list"),
    path("publications/<int:pk>/", pubv.PublicationDetailView.as_view(), name="v2-publication-detail"),
    path("publications/<int:pk>/publish", pubv.PublicationPublishView.as_view(), name="v2-publication-publish"),
    path("publications/<int:pk>/offers", pubv.PublicationOffersView.as_view(), name="v2-publication-offers"),
    path("publications/<int:pk>/award", pubv.PublicationAwardView.as_view(), name="v2-publication-award"),

    # Portal del Transportista
    path("portal/carrier/me", portal.CarrierMeView.as_view(), name="v2-portal-carrier-me"),
    path("portal/carrier/loads", portal.CarrierLoadsView.as_view(), name="v2-portal-carrier-loads"),
    path("portal/carrier/loads/<str:code>/offer", portal.CarrierOfferView.as_view(), name="v2-portal-carrier-offer"),
    path("portal/carrier/offers", portal.CarrierOffersView.as_view(), name="v2-portal-carrier-offers"),
    path("portal/carrier/assignments", portal.CarrierAssignmentsView.as_view(), name="v2-portal-carrier-assignments"),
    path("portal/carrier/earnings", portal.CarrierEarningsView.as_view(), name="v2-portal-carrier-earnings"),
    path("portal/carrier/negotiations", portal.CarrierNegotiationsView.as_view(), name="v2-portal-carrier-negotiations"),
    path("portal/carrier/negotiations/<int:pk>/", portal.CarrierNegotiationDetailView.as_view(), name="v2-portal-carrier-negotiation-detail"),
    path("portal/carrier/negotiations/<int:pk>/messages", portal.CarrierNegotiationMessagesView.as_view(), name="v2-portal-carrier-negotiation-messages"),
    path("portal/carrier/negotiations/messages/<int:pk>/respond", portal.CarrierNegotiationRespondView.as_view(), name="v2-portal-carrier-negotiation-respond"),
]
