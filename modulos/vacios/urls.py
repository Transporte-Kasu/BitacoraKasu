from django.urls import path

from . import views

app_name = 'vacios'

urlpatterns = [
    path('', views.vacios_dashboard, name='dashboard'),
    path('lista/', views.VacioListView.as_view(), name='list'),
    path('<int:pk>/', views.VacioDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.VacioUpdateView.as_view(), name='update'),
    path('<int:pk>/eliminar/', views.VacioDeleteView.as_view(), name='delete'),
    path('<int:pk>/asignar/', views.AsignarUnidadOperadorVacioView.as_view(), name='asignar'),
    path('<int:pk>/retorno-patio/', views.registrar_retorno_patio, name='registrar_retorno_patio'),
    path('<int:pk>/reasignar/', views.reasignar_operador, name='reasignar_operador'),
    path('<int:pk>/salida-naviera/', views.registrar_salida_naviera, name='registrar_salida_naviera'),
    path('<int:pk>/entrega-naviera/', views.registrar_entrega_naviera, name='registrar_entrega_naviera'),
    path('<int:pk>/retraso/', views.RegistrarRetrasoView.as_view(), name='registrar_retraso'),
    path('<int:pk>/retraso/<int:rid>/reenviar/', views.reenviar_aviso_retraso, name='reenviar_aviso_retraso'),
]
