from django.urls import path
from . import views

app_name = 'caja_seca'

urlpatterns = [
    path('', views.CajaSecaListView.as_view(), name='list'),
    path('crear/', views.CajaSecaCreateView.as_view(), name='create'),
    path('<slug:slug>/', views.CajaSecaDetailView.as_view(), name='detail'),
    path('<slug:slug>/editar/', views.CajaSecaUpdateView.as_view(), name='update'),
    path('<slug:slug>/eliminar/', views.CajaSecaDeleteView.as_view(), name='delete'),
]
