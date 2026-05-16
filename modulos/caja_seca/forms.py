from django import forms
from .models import CajaSeca


class CajaSecaForm(forms.ModelForm):
    class Meta:
        model = CajaSeca
        fields = [
            'numero_economico', 'placas', 'numero_serie', 'marca',
            'modelo', 'anio', 'color', 'activo',
        ]

    def clean_numero_economico(self):
        return self.cleaned_data.get('numero_economico', '').upper().strip()

    def clean_numero_serie(self):
        return self.cleaned_data.get('numero_serie', '').strip()


class FiltroCajaSecaForm(forms.Form):
    buscar = forms.CharField(required=False, label='Buscar')
    marca = forms.CharField(required=False, label='Marca')
    activo = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos'), ('1', 'Activos'), ('0', 'Inactivos')]
    )
