from django.urls import path

from . import views

urlpatterns = [
    path("bot/status", views.BotStatusView.as_view(), name="v2-bot-status"),
    path("bot/operations/pause", views.BotOperationsPauseView.as_view(), name="v2-bot-operations-pause"),
    path("bot/operations/resume", views.BotOperationsResumeView.as_view(), name="v2-bot-operations-resume"),
]
