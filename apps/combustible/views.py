from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, View
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.http import JsonResponse
from .models import CargaCombustible, Despachador
from .forms import (
    Paso1Form, Paso2Form, Paso3Form, Paso4Form, Paso5Form, Paso6Form
)


class CargaCombustibleWizardView(LoginRequiredMixin, View):
    """Vista principal para el proceso de carga paso a paso"""

    def get(self, request, paso=1):
        # Obtener o iniciar sesión de carga
        carga_id = request.session.get('carga_combustible_id')

        if paso == 1:
            # Limpiar sesión anterior si es paso 1
            if 'carga_combustible_id' in request.session:
                del request.session['carga_combustible_id']
            form = Paso1Form()
        elif paso == 2:
            form = Paso2Form()
        elif paso == 3:
            form = Paso3Form()
        elif paso == 4:
            form = Paso4Form()
            # Obtener datos para mostrar resumen
            if carga_id:
                carga = get_object_or_404(CargaCombustible, id=carga_id)
                context = {
                    'form': form,
                    'paso': paso,
                    'carga': carga,
                    'total_pasos': 6
                }
                return render(request, 'combustible/wizard_paso4.html', context)
        elif paso == 5:
            form = Paso5Form()
        elif paso == 6:
            form = Paso6Form()
        else:
            return redirect('combustible:wizard', paso=1)

        context = {
            'form': form,
            'paso': paso,
            'total_pasos': 6,
            'progreso': int((paso / 6) * 100)
        }

        return render(request, f'combustible/wizard_paso{paso}.html', context)

    def post(self, request, paso=1):
        carga_id = request.session.get('carga_combustible_id')

        if paso == 1:
            form = Paso1Form(request.POST, request.FILES)
            if form.is_valid():
                # Crear nueva carga
                carga = CargaCombustible(
                    despachador=form.cleaned_data['despachador'],
                    unidad=form.cleaned_data['unidad'],
                    foto_numero_economico=form.cleaned_data['foto_numero_economico'],
                    fecha_hora_inicio=timezone.now(),
                    estado='INICIADO',
                    # Valores temporales que se actualizarán después
                    cantidad_litros=0,
                    kilometraje_actual=0,
                    nivel_combustible_inicial='VACIO',
                    estado_candado_anterior='NORMAL'
                )
                carga.save()
                request.session['carga_combustible_id'] = carga.id
                messages.success(request, '✓ Paso 1 completado: Unidad confirmada')
                return redirect('combustible:wizard', paso=2)

        elif paso == 2:
            form = Paso2Form(request.POST, request.FILES)
            if form.is_valid() and carga_id:
                carga = get_object_or_404(CargaCombustible, id=carga_id)
                carga.foto_tablero = form.cleaned_data['foto_tablero']
                carga.kilometraje_actual = form.cleaned_data['kilometraje_actual']
                carga.nivel_combustible_inicial = form.cleaned_data['nivel_combustible_inicial']
                carga.save()
                messages.success(request, '✓ Paso 2 completado: Kilometraje registrado')
                return redirect('combustible:wizard', paso=3)

        elif paso == 3:
            form = Paso3Form(request.POST, request.FILES)
            if form.is_valid() and carga_id:
                carga = get_object_or_404(CargaCombustible, id=carga_id)
                carga.foto_candado_anterior = form.cleaned_data['foto_candado_anterior']
                carga.estado_candado_anterior = form.cleaned_data['estado_candado_anterior']
                carga.observaciones_candado = form.cleaned_data['observaciones_candado']
                carga.save()

                # Alerta si hay problema con el candado
                if carga.tiene_alertas():
                    messages.warning(
                        request,
                        f'⚠️ Alerta: Candado {carga.get_estado_candado_anterior_display()}'
                    )

                messages.success(request, '✓ Paso 3 completado: Candado anterior registrado')
                return redirect('combustible:wizard', paso=4)

        elif paso == 4:
            form = Paso4Form(request.POST)
            if form.is_valid() and carga_id:
                carga = get_object_or_404(CargaCombustible, id=carga_id)
                carga.cantidad_litros = form.cleaned_data['cantidad_litros']
                carga.save()
                messages.success(request, '✓ Paso 4 completado: Cantidad registrada')
                return redirect('combustible:wizard', paso=5)

        elif paso == 5:
            form = Paso5Form(request.POST, request.FILES)
            if form.is_valid() and carga_id:
                carga = get_object_or_404(CargaCombustible, id=carga_id)
                carga.foto_candado_nuevo = form.cleaned_data['foto_candado_nuevo']
                carga.save()
                messages.success(request, '✓ Paso 5 completado: Candado nuevo registrado')
                return redirect('combustible:wizard', paso=6)

        elif paso == 6:
            form = Paso6Form(request.POST, request.FILES)
            if form.is_valid() and carga_id:
                carga = get_object_or_404(CargaCombustible, id=carga_id)
                carga.foto_ticket = form.cleaned_data['foto_ticket']
                carga.notas = form.cleaned_data['notas']
                carga.finalizar_carga()

                # Limpiar sesión
                del request.session['carga_combustible_id']

                messages.success(
                    request,
                    f'✓ ¡Carga completada exitosamente! Tiempo total: {carga.tiempo_carga_minutos} minutos'
                )
                return redirect('combustible:detalle', pk=carga.id)

        # Si hay errores, mostrar el formulario con errores
        context = {
            'form': form,
            'paso': paso,
            'total_pasos': 6,
            'progreso': int((paso / 6) * 100)
        }
        return render(request, f'combustible/wizard_paso{paso}.html', context)


