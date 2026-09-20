from django.urls import path

from . import views

urlpatterns = [
    path("ia/config", views.AIConfigView.as_view(), name="v2-ia-config"),
]
