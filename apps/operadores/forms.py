from django import forms
from .models import Operador


class OperadorForm(forms.ModelForm):
    """Formulario para crear y editar operadores"""
    
    class Meta:
        model = Operador
        fields = [
            'nombre', 'tipo', 'unidad_asignada', 'licencia',
            'telefono', 'email', 'activo', 'fecha_baja', 'notas'
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre completo del operador'
            }),
            'tipo': forms.Select(attrs={
                'class': 'form-control'
            }),
            'unidad_asignada': forms.Select(attrs={
                'class': 'form-control'
            }),
            'licencia': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de licencia'
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '(área) número'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'correo@ejemplo.com'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'fecha_baja': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notas': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Notas adicionales sobre el operador'
            }),
        }
    
    def clean_telefono(self):
        """Validación personalizada para teléfono"""
        telefono = self.cleaned_data.get('telefono')
        if telefono:
            # Remover caracteres no numéricos
            telefono_limpio = ''.join(filter(str.isdigit, telefono))
            if len(telefono_limpio) < 10:
                raise forms.ValidationError('El teléfono debe tener al menos 10 dígitos')
        return telefono
    
    def clean(self):
        """Validaciones personalizadas del formulario"""
        cleaned_data = super().clean()
        activo = cleaned_data.get('activo')
        fecha_baja = cleaned_data.get('fecha_baja')
        
        # Si está inactivo, debe tener fecha de baja
        if not activo and not fecha_baja:
            raise forms.ValidationError(
                'Debe especificar una fecha de baja para operadores inactivos'
            )
        
        # Si está activo, no debe tener fecha de baja
        if activo and fecha_baja:
            raise forms.ValidationError(
                'Los operadores activos no pueden tener fecha de baja'
            )
        
        return cleaned_data
