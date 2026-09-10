from django.urls import path

from . import views

urlpatterns = [
    path("agent/status", views.StatusView.as_view(), name="v2-agent-status"),
    path("agent/ask", views.AskView.as_view(), name="v2-agent-ask"),
    path("agent/conversations/", views.ConversationListView.as_view(), name="v2-agent-conversations"),
    path("agent/conversations/<int:pk>/", views.ConversationDetailView.as_view(), name="v2-agent-conversation"),
    path("agent/proposals/", views.ProposalListView.as_view(), name="v2-agent-proposals"),
    path("agent/proposals/<int:pk>/apply", views.ProposalApplyView.as_view(), name="v2-agent-proposal-apply"),
    path("agent/proposals/<int:pk>/reject", views.ProposalRejectView.as_view(), name="v2-agent-proposal-reject"),
]
