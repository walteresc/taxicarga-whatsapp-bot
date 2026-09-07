from django.urls import path

from . import views

urlpatterns = [
    path("groups/", views.GroupListView.as_view(), name="v2-group-list"),
    path("groups/<int:pk>/", views.GroupDetailView.as_view(), name="v2-group-detail"),
    path("groups/<int:pk>/members", views.GroupMembersView.as_view(), name="v2-group-members"),
    path("groups/<int:pk>/members/<int:user_id>", views.GroupMemberDetailView.as_view(), name="v2-group-member-detail"),
    path("groups/<int:pk>/messages", views.GroupMessageListView.as_view(), name="v2-group-messages"),
    path("groups/<int:pk>/messages/media", views.GroupMessageMediaView.as_view(), name="v2-group-messages-media"),
    path("groups/users", views.AvailableUsersView.as_view(), name="v2-group-available-users"),
]
