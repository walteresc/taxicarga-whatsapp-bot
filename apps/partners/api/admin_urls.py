from django.urls import path

from . import admin_views as v

urlpatterns = [
    path("partners/", v.PartnerListView.as_view(), name="v2-partner-list"),
    path("partners/<int:pk>/", v.PartnerDetailView.as_view(), name="v2-partner-detail"),
    path("partners/<int:pk>/keys", v.PartnerKeyListView.as_view(), name="v2-partner-key-list"),
    path("partners/<int:pk>/keys/<int:key_id>/revoke", v.PartnerKeyRevokeView.as_view(), name="v2-partner-key-revoke"),
]
