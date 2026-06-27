from django.urls import path
from . import views

app_name = 'bitacoras'

urlpatterns = [
    # Dashboard
    path('', views.bitacora_dashboard, name='dashboard'),

    # CRUD bitácoras
    path('lista/', views.BitacoraListView.as_view(), name='list'),
    path('crear/', views.BitacoraCreateView.as_view(), name='create'),
    path('<int:pk>/', views.BitacoraDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.BitacoraUpdateView.as_view(), name='update'),
    path('<int:pk>/eliminar/', views.BitacoraDeleteView.as_view(), name='delete'),

    # Acciones especiales bitácora
    path('<int:pk>/completar/', views.completar_viaje, name='completar'),
    path('<int:pk>/calcular-distancia/', views.calcular_distancia_ajax, name='calcular_distancia'),
    path('<int:pk>/notificar-cliente/', views.enviar_notificacion_cliente, name='notificar_cliente'),

    # CRUD clientes
    path('clientes/', views.ClienteListView.as_view(), name='cliente_list'),
    path('clientes/nuevo/', views.ClienteCreateView.as_view(), name='cliente_create'),
    path('clientes/<int:pk>/editar/', views.ClienteUpdateView.as_view(), name='cliente_update'),
    path('clientes/<int:pk>/eliminar/', views.ClienteDeleteView.as_view(), name='cliente_delete'),

    # Carga masiva desde Excel
    path('carga-masiva/', views.carga_masiva_upload, name='carga_masiva'),
    path('carga-masiva/preview/', views.carga_masiva_preview, name='carga_masiva_preview'),

    # Exportar Excel
    path('exportar-excel/', views.exportar_excel, name='exportar_excel'),

    # AJAX utilitarios
    path('ajax/unidad-info/', views.unidad_info_ajax, name='unidad_info_ajax'),
    path('ajax/calcular-distancia/', views.calcular_distancia_preview_ajax, name='calcular_distancia_preview'),
]
