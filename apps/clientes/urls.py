from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ClienteViewSet, ConversacionViewSet

router = DefaultRouter()
router.register("clientes", ClienteViewSet)
router.register("conversaciones", ConversacionViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
