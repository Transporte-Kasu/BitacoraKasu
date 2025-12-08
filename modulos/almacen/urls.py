from django.urls import path
from . import views

app_name = 'almacen'

urlpatterns = [
    # Dashboard
    path('', views.dashboard_almacen, name='dashboard'),
    
    # Productos
    path('productos/', views.ProductoAlmacenListView.as_view(), name='producto_list'),
    path('productos/crear/', views.ProductoAlmacenCreateView.as_view(), name='producto_create'),
    path('productos/<int:pk>/', views.ProductoAlmacenDetailView.as_view(), name='producto_detail'),
    path('productos/<int:pk>/editar/', views.ProductoAlmacenUpdateView.as_view(), name='producto_update'),
    path('productos/<int:pk>/eliminar/', views.ProductoAlmacenDeleteView.as_view(), name='producto_delete'),
    
    # Entradas
    path('entradas/', views.EntradaAlmacenListView.as_view(), name='entrada_list'),
    path('entradas/crear/', views.EntradaAlmacenCreateView.as_view(), name='entrada_create'),
    path('entradas/<int:pk>/', views.EntradaAlmacenDetailView.as_view(), name='entrada_detail'),
    
    # Solicitudes de Salida
    path('solicitudes/', views.SolicitudSalidaListView.as_view(), name='solicitud_list'),
    path('solicitudes/crear/', views.SolicitudSalidaCreateView.as_view(), name='solicitud_create'),
    path('solicitudes/<int:pk>/', views.SolicitudSalidaDetailView.as_view(), name='solicitud_detail'),
    path('solicitudes/<int:pk>/autorizar/', views.autorizar_solicitud, name='solicitud_autorizar'),
    path('solicitudes/<int:pk>/procesar-entrega/', views.procesar_entrega, name='solicitud_procesar_entrega'),
    
    # Salidas
    path('salidas/', views.SalidaAlmacenListView.as_view(), name='salida_list'),
    path('salidas/<int:pk>/', views.SalidaAlmacenDetailView.as_view(), name='salida_detail'),
    
    # Movimientos
    path('movimientos/', views.MovimientoAlmacenListView.as_view(), name='movimiento_list'),
    
    # Alertas
    path('alertas/', views.AlertaStockListView.as_view(), name='alerta_list'),
    path('alertas/<int:pk>/resolver/', views.resolver_alerta, name='alerta_resolver'),
    
    # Reportes
    path('reportes/inventario/', views.reporte_inventario, name='reporte_inventario'),
    path('reportes/stock-critico/', views.reporte_stock_critico, name='reporte_stock_critico'),
    path('reportes/proximos-caducar/', views.reporte_proximos_caducar, name='reporte_caducidad'),
]
