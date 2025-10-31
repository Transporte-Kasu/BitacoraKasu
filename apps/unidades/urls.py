from django.urls import path
from . import views

app_name = 'unidades'

urlpatterns = [
    # Dashboard
    path('', views.unidad_dashboard, name='dashboard'),
    
    # CRUD de unidades
    path('lista/', views.UnidadListView.as_view(), name='list'),
    path('crear/', views.UnidadCreateView.as_view(), name='create'),
    path('<int:pk>/', views.UnidadDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.UnidadUpdateView.as_view(), name='update'),
    path('<int:pk>/eliminar/', views.UnidadDeleteView.as_view(), name='delete'),
]