class IniciarCargaView(LoginRequiredMixin, View):
    """Vista AJAX para iniciar el cronómetro de carga"""

    def post(self, request, pk):
        carga = get_object_or_404(CargaCombustible, id=pk)
        carga.iniciar_carga()
        return JsonResponse({
            'status': 'success',
            'mensaje': 'Carga iniciada',
            'hora_inicio': carga.fecha_hora_inicio.strftime('%H:%M:%S')
        })


class FinalizarCargaView(LoginRequiredMixin, View):
    """Vista AJAX para finalizar el cronómetro de carga"""

    def post(self, request, pk):
        carga = get_object_or_404(CargaCombustible, id=pk)
        carga.finalizar_carga()
        return JsonResponse({
            'status': 'success',
            'mensaje': 'Carga finalizada',
            'hora_fin': carga.fecha_hora_fin.strftime('%H:%M:%S'),
            'tiempo_total': carga.tiempo_carga_minutos
        })


class CargaCombustibleListView(LoginRequiredMixin, ListView):
    """Lista de todas las cargas de combustible"""
    model = CargaCombustible
    template_name = 'combustible/carga_list.html'
    context_object_name = 'cargas'
    paginate_by = 20

    def get_queryset(self):
        queryset = CargaCombustible.objects.select_related(
            'despachador', 'unidad'
        ).order_by('-fecha_hora_inicio')

        # Filtros
        unidad = self.request.GET.get('unidad')
        if unidad:
            queryset = queryset.filter(unidad__numero_economico__icontains=unidad)

        estado = self.request.GET.get('estado')
        if estado:
            queryset = queryset.filter(estado=estado)

        return queryset


class CargaCombustibleDetailView(LoginRequiredMixin, DetailView):
    """Detalle de una carga de combustible"""
    model = CargaCombustible
    template_name = 'combustible/carga_detail.html'
    context_object_name = 'carga'


def dashboard_combustible(request):
    """Dashboard principal de combustible"""
    cargas_hoy = CargaCombustible.objects.filter(
        fecha_hora_inicio__date=timezone.now().date()
    )

    context = {
        'total_cargas_hoy': cargas_hoy.count(),
        'cargas_completadas_hoy': cargas_hoy.filter(estado='COMPLETADO').count(),
        'cargas_en_proceso': CargaCombustible.objects.filter(estado='EN_PROCESO').count(),
        'total_litros_hoy': sum(c.cantidad_litros for c in cargas_hoy.filter(estado='COMPLETADO')),
        'alertas_candado': CargaCombustible.objects.filter(
            estado_candado_anterior__in=['ALTERADO', 'VIOLADO', 'SIN_CANDADO'],
            fecha_hora_inicio__date=timezone.now().date()
        ).count(),
        'ultimas_cargas': CargaCombustible.objects.select_related(
            'despachador', 'unidad'
        ).order_by('-fecha_hora_inicio')[:10],
    }
    return render(request, 'combustible/dashboard.html', context)