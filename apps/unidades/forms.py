from django import forms
from .models import Unidad
from datetime import date


class UnidadForm(forms.ModelForm):
    """Formulario para crear y editar unidades"""
    
    class Meta:
        model = Unidad
        fields = [
            'numero_economico', 'placa', 'tipo', 'marca', 'modelo', 'año',
            'capacidad_combustible', 'rendimiento_esperado', 'kilometraje_actual',
            'activa', 'fecha_baja', 'ultimo_mantenimiento', 'proximo_mantenimiento',
            'notas'
        ]
        widgets = {
            'numero_economico': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: U001'
            }),
            'placa': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: ABC-123-D'
            }),
            'tipo': forms.Select(attrs={
                'class': 'form-control'
            }),
            'marca': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Kenworth'
            }),
            'modelo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: T680'
            }),
            'año': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1990,
                'max': 2030
            }),
            'capacidad_combustible': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Litros'
            }),
            'rendimiento_esperado': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'km/litro'
            }),
            'kilometraje_actual': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Kilómetros'
            }),
            'activa': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'fecha_baja': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'ultimo_mantenimiento': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'proximo_mantenimiento': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notas': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Notas adicionales sobre la unidad'
            }),
        }
    
    def clean_numero_economico(self):
        """Validación personalizada para número económico"""
        numero = self.cleaned_data.get('numero_economico')
        if numero:
            numero = numero.upper()
        return numero
    
    def clean_placa(self):
        """Validación personalizada para placa"""
        placa = self.cleaned_data.get('placa')
        if placa:
            placa = placa.upper()
        return placa
    
    def clean_año(self):
        """Validación del año"""
        año = self.cleaned_data.get('año')
        if año:
            current_year = date.today().year
            if año < 1990:
                raise forms.ValidationError('El año debe ser mayor a 1990')
            if año > current_year + 1:
                raise forms.ValidationError(f'El año no puede ser mayor a {current_year + 1}')
        return año
    
    def clean_proximo_mantenimiento(self):
        """Validar que el próximo mantenimiento sea futuro"""
        proximo = self.cleaned_data.get('proximo_mantenimiento')
        ultimo = self.cleaned_data.get('ultimo_mantenimiento')
        
        if proximo and ultimo:
            if proximo <= ultimo:
                raise forms.ValidationError(
                    'El próximo mantenimiento debe ser posterior al último mantenimiento'
                )
        
        return proximo
    
    def clean(self):
        """Validaciones personalizadas del formulario"""
        cleaned_data = super().clean()
        activa = cleaned_data.get('activa')
        fecha_baja = cleaned_data.get('fecha_baja')
        
        # Si está inactiva, debe tener fecha de baja
        if not activa and not fecha_baja:
            raise forms.ValidationError(
                'Debe especificar una fecha de baja para unidades inactivas'
            )
        
        # Si está activa, no debe tener fecha de baja
        if activa and fecha_baja:
            raise forms.ValidationError(
                'Las unidades activas no pueden tener fecha de baja'
            )
        
        return cleaned_data
