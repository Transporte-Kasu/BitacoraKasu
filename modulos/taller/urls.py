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

    # Reportes de falla (operador vía QR, sin login)
    path('reportar/<int:unidad_pk>/', views.reportar_falla, name='reportar_falla'),
    path('reportar/enviado/<str:folio>/', views.reporte_enviado, name='reporte_enviado'),

    # Bandeja de reportes (taller)
    path('reportes/', views.bandeja_reportes, name='bandeja_reportes'),
    path('reportes/<str:folio>/', views.detalle_reporte, name='detalle_reporte'),
    path('reportes/<str:folio>/atender/', views.atender_reporte, name='atender_reporte'),
    path('reportes/<str:folio>/resolver/', views.resolver_reporte, name='resolver_reporte'),
    path('reportes/<str:folio>/convertir-ot/', views.convertir_reporte_a_ot, name='convertir_reporte_a_ot'),
    path('reportes/<str:folio>/cancelar/', views.cancelar_reporte, name='cancelar_reporte'),

    # QR por unidad (para imprimir y pegar en el vehículo)
    path('unidades/<int:unidad_pk>/qr/', views.qr_unidad, name='qr_unidad'),
    path('unidades/qr-todas/', views.qr_todas_unidades, name='qr_todas_unidades'),

    # API
    path('api/ordenes-activas/', views.api_ordenes_activas, name='api_ordenes_activas'),
    path('api/buscar-producto-almacen/', views.buscar_producto_almacen, name='buscar_producto_almacen'),
]