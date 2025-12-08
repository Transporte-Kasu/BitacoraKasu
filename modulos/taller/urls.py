from django.urls import path
from . import views

app_name = 'taller'

urlpatterns = [
    # Dashboard
    path('', views.dashboard_taller, name='dashboard'),

    # Órdenes de trabajo
    path('ordenes/', views.lista_ordenes, name='lista_ordenes'),
    path('ordenes/crear/', views.crear_orden, name='crear_orden'),
    path('ordenes/<str:folio>/', views.detalle_orden, name='detalle_orden'),
    path('ordenes/<str:folio>/diagnostico/', views.actualizar_diagnostico, name='actualizar_diagnostico'),
    path('ordenes/<str:folio>/estado/', views.cambiar_estado_orden, name='cambiar_estado_orden'),

    # Piezas
    path('ordenes/<str:folio>/agregar-pieza/', views.agregar_pieza, name='agregar_pieza'),
    path('ordenes/<str:folio>/generar-requisicion/', views.generar_requisicion, name='generar_requisicion'),

    # Historial
    path('historial/unidad/<int:unidad_id>/', views.historial_unidad, name='historial_unidad'),

    # API
    path('api/ordenes-activas/', views.api_ordenes_activas, name='api_ordenes_activas'),
]