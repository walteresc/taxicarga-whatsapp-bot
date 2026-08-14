from django.urls import path

from .views import meta_webhook_v4


urlpatterns = [
    path("", meta_webhook_v4, name="meta-webhook-v4"),
]
