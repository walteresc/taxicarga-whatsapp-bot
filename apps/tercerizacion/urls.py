from django.urls import path

from . import views

urlpatterns = [
    path("", views.lista_publicaciones, name="tercerizacion-list"),
    path("servicio/<int:servicio_id>/tercerizar/", views.tercerizar, name="tercerizacion-tercerizar"),
    path("bot/estado/", views.api_bot_estado, name="tercerizacion-bot-estado"),
    path("bot/pausar/", views.api_bot_pausar, name="tercerizacion-bot-pausar"),
    path("bot/activar/", views.api_bot_activar, name="tercerizacion-bot-activar"),
    path("<int:pk>/", views.detalle_publicacion, name="tercerizacion-detail"),
]
