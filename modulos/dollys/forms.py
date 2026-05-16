from django import forms
from .models import Dolly


class DollyForm(forms.ModelForm):
    class Meta:
        model = Dolly
        fields = ['numero_economico', 'marca', 'color', 'numero_serie', 'activo']

    def clean_numero_economico(self):
        return self.cleaned_data.get('numero_economico', '').upper().strip()

    def clean_numero_serie(self):
        return self.cleaned_data.get('numero_serie', '').strip()


class FiltroDollysForm(forms.Form):
    buscar = forms.CharField(required=False, label='Buscar')
    marca = forms.CharField(required=False, label='Marca')
    activo = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos'), ('1', 'Activos'), ('0', 'Inactivos')]
    )
