from django import forms
from .models import BitacoraViaje
from django.utils import timezone


class BitacoraViajeForm(forms.ModelForm):
    """Formulario para crear y editar bitácoras de viaje"""
    
    class Meta:
        model = BitacoraViaje
        fields = [
            'operador', 'unidad', 'modalidad', 'contenedor', 'peso',
            'fecha_carga', 'fecha_salida', 'diesel_cargado', 'kilometraje_salida',
            'cp_origen', 'cp_destino', 'destino', 'sellos', 'reparto', 'observaciones'
        ]
        widgets = {
            'operador': forms.Select(attrs={
                'class': 'form-control'
            }),
            'unidad': forms.Select(attrs={
                'class': 'form-control'
            }),
            'modalidad': forms.Select(attrs={
                'class': 'form-control'
            }),
            'contenedor': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de contenedor'
            }),
            'peso': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Peso en kg'
            }),
            'fecha_carga': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'fecha_salida': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'diesel_cargado': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Litros'
            }),
            'kilometraje_salida': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Kilometraje al salir'
            }),
            'cp_origen': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Código postal de origen'
            }),
            'cp_destino': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Código postal de destino'
            }),
            'destino': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción del destino'
            }),
            'sellos': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Números de sellos de seguridad'
            }),
            'reparto': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observaciones del viaje'
            }),
        }
    
    def clean(self):
        """Validaciones personalizadas del formulario"""
        cleaned_data = super().clean()
        fecha_carga = cleaned_data.get('fecha_carga')
        fecha_salida = cleaned_data.get('fecha_salida')
        kilometraje_salida = cleaned_data.get('kilometraje_salida')
        unidad = cleaned_data.get('unidad')
        
        # Validar que fecha_salida sea posterior a fecha_carga
        if fecha_carga and fecha_salida:
            if fecha_salida < fecha_carga:
                raise forms.ValidationError(
                    'La fecha de salida no puede ser anterior a la fecha de carga'
                )
        
        # Validar que el kilometraje de salida sea razonable
        if unidad and kilometraje_salida:
            if kilometraje_salida < unidad.kilometraje_actual:
                raise forms.ValidationError(
                    f'El kilometraje de salida ({kilometraje_salida} km) no puede ser menor '
                    f'al kilometraje actual de la unidad ({unidad.kilometraje_actual} km)'
                )
        
        return cleaned_data


class BitacoraViajeCompletarForm(forms.ModelForm):
    """Formulario para completar un viaje (agregar datos de llegada)"""
    
    class Meta:
        model = BitacoraViaje
        fields = [
            'fecha_llegada', 'kilometraje_llegada', 'observaciones'
        ]
        widgets = {
            'fecha_llegada': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'kilometraje_llegada': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Kilometraje al llegar'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Observaciones finales del viaje'
            }),
        }
    
    def clean_fecha_llegada(self):
        """Validar que la fecha de llegada sea posterior a la salida"""
        fecha_llegada = self.cleaned_data.get('fecha_llegada')
        if fecha_llegada and self.instance.fecha_salida:
            if fecha_llegada < self.instance.fecha_salida:
                raise forms.ValidationError(
                    'La fecha de llegada no puede ser anterior a la fecha de salida'
                )
        return fecha_llegada
    
    def clean_kilometraje_llegada(self):
        """Validar que el kilometraje de llegada sea mayor al de salida"""
        kilometraje_llegada = self.cleaned_data.get('kilometraje_llegada')
        if kilometraje_llegada and self.instance.kilometraje_salida:
            if kilometraje_llegada < self.instance.kilometraje_salida:
                raise forms.ValidationError(
                    f'El kilometraje de llegada ({kilometraje_llegada} km) debe ser mayor '
                    f'al kilometraje de salida ({self.instance.kilometraje_salida} km)'
                )
        return kilometraje_llegada
    
    def clean(self):
        """Validaciones finales"""
        cleaned_data = super().clean()
        
        # Validar que se proporcionen ambos campos
        fecha_llegada = cleaned_data.get('fecha_llegada')
        kilometraje_llegada = cleaned_data.get('kilometraje_llegada')
        
        if fecha_llegada and not kilometraje_llegada:
            raise forms.ValidationError(
                'Debe especificar el kilometraje de llegada'
            )
        
        if kilometraje_llegada and not fecha_llegada:
            raise forms.ValidationError(
                'Debe especificar la fecha de llegada'
            )
        
        return cleaned_data
