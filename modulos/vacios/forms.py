from django import forms

from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad

from .models import CambioOperadorVacio, Naviera, RetrasoVacio, Vacio
from .services import operadores_libres

_INPUT = 'form-control border border-gray-300 rounded-lg px-3 py-2 w-full text-sm'


class NavieraForm(forms.ModelForm):
    class Meta:
        model = Naviera
        fields = ['nombre', 'direccion_retorno', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': _INPUT}),
            'direccion_retorno': forms.Textarea(attrs={'class': _INPUT, 'rows': 2}),
            'activo': forms.CheckboxInput(),
        }


class VacioUpdateForm(forms.ModelForm):
    class Meta:
        model = Vacio
        fields = ['naviera', 'agencia', 'fecha_compromiso_naviera', 'observaciones']
        widgets = {
            'naviera': forms.Select(attrs={'class': _INPUT}),
            'agencia': forms.Select(attrs={'class': _INPUT}),
            'fecha_compromiso_naviera': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'class': _INPUT, 'type': 'datetime-local'},
            ),
            'observaciones': forms.Textarea(attrs={'class': _INPUT, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['naviera'].queryset = Naviera.objects.filter(activo=True)
        self.fields['naviera'].required = False
        self.fields['agencia'].required = False
        self.fields['fecha_compromiso_naviera'].required = False


class AsignarUnidadOperadorVacioForm(forms.ModelForm):
    """Asigna unidad + operador libre. El operador se auto-llena en el navegador."""

    class Meta:
        model = Vacio
        fields = ['unidad', 'operador']
        widgets = {
            'unidad': forms.Select(attrs={'class': _INPUT, 'id': 'id_unidad'}),
            'operador': forms.Select(attrs={'class': _INPUT, 'id': 'id_operador'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unidad'].queryset = Unidad.objects.filter(tipo='LOCAL', activa=True)
        self.fields['unidad'].required = True
        self.fields['operador'].queryset = operadores_libres()
        self.fields['operador'].required = True


class ReasignarOperadorVacioForm(forms.Form):
    unidad_entrante = forms.ModelChoiceField(
        queryset=Unidad.objects.filter(tipo='LOCAL', activa=True),
        widget=forms.Select(attrs={'class': _INPUT, 'id': 'id_unidad'}),
    )
    operador_entrante = forms.ModelChoiceField(
        queryset=Operador.objects.none(),
        widget=forms.Select(attrs={'class': _INPUT, 'id': 'id_operador'}),
    )
    causa = forms.ChoiceField(
        choices=CambioOperadorVacio.CAUSA_CHOICES,
        widget=forms.Select(attrs={'class': _INPUT}),
    )
    motivo = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': _INPUT, 'rows': 2}),
    )

    def __init__(self, *args, vacio=None, **kwargs):
        super().__init__(*args, **kwargs)
        libres = operadores_libres()
        self.sin_operadores_libres = not libres.exists()
        if self.sin_operadores_libres:
            # Sin operadores libres: se ofrecen todos los LOCAL activos como
            # último recurso; la plantilla avisa de la situación.
            self.fields['operador_entrante'].queryset = Operador.objects.filter(
                tipo='LOCAL', activo=True
            )
        else:
            self.fields['operador_entrante'].queryset = libres


class RetrasoVacioForm(forms.ModelForm):
    class Meta:
        model = RetrasoVacio
        fields = ['tipo', 'motivo', 'fecha_estimada_nueva']
        widgets = {
            'tipo': forms.Select(attrs={'class': _INPUT}),
            'motivo': forms.Textarea(attrs={'class': _INPUT, 'rows': 3}),
            'fecha_estimada_nueva': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'class': _INPUT, 'type': 'date'},
            ),
        }
