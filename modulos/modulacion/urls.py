from django.urls import path

from . import views, views_api

app_name = 'modulacion'

urlpatterns = [
    # Dashboard
    path('', views.modulacion_dashboard, name='dashboard'),

    # CRUD modulaciones
    path('lista/', views.ModulacionListView.as_view(), name='list'),
    path('crear/', views.ModulacionCreateView.as_view(), name='create'),
    path('<int:pk>/', views.ModulacionDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.ModulacionUpdateView.as_view(), name='update'),
    path('<int:pk>/asignar/', views.AsignarUnidadOperadorView.as_view(), name='asignar'),
    path('<int:pk>/eliminar/', views.ModulacionDeleteView.as_view(), name='delete'),

    # Acciones especiales
    path('<int:pk>/enviar-a-bitacora/', views.EnviarABitacoraView.as_view(), name='enviar_a_bitacora'),
    path('<int:pk>/enviar-a-patio-esperanza/', views.enviar_a_patio_esperanza, name='enviar_a_patio_esperanza'),
    path('<int:pk>/retirar-de-patio/', views.retirar_de_patio, name='retirar_de_patio'),

    # Catálogo: agencias
    path('agencias/', views.AgenciaListView.as_view(), name='agencia_list'),
    path('agencias/nueva/', views.AgenciaCreateView.as_view(), name='agencia_create'),
    path('agencias/<int:pk>/editar/', views.AgenciaUpdateView.as_view(), name='agencia_update'),
    path('agencias/<int:pk>/eliminar/', views.AgenciaDeleteView.as_view(), name='agencia_delete'),

    # Catálogo: terminales portuarias
    path('terminales/', views.TerminalPortuariaListView.as_view(), name='terminal_list'),
    path('terminales/nueva/', views.TerminalPortuariaCreateView.as_view(), name='terminal_create'),
    path('terminales/<int:pk>/editar/', views.TerminalPortuariaUpdateView.as_view(), name='terminal_update'),
    path('terminales/<int:pk>/eliminar/', views.TerminalPortuariaDeleteView.as_view(), name='terminal_delete'),

    # API de recepción (HAL9MIL)
    path('api/recibir/', views_api.recibir_modulacion, name='api_recibir'),
]
