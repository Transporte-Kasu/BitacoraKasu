from django.urls import path
from . import views

app_name = 'compras'

urlpatterns = [
    # Dashboard
    path('', views.dashboard_compras, name='dashboard'),
    
    # Proveedores
    path('proveedores/', views.ProveedorListView.as_view(), name='proveedor_list'),
    
    # Requisiciones
    path('requisiciones/', views.RequisicionListView.as_view(), name='requisicion_list'),
    
    # Órdenes de Compra
    path('ordenes/', views.OrdenCompraListView.as_view(), name='ordencompra_list'),
    
    # Productos
    path('productos/', views.ProductoListView.as_view(), name='producto_list'),
]