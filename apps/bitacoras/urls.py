from django.urls import path
from . import views

app_name = 'bitacoras'

urlpatterns = [
    # Dashboard
    path('', views.bitacora_dashboard, name='dashboard'),
    
    # CRUD de bitácoras
    path('lista/', views.BitacoraListView.as_view(), name='list'),
    path('crear/', views.BitacoraCreateView.as_view(), name='create'),
    path('<int:pk>/', views.BitacoraDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.BitacoraUpdateView.as_view(), name='update'),
    path('<int:pk>/eliminar/', views.BitacoraDeleteView.as_view(), name='delete'),
    
    # Funciones especiales
    path('<int:pk>/completar/', views.completar_viaje, name='completar'),
    path('<int:pk>/calcular-distancia/', views.calcular_distancia_ajax, name='calcular_distancia'),
]
