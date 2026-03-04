from django.urls import path
from . import views

app_name = 'reportes'

urlpatterns = [
    # Historial de reportes generados
    path('historial/', views.HistorialReportesView.as_view(), name='historial'),
    path('historial/<int:pk>/', views.DetalleReporteGeneradoView.as_view(), name='detalle'),

    # Configuraciones de reportes programados
    path('configuraciones/', views.ConfiguracionListView.as_view(), name='configuracion_list'),
    path('configuraciones/nueva/', views.ConfiguracionCreateView.as_view(), name='configuracion_create'),
    path('configuraciones/<int:pk>/editar/', views.ConfiguracionUpdateView.as_view(), name='configuracion_update'),
    path('configuraciones/<int:pk>/eliminar/', views.ConfiguracionDeleteView.as_view(), name='configuracion_delete'),
]
