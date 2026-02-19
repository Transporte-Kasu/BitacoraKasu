from django.urls import path
from . import views

app_name = 'combustible'

urlpatterns = [
    # Dashboard
    path('', views.dashboard_combustible, name='dashboard'),

    # Wizard de carga paso a paso
    path('nueva-carga/', views.CargaCombustibleWizardView.as_view(), name='wizard'),
    path('nueva-carga/paso/<int:paso>/', views.CargaCombustibleWizardView.as_view(), name='wizard'),

    # Control de carga (AJAX)
    path('<int:pk>/iniciar/', views.IniciarCargaView.as_view(), name='iniciar_carga'),
    path('<int:pk>/finalizar/', views.FinalizarCargaView.as_view(), name='finalizar_carga'),

    # Listado y detalle
    path('lista/', views.CargaCombustibleListView.as_view(), name='lista'),
    path('<int:pk>/', views.CargaCombustibleDetailView.as_view(), name='detalle'),

    # Alertas (solo superusuarios)
    path('alertas/', views.AlertaCombustibleListView.as_view(), name='alertas'),
    path('alertas/<int:pk>/resolver/', views.resolver_alerta_combustible, name='resolver_alerta'),
]