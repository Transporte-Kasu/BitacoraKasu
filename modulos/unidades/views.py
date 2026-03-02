from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Count, Avg, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import timedelta
import json
from .models import Unidad
from .forms import UnidadForm, AsignacionDirectaAlmacenForm
from modulos.taller.models import OrdenTrabajo
from modulos.almacen.models import SalidaRapidaConsumible, AsignacionDirectaAlmacen, MovimientoAlmacen


class UnidadListView(LoginRequiredMixin, ListView):
    """Vista para listar todas las unidades"""
    model = Unidad
    template_name = 'unidades/unidad_list.html'
    context_object_name = 'unidades'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Unidad.objects.annotate(
            total_viajes=Count('bitacoras')
        )
        
        # Filtro por búsqueda
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(numero_economico__icontains=search) |
                Q(placa__icontains=search) |
                Q(marca__icontains=search) |
                Q(modelo__icontains=search)
            )
        
        # Filtro por tipo
        tipo = self.request.GET.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        
        # Filtro por estado
        activa = self.request.GET.get('activa')
        if activa == 'true':
            queryset = queryset.filter(activa=True)
        elif activa == 'false':
            queryset = queryset.filter(activa=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_unidades'] = Unidad.objects.count()
        context['unidades_activas'] = Unidad.objects.filter(activa=True).count()
        context['tipos_choices'] = Unidad.TIPO_CHOICES
        return context


class UnidadDetailView(LoginRequiredMixin, DetailView):
    """Vista de detalle de una unidad"""
    model = Unidad
    template_name = 'unidades/unidad_detail.html'
    context_object_name = 'unidad'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        unidad = self.get_object()
        hoy = timezone.now().date()
        
        # Obtener últimos viajes
        context['ultimos_viajes'] = unidad.bitacoras.select_related(
            'operador'
        ).order_by('-fecha_salida')[:10]
        
        # Estadísticas de viajes
        context['viajes_completados'] = unidad.viajes_completados()
        context['rendimiento_promedio'] = unidad.rendimiento_promedio_real()
        context['eficiencia'] = unidad.eficiencia_combustible()
        context['requiere_mantenimiento'] = unidad.requiere_mantenimiento()
        
        # Operadores asignados
        context['operadores_asignados'] = unidad.operadores.filter(activo=True)
        
        # Historial de cargas de combustible
        cargas = unidad.cargas_combustible.select_related(
            'despachador'
        ).order_by('-fecha_hora_inicio')
        
        context['cargas_combustible'] = cargas[:15]  # Últimas 15 cargas
        context['total_cargas'] = cargas.count()
        
        # Estadísticas de combustible
        cargas_completadas = cargas.filter(estado='COMPLETADO')
        context['total_litros_cargados'] = cargas_completadas.aggregate(
            total=Sum('cantidad_litros')
        )['total'] or 0
        
        # Estadísticas del mes actual
        cargas_mes = cargas_completadas.filter(
            fecha_hora_inicio__year=hoy.year,
            fecha_hora_inicio__month=hoy.month
        )
        context['litros_mes_actual'] = cargas_mes.aggregate(
            total=Sum('cantidad_litros')
        )['total'] or 0
        context['cargas_mes_actual'] = cargas_mes.count()
        
        # Alertas de candado en últimas 10 cargas
        context['alertas_candado_recientes'] = cargas.filter(
            estado_candado_anterior__in=['ALTERADO', 'VIOLADO', 'SIN_CANDADO']
        )[:10]
        
        # Datos para gráfico de litros por mes (últimos 12 meses)
        fecha_inicio = hoy - timedelta(days=365)
        cargas_por_mes = cargas_completadas.filter(
            fecha_hora_inicio__gte=fecha_inicio
        ).annotate(
            mes=TruncMonth('fecha_hora_inicio')
        ).values('mes').annotate(
            total_litros=Sum('cantidad_litros')
        ).order_by('mes')
        
        # Preparar datos para Chart.js
        meses_labels = []
        litros_data = []
        
        for item in cargas_por_mes:
            mes_fecha = item['mes']
            # Formato: "Ene 2024"
            meses_labels.append(mes_fecha.strftime('%b %Y'))
            litros_data.append(float(item['total_litros']))
        
        context['grafico_meses'] = json.dumps(meses_labels)
        context['grafico_litros'] = json.dumps(litros_data)

        # Órdenes de taller
        ordenes_taller = unidad.ordenes_trabajo.select_related(
            'tipo_mantenimiento', 'mecanico_asignado'
        ).prefetch_related('piezas_requeridas').order_by('-fecha_creacion')
        context['ordenes_taller'] = ordenes_taller[:10]
        context['total_ordenes_taller'] = ordenes_taller.count()

        # Consumibles asignados desde almacén
        consumibles = unidad.consumibles_asignados.select_related(
            'producto', 'entregado_por'
        ).order_by('-fecha_salida')
        context['consumibles_asignados'] = consumibles[:15]
        context['total_consumibles'] = consumibles.count()

        # Asignaciones directas de almacén (piezas para reparación rápida)
        asignaciones = unidad.asignaciones_almacen.select_related(
            'producto', 'entregado_por'
        ).order_by('-fecha_asignacion')
        context['asignaciones_directas'] = asignaciones[:15]
        context['total_asignaciones_directas'] = asignaciones.count()

        # Formulario de asignación directa
        context['form_asignacion'] = AsignacionDirectaAlmacenForm()

        # Datos de productos para validación JS (stock y unidad de medida)
        from modulos.almacen.models import ProductoAlmacen
        productos_data = {
            str(p.id): {
                'stock': float(p.cantidad),
                'unidad': p.unidad_medida,
            }
            for p in ProductoAlmacen.objects.filter(activo=True, cantidad__gt=0)
        }
        context['productos_json'] = json.dumps(productos_data)

        return context


class UnidadCreateView(LoginRequiredMixin, CreateView):
    """Vista para crear una nueva unidad"""
    model = Unidad
    form_class = UnidadForm
    template_name = 'unidades/unidad_form.html'
    success_url = reverse_lazy('unidades:list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Unidad {form.instance.numero_economico} creada exitosamente.')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Error al crear la unidad. Verifique los datos.')
        return super().form_invalid(form)


class UnidadUpdateView(LoginRequiredMixin, UpdateView):
    """Vista para actualizar una unidad"""
    model = Unidad
    form_class = UnidadForm
    template_name = 'unidades/unidad_form.html'

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse('unidades:list')

    def form_valid(self, form):
        messages.success(self.request, f'Unidad {form.instance.numero_economico} actualizada exitosamente.')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Error al actualizar la unidad. Verifique los datos.')
        return super().form_invalid(form)


class UnidadDeleteView(LoginRequiredMixin, DeleteView):
    """Vista para eliminar una unidad"""
    model = Unidad
    template_name = 'unidades/unidad_confirm_delete.html'

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse('unidades:list')

    def delete(self, request, *args, **kwargs):
        unidad = self.get_object()
        messages.success(request, f'Unidad {unidad.numero_economico} eliminada exitosamente.')
        return super().delete(request, *args, **kwargs)


@login_required
def asignar_pieza_unidad(request, pk):
    """Asignar una pieza del almacén a la unidad para reparación rápida"""
    unidad = get_object_or_404(Unidad, pk=pk)

    if request.method == 'POST':
        form = AsignacionDirectaAlmacenForm(request.POST)
        if form.is_valid():
            asignacion = form.save(commit=False)
            asignacion.unidad = unidad
            asignacion.entregado_por = request.user
            asignacion.observacion_interna = 'ASIGNACION DIRECTA'
            asignacion.save()

            # Reducir stock y crear movimiento
            producto = asignacion.producto
            cantidad_anterior = producto.cantidad
            producto.reducir_stock(asignacion.cantidad)

            MovimientoAlmacen.objects.create(
                tipo='SALIDA',
                producto_almacen=producto,
                cantidad=-asignacion.cantidad,
                cantidad_anterior=cantidad_anterior,
                cantidad_posterior=producto.cantidad,
                usuario=request.user,
                observaciones=(
                    f'Asignación directa {asignacion.folio} a {unidad} - {asignacion.motivo}'
                )
            )

            messages.success(
                request,
                f'Pieza asignada. Folio: {asignacion.folio} - '
                f'{asignacion.cantidad} {producto.unidad_medida} de '
                f'{producto.descripcion} a {unidad.numero_economico}'
            )
            return redirect(f"{reverse('unidades:detail', args=[pk])}?tab=almacen")
        else:
            messages.error(request, 'Error al registrar la asignación. Verifique los datos.')
            return redirect(f"{reverse('unidades:detail', args=[pk])}?tab=almacen")

    return redirect('unidades:detail', pk=pk)


# Vista funcional para dashboard
def unidad_dashboard(request):
    """Dashboard de unidades con estadísticas generales"""
    unidades = Unidad.objects.all()
    
    context = {
        'total_unidades': unidades.count(),
        'unidades_activas': unidades.filter(activa=True).count(),
        'unidades_inactivas': unidades.filter(activa=False).count(),
        'unidades_por_tipo': {
            tipo[0]: unidades.filter(tipo=tipo[0]).count()
            for tipo in Unidad.TIPO_CHOICES
        },
        'unidades_recientes': unidades.order_by('-created_at')[:5],
        'unidades_mantenimiento': [
            u for u in unidades.filter(activa=True) 
            if u.requiere_mantenimiento()
        ],
    }
    return render(request, 'unidades/unidad_dashboard.html', context)
