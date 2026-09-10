from django.urls import path

from . import views

urlpatterns = [
    path("pay/<str:token>", views.PublicOrderView.as_view(), name="v2-pay-order"),
    path("pay/<str:token>/charge", views.PublicChargeView.as_view(), name="v2-pay-charge"),
    path("payments/webhook/<str:provider>", views.WebhookView.as_view(), name="v2-pay-webhook"),
    path("pipeline/bookings/<int:pk>/payment-link", views.BookingPaymentLinkView.as_view(), name="v2-booking-payment-link"),
]
