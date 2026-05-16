from django.urls import path
from . import views

app_name = 'equipos'

urlpatterns = [
    path('', views.EquipoListView.as_view(), name='list'),
    path('crear/', views.EquipoCreateView.as_view(), name='create'),
    path('<slug:slug>/', views.EquipoDetailView.as_view(), name='detail'),
    path('<slug:slug>/editar/', views.EquipoUpdateView.as_view(), name='update'),
    path('<slug:slug>/eliminar/', views.EquipoDeleteView.as_view(), name='delete'),
]
