from django import forms
from .models import Equipo


class EquipoForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = [
            'numero_economico', 'tipo', 'placas', 'marca', 'modelo',
            'color', 'numero_serie', 'vigencia_doble_articulado',
            'verificacion', 'activo',
        ]
        widgets = {
            'vigencia_doble_articulado': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_numero_economico(self):
        return self.cleaned_data.get('numero_economico', '').upper().strip()

    def clean_numero_serie(self):
        return self.cleaned_data.get('numero_serie', '').strip()


class FiltroEquiposForm(forms.Form):
    buscar = forms.CharField(required=False, label='Buscar')
    tipo = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos los tipos')] + list(Equipo.TIPO_CHOICES)
    )
    marca = forms.CharField(required=False, label='Marca')
    activo = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos'), ('1', 'Activos'), ('0', 'Inactivos')]
    )
