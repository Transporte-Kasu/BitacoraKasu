from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.db.models import Q

from .models import CajaSeca
from .forms import CajaSecaForm, FiltroCajaSecaForm


class CajaSecaListView(LoginRequiredMixin, ListView):
    model = CajaSeca
    template_name = 'caja_seca/caja_list.html'
    context_object_name = 'cajas'
    paginate_by = None

    def get_queryset(self):
        qs = CajaSeca.objects.all()
        buscar = self.request.GET.get('buscar', '').strip()
        activo = self.request.GET.get('activo', '')

        if buscar:
            qs = qs.filter(
                Q(numero_economico__icontains=buscar) |
                Q(placas__icontains=buscar) |
                Q(numero_serie__icontains=buscar) |
                Q(marca__icontains=buscar)
            )
        if activo in ('1', '0'):
            qs = qs.filter(activo=(activo == '1'))

        return qs.order_by('numero_economico')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total'] = CajaSeca.objects.count()
        ctx['activos'] = CajaSeca.objects.filter(activo=True).count()

        cajas_qs = ctx['cajas']
        ctx['cajas_activas'] = [c for c in cajas_qs if c.activo]
        ctx['cajas_inactivas'] = [c for c in cajas_qs if not c.activo]
        return ctx


class CajaSecaDetailView(LoginRequiredMixin, DetailView):
    model = CajaSeca
    template_name = 'caja_seca/caja_detail.html'
    context_object_name = 'caja'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['asignaciones_salida'] = self.object.asignaciones_salida.prefetch_related('items').order_by('-creado_en')[:20]
        ctx['total_asignaciones'] = self.object.asignaciones_salida.count()
        return ctx


class CajaSecaCreateView(LoginRequiredMixin, CreateView):
    model = CajaSeca
    form_class = CajaSecaForm
    template_name = 'caja_seca/caja_form.html'
    success_url = reverse_lazy('caja_seca:list')

    def form_valid(self, form):
        messages.success(self.request, f'Caja Seca {form.instance.numero_economico} creada.')
        return super().form_valid(form)


class CajaSecaUpdateView(LoginRequiredMixin, UpdateView):
    model = CajaSeca
    form_class = CajaSecaForm
    template_name = 'caja_seca/caja_form.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        return next_url or reverse('caja_seca:list')

    def form_valid(self, form):
        messages.success(self.request, f'Caja Seca {form.instance.numero_economico} actualizada.')
        return super().form_valid(form)


class CajaSecaDeleteView(LoginRequiredMixin, DeleteView):
    model = CajaSeca
    template_name = 'caja_seca/caja_confirm_delete.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    success_url = reverse_lazy('caja_seca:list')

    def form_valid(self, form):
        messages.success(self.request, 'Caja Seca eliminada.')
        return super().form_valid(form)
