from django.urls import path

from .views import chatwoot_webhook


urlpatterns = [
    path("", chatwoot_webhook, name="chatwoot-webhook"),
]
