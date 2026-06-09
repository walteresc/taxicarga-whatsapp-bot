from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CotizacionViewSet, ServicioHistoricoViewSet

router = DefaultRouter()
router.register("servicios-historicos", ServicioHistoricoViewSet)
router.register("cotizaciones", CotizacionViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
