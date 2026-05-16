from django.urls import path
from . import views

app_name = 'dollys'

urlpatterns = [
    path('', views.DollyListView.as_view(), name='list'),
    path('crear/', views.DollyCreateView.as_view(), name='create'),
    path('<slug:slug>/', views.DollyDetailView.as_view(), name='detail'),
    path('<slug:slug>/editar/', views.DollyUpdateView.as_view(), name='update'),
    path('<slug:slug>/eliminar/', views.DollyDeleteView.as_view(), name='delete'),
]
