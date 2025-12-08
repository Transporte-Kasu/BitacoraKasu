from django.urls import path
from . import views

app_name = 'compras'

urlpatterns = [
    # Dashboard
    path('', views.dashboard_compras, name='dashboard'),
    
    # Proveedores
    path('proveedores/', views.ProveedorListView.as_view(), name='proveedor_list'),
    path('proveedores/crear/', views.ProveedorCreateView.as_view(), name='proveedor_crear'),
    path('proveedores/<int:pk>/editar/', views.ProveedorUpdateView.as_view(), name='proveedor_editar'),
    path('proveedores/<int:pk>/eliminar/', views.ProveedorDeleteView.as_view(), name='proveedor_eliminar'),
    
    # Productos
    path('productos/', views.ProductoListView.as_view(), name='producto_list'),
    path('productos/crear/', views.ProductoCreateView.as_view(), name='producto_crear'),
    path('productos/<int:pk>/editar/', views.ProductoUpdateView.as_view(), name='producto_editar'),
    path('productos/<int:pk>/eliminar/', views.ProductoDeleteView.as_view(), name='producto_eliminar'),
    
    # Requisiciones
    path('requisiciones/', views.RequisicionListView.as_view(), name='requisicion_list'),
    path('requisiciones/crear/', views.requisicion_crear, name='requisicion_crear'),
    path('requisiciones/<int:pk>/items/', views.requisicion_agregar_items, name='requisicion_agregar_items'),
    path('requisiciones/<int:requisicion_pk>/items/<int:item_pk>/eliminar/', views.requisicion_eliminar_item, name='requisicion_eliminar_item'),
    
    # Órdenes de Compra
    path('ordenes/', views.OrdenCompraListView.as_view(), name='ordencompra_list'),
    path('ordenes/crear/', views.OrdenCompraCreateView.as_view(), name='ordencompra_crear'),
    path('ordenes/<int:pk>/editar/', views.OrdenCompraUpdateView.as_view(), name='ordencompra_editar'),
]
