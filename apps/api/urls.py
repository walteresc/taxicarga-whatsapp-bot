"""Raíz de la API v2. Cada módulo aporta su propio apps/<app>/api/urls.py."""
from django.urls import include, path

from .views_public_tracking import TrackingLookupView

urlpatterns = [
    # Antes del include de encomiendas: si no, "lookup" caería en su
    # "track/<str:token>" y nunca llegaría a esta vista.
    path("track/lookup", TrackingLookupView.as_view(), name="v2-track-lookup"),
    path("", include("apps.campo.api.urls")),
    path("", include("apps.flota.api.urls")),
    path("", include("apps.clientes.api.urls")),
    path("", include("apps.dashboard.api.urls")),
    path("", include("apps.cotizador.api.urls")),
    path("", include("apps.whatsapp_bot_v4.api.urls")),
    path("", include("apps.grupos_internos.api.urls")),
    path("", include("apps.catalogo.api.urls")),
    path("", include("apps.tercerizacion.api.urls")),
    path("", include("apps.planilla.api.urls")),
    path("", include("apps.agente.api.urls")),
    path("", include("apps.pagos.api.urls")),
    path("", include("apps.encomiendas.api.urls")),
    path("", include("apps.partners.api.admin_urls")),
]
