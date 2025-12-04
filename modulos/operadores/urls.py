from django.urls import path
from . import views

app_name = 'operadores'

urlpatterns = [
    # Dashboard
    path('', views.operador_dashboard, name='dashboard'),
    
    # CRUD de operadores
    path('lista/', views.OperadorListView.as_view(), name='list'),
    path('crear/', views.OperadorCreateView.as_view(), name='create'),
    path('<int:pk>/', views.OperadorDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.OperadorUpdateView.as_view(), name='update'),
    path('<int:pk>/eliminar/', views.OperadorDeleteView.as_view(), name='delete'),
]
