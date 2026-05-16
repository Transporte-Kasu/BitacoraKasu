from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.db.models import Q

from .models import Dolly
from .forms import DollyForm, FiltroDollysForm


class DollyListView(LoginRequiredMixin, ListView):
    model = Dolly
    template_name = 'dollys/dolly_list.html'
    context_object_name = 'dollys'
    paginate_by = 25

    def get_queryset(self):
        qs = Dolly.objects.all()
        buscar = self.request.GET.get('buscar', '').strip()
        marca = self.request.GET.get('marca', '').strip()
        activo = self.request.GET.get('activo', '')

        if buscar:
            qs = qs.filter(
                Q(numero_economico__icontains=buscar) |
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
        ctx['filtro_form'] = FiltroDollysForm(self.request.GET)
        ctx['total'] = Dolly.objects.count()
        ctx['activos'] = Dolly.objects.filter(activo=True).count()
        params = self.request.GET.copy()
        params.pop('page', None)
        ctx['filtro_params'] = params.urlencode()
        return ctx


class DollyDetailView(LoginRequiredMixin, DetailView):
    model = Dolly
    template_name = 'dollys/dolly_detail.html'
    context_object_name = 'dolly'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        d = self.object
        ctx['campo_list'] = [
            ('Número económico', d.numero_economico, False),
            ('Marca', d.marca, False),
            ('Color', d.color, False),
            ('No. de serie', d.numero_serie, True),
        ]
        ctx['asignaciones_salida'] = self.object.asignaciones_salida.prefetch_related('items').order_by('-creado_en')[:20]
        return ctx


class DollyCreateView(LoginRequiredMixin, CreateView):
    model = Dolly
    form_class = DollyForm
    template_name = 'dollys/dolly_form.html'
    success_url = reverse_lazy('dollys:list')

    def form_valid(self, form):
        messages.success(self.request, f'Dolly {form.instance.numero_economico} creado.')
        return super().form_valid(form)


class DollyUpdateView(LoginRequiredMixin, UpdateView):
    model = Dolly
    form_class = DollyForm
    template_name = 'dollys/dolly_form.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        return next_url or reverse('dollys:list')

    def form_valid(self, form):
        messages.success(self.request, f'Dolly {form.instance.numero_economico} actualizado.')
        return super().form_valid(form)


class DollyDeleteView(LoginRequiredMixin, DeleteView):
    model = Dolly
    template_name = 'dollys/dolly_confirm_delete.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    success_url = reverse_lazy('dollys:list')

    def form_valid(self, form):
        messages.success(self.request, 'Dolly eliminado.')
        return super().form_valid(form)
