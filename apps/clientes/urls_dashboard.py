from django.urls import path

from . import views_dashboard

urlpatterns = [
    path('', views_dashboard.cliente_lista, name='cliente_lista'),
    path('nuevo/', views_dashboard.cliente_crear, name='cliente_crear'),
    path('<int:pk>/editar/', views_dashboard.cliente_editar, name='cliente_editar'),
    path('<int:pk>/eliminar/', views_dashboard.cliente_eliminar, name='cliente_eliminar'),
]
