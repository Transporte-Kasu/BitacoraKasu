from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.db.models import Q

from .models import Equipo
from .forms import EquipoForm, FiltroEquiposForm


class EquipoListView(LoginRequiredMixin, ListView):
    model = Equipo
    template_name = 'equipos/equipo_list.html'
    context_object_name = 'equipos'
    paginate_by = None

    def get_queryset(self):
        qs = Equipo.objects.all()
        buscar = self.request.GET.get('buscar', '').strip()
        tipo = self.request.GET.get('tipo', '')
        activo = self.request.GET.get('activo', '')

        if buscar:
            qs = qs.filter(
                Q(numero_economico__icontains=buscar) |
                Q(placas__icontains=buscar) |
                Q(numero_serie__icontains=buscar) |
                Q(marca__icontains=buscar)
            )
        if tipo:
            qs = qs.filter(tipo=tipo)
        if activo in ('1', '0'):
            qs = qs.filter(activo=(activo == '1'))

        return qs.order_by('numero_economico')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total'] = Equipo.objects.count()
        ctx['activos'] = Equipo.objects.filter(activo=True).count()

        equipos_qs = ctx['equipos']
        grupos = {}
        for tipo_key, tipo_label in [('CHASIS', 'Chasis'), ('PLANA', 'Plana'), ('OTRO', 'Otro')]:
            items = [e for e in equipos_qs if e.tipo == tipo_key]
            if items:
                grupos[tipo_key] = {'label': tipo_label, 'items': items}
        ctx['grupos_equipos'] = grupos
        return ctx


class EquipoDetailView(LoginRequiredMixin, DetailView):
    model = Equipo
    template_name = 'equipos/equipo_detail.html'
    context_object_name = 'equipo'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['asignaciones_salida'] = self.object.asignaciones_salida.prefetch_related('items').order_by('-creado_en')[:20]
        ctx['total_asignaciones'] = self.object.asignaciones_salida.count()
        return ctx


class EquipoCreateView(LoginRequiredMixin, CreateView):
    model = Equipo
    form_class = EquipoForm
    template_name = 'equipos/equipo_form.html'
    success_url = reverse_lazy('equipos:list')

    def form_valid(self, form):
        messages.success(self.request, f'Equipo {form.instance.numero_economico} creado.')
        return super().form_valid(form)


class EquipoUpdateView(LoginRequiredMixin, UpdateView):
    model = Equipo
    form_class = EquipoForm
    template_name = 'equipos/equipo_form.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        return next_url or reverse('equipos:list')

    def form_valid(self, form):
        messages.success(self.request, f'Equipo {form.instance.numero_economico} actualizado.')
        return super().form_valid(form)


class EquipoDeleteView(LoginRequiredMixin, DeleteView):
    model = Equipo
    template_name = 'equipos/equipo_confirm_delete.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    success_url = reverse_lazy('equipos:list')

    def form_valid(self, form):
        messages.success(self.request, 'Equipo eliminado.')
        return super().form_valid(form)
