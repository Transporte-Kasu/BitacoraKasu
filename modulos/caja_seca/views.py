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
    paginate_by = 25

    def get_queryset(self):
        qs = CajaSeca.objects.all()
        buscar = self.request.GET.get('buscar', '').strip()
        marca = self.request.GET.get('marca', '').strip()
        activo = self.request.GET.get('activo', '')

        if buscar:
            qs = qs.filter(
                Q(numero_economico__icontains=buscar) |
                Q(placas__icontains=buscar) |
                Q(numero_serie__icontains=buscar) |
                Q(marca__icontains=buscar)
            )
        if marca:
            qs = qs.filter(marca__icontains=marca)
        if activo in ('1', '0'):
            qs = qs.filter(activo=(activo == '1'))

        return qs.order_by('numero_economico')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filtro_form'] = FiltroCajaSecaForm(self.request.GET)
        ctx['total'] = CajaSeca.objects.count()
        ctx['activos'] = CajaSeca.objects.filter(activo=True).count()
        params = self.request.GET.copy()
        params.pop('page', None)
        ctx['filtro_params'] = params.urlencode()
        return ctx


class CajaSecaDetailView(LoginRequiredMixin, DetailView):
    model = CajaSeca
    template_name = 'caja_seca/caja_detail.html'
    context_object_name = 'caja'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        c = self.object
        ctx['campos'] = [
            ('Número económico', c.numero_economico, False),
            ('Placas', c.placas, False),
            ('No. de serie', c.numero_serie, True),
            ('Marca', c.marca, False),
            ('Modelo', c.modelo, False),
            ('Año', c.anio, False),
            ('Color', c.color, False),
        ]
        ctx['asignaciones_salida'] = self.object.asignaciones_salida.prefetch_related('items').order_by('-creado_en')[:20]
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
