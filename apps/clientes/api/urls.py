from django.urls import path
from rest_framework.routers import DefaultRouter

from . import portal_cliente_views as pc
from .views import CustomerViewSet

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="v2-customer")

urlpatterns = router.urls + [
    path("portal/customer/me", pc.CustomerMeView.as_view(), name="v2-portal-customer-me"),
    path("portal/customer/loads", pc.CustomerLoadsView.as_view(), name="v2-portal-customer-loads"),
    path("portal/customer/loads/<str:code>", pc.CustomerLoadDetailView.as_view(), name="v2-portal-customer-load"),
    path("portal/customer/loads/<str:code>/accept", pc.CustomerLoadAcceptView.as_view(), name="v2-portal-customer-accept"),
    path("portal/customer/loads/<str:code>/request-advisor", pc.CustomerLoadRequestAdvisorView.as_view(), name="v2-portal-customer-request-advisor"),
    path("portal/customer/loads/<str:code>/negotiate", pc.CustomerLoadNegotiateView.as_view(), name="v2-portal-customer-negotiate"),
    path("portal/customer/loads/<str:code>/negotiation", pc.CustomerNegotiationView.as_view(), name="v2-portal-customer-negotiation"),
    path("portal/customer/loads/<str:code>/negotiation/messages", pc.CustomerNegotiationMessagesView.as_view(), name="v2-portal-customer-negotiation-messages"),
    path("portal/customer/loads/<str:code>/negotiation/messages/<int:pk>/respond", pc.CustomerNegotiationRespondView.as_view(), name="v2-portal-customer-negotiation-respond"),
]
