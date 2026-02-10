from django import forms
from django.forms.widgets import FileInput
from .models import CargaCombustible, Despachador
from modulos.unidades.models import Unidad


class MultipleFileInput(FileInput):
    """Widget que permite seleccionar múltiples archivos"""
    allow_multiple_selected = True


class Paso1Form(forms.Form):
    """Paso 1: Foto del número económico y confirmación de unidad"""
    unidad = forms.ModelChoiceField(
        queryset=Unidad.objects.filter(activa=True),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent'
        }),
        label="Unidad"
    )
    foto_numero_economico = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'hidden',
            'accept': 'image/*',
            'capture': 'environment'
        }),
        label="Foto del número económico"
    )


class Paso2Form(forms.Form):
    """Paso 2: Foto del tablero con kilometraje y nivel de combustible"""
    foto_tablero = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'hidden',
            'accept': 'image/*',
            'capture': 'environment'
        }),
        label="Foto del tablero"
    )
    kilometraje_actual = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-lg',
            'placeholder': 'Ingrese el kilometraje'
        }),
        label="Kilometraje actual"
    )
    nivel_combustible_inicial = forms.ChoiceField(
        choices=CargaCombustible.NIVEL_COMBUSTIBLE_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'form-radio h-5 w-5 text-blue-600'
        }),
        label="Nivel de combustible inicial"
    )


class Paso3Form(forms.Form):
    """Paso 3: Foto y estado del candado anterior"""
    foto_candado_anterior = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'hidden',
            'accept': 'image/*',
            'capture': 'environment'
        }),
        label="Foto del candado anterior"
    )
    estado_candado_anterior = forms.ChoiceField(
        choices=CargaCombustible.ESTADO_CANDADO_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'form-radio h-5 w-5 text-blue-600'
        }),
        label="Estado del candado anterior"
    )
    observaciones_candado = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'rows': 3,
            'placeholder': 'Observaciones adicionales (opcional)'
        }),
        label="Observaciones"
    )


class Paso4Form(forms.Form):
    """Paso 4: Control de inicio/fin de carga"""
    cantidad_litros = forms.DecimalField(
        min_value=0.01,
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-lg',
            'placeholder': 'Ingrese la cantidad de litros',
            'step': '0.01'
        }),
        label="Cantidad de litros a cargar"
    )


class Paso5Form(forms.Form):
    """Paso 5: Fotos del candado nuevo (permite múltiples)"""
    fotos_candado_nuevo = forms.FileField(
        widget=MultipleFileInput(attrs={
            'class': 'hidden',
            'accept': 'image/*',
        }),
        label="Fotos del candado nuevo",
        required=False
    )


class Paso6Form(forms.Form):
    """Paso 6: Foto del ticket o medidor"""
    foto_ticket = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'hidden',
            'accept': 'image/*',
            'capture': 'environment'
        }),
        label="Foto del ticket o medidor"
    )
    notas = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'rows': 3,
            'placeholder': 'Notas finales (opcional)'
        }),
        label="Notas adicionales"
    )


class CargaCombustibleCompleteForm(forms.ModelForm):
    """Formulario completo para edición administrativa"""
    class Meta:
        model = CargaCombustible
        fields = [
            'despachador', 'unidad', 'cantidad_litros', 'kilometraje_actual',
            'nivel_combustible_inicial', 'estado_candado_anterior',
            'observaciones_candado', 'foto_numero_economico', 'foto_tablero',
            'foto_candado_anterior', 'foto_candado_nuevo', 'foto_ticket',
            'estado', 'notas'
        ]
        widgets = {
            'despachador': forms.Select(attrs={'class': 'form-control'}),
            'unidad': forms.Select(attrs={'class': 'form-control'}),
            'cantidad_litros': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'kilometraje_actual': forms.NumberInput(attrs={'class': 'form-control'}),
            'nivel_combustible_inicial': forms.Select(attrs={'class': 'form-control'}),
            'estado_candado_anterior': forms.Select(attrs={'class': 'form-control'}),
            'observaciones_candado': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'estado': forms.Select(attrs={'class': 'form-control'}),
            'notas': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4
            }),
        }