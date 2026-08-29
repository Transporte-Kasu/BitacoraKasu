from django.urls import path

from . import views

app_name = 'vacios'

urlpatterns = [
    path('', views.vacios_dashboard, name='dashboard'),
    path('lista/', views.VacioListView.as_view(), name='list'),
    path('<int:pk>/', views.VacioDetailView.as_view(), name='detail'),
]
