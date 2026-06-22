import re
from django import forms
from .models import BitacoraViaje, Cliente


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nombre', 'email', 'celular', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del cliente'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@empresa.com'}),
            'celular': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+52 753 123 4567'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

_CONTAINER_RE = re.compile(r'^[A-Z]{3}U\d{7}$')


class BitacoraViajeForm(forms.ModelForm):
    """Formulario para crear y editar bitácoras de viaje"""

    class Meta:
        model = BitacoraViaje
        fields = [
            'cliente',
            'modalidad',
            'operador', 'unidad',
            'salida_a_ruta',
            'fecha_salida',
            # Contenedor 1
            'contenedor', 'tipo_contenedor', 'peso', 'sellos',
            # Contenedor 2 (solo FULL)
            'contenedor_2', 'peso_2', 'sellos_2',
            'reparto',
            # Destino
            'cp_origen', 'cp_destino', 'cp_destino_2', 'destino',
            # Opcional
            'observaciones',
        ]
        widgets = {
            'cliente': forms.Select(attrs={
                'class': 'form-control',
            }),
            'modalidad': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_modalidad',
            }),
            'operador': forms.Select(attrs={
                'class': 'form-control',
            }),
            'unidad': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_unidad',
            }),
            'salida_a_ruta': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Folio o referencia de salida',
            }),
            'fecha_carga': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'fecha_salida': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            # Contenedor 1
            'contenedor': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ABCU1234567',
                'maxlength': '11',
                'oninput': 'this.value=this.value.toUpperCase()',
                'title': '4 letras (4ª = U) + 7 dígitos, ej. ABCU1234567',
            }),
            'tipo_contenedor': forms.Select(attrs={
                'class': 'form-control',
            }),
            'peso': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Peso en toneladas',
            }),
            'sellos': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Números de sellos',
            }),
            # Contenedor 2
            'contenedor_2': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ABCU1234567',
                'maxlength': '11',
                'oninput': 'this.value=this.value.toUpperCase()',
                'title': '4 letras (4ª = U) + 7 dígitos, ej. ABCU1234567',
            }),
            'peso_2': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Peso en toneladas',
            }),
            'sellos_2': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Números de sellos del segundo contenedor',
            }),
            'reparto': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            # Destino
            'cp_origen': forms.TextInput(attrs={
                'class': 'form-control',
                'readonly': True,
            }),
            'cp_destino': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_cp_destino',
                'placeholder': 'Código postal de destino',
                'maxlength': '10',
            }),
            'cp_destino_2': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_cp_destino_2',
                'placeholder': 'CP destino segundo contenedor',
                'maxlength': '10',
            }),
            'destino': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Descripción del destino',
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Observaciones del viaje',
            }),
        }

    def _validar_numero_contenedor(self, valor, field_name):
        val = (valor or '').strip().upper()
        if val and not _CONTAINER_RE.match(val):
            raise forms.ValidationError(
                'Formato incorrecto. Debe ser 3 letras mayúsculas + U + 7 dígitos (ej. ABCU1234567).'
            )
        return val

    def clean_contenedor(self):
        return self._validar_numero_contenedor(self.cleaned_data.get('contenedor'), 'contenedor')

    def clean_contenedor_2(self):
        return self._validar_numero_contenedor(self.cleaned_data.get('contenedor_2'), 'contenedor_2')

    def clean(self):
        cleaned_data = super().clean()
        modalidad = cleaned_data.get('modalidad')
        contenedor_2 = cleaned_data.get('contenedor_2')
        reparto = cleaned_data.get('reparto')

        if modalidad in ('FULL', 'LOCAL_FULL') and not contenedor_2:
            self.add_error('contenedor_2', 'Full y Local Full requieren el segundo contenedor.')

        if modalidad in ('SENCILLO', 'LOCAL'):
            if contenedor_2:
                self.add_error('contenedor_2', 'SENCILLO y LOCAL no pueden tener segundo contenedor.')
            if reparto:
                self.add_error('reparto', 'SENCILLO y LOCAL no usan reparto.')

        if modalidad == 'LOCAL_FULL' and reparto:
            self.add_error('reparto', 'Local Full no usa reparto.')

        return cleaned_data


class BitacoraViajeCompletarForm(forms.ModelForm):
    """Formulario para completar un viaje (agregar datos de llegada)"""

    class Meta:
        model = BitacoraViaje
        fields = ['fecha_llegada', 'kilometraje_llegada', 'observaciones']
        widgets = {
            'fecha_llegada': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'kilometraje_llegada': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Kilometraje al llegar',
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Observaciones finales del viaje',
            }),
        }

    def clean_fecha_llegada(self):
        fecha_llegada = self.cleaned_data.get('fecha_llegada')
        if fecha_llegada and self.instance.fecha_salida:
            if fecha_llegada < self.instance.fecha_salida:
                raise forms.ValidationError(
                    'La fecha de llegada no puede ser anterior a la fecha de salida.'
                )
        return fecha_llegada

    def clean_kilometraje_llegada(self):
        kilometraje_llegada = self.cleaned_data.get('kilometraje_llegada')
        if kilometraje_llegada and self.instance.kilometraje_salida:
            if kilometraje_llegada < self.instance.kilometraje_salida:
                raise forms.ValidationError(
                    f'El kilometraje de llegada ({kilometraje_llegada} km) debe ser mayor '
                    f'al de salida ({self.instance.kilometraje_salida} km).'
                )
        return kilometraje_llegada

    def clean(self):
        cleaned_data = super().clean()
        fecha_llegada = cleaned_data.get('fecha_llegada')
        kilometraje_llegada = cleaned_data.get('kilometraje_llegada')

        if fecha_llegada and not kilometraje_llegada:
            raise forms.ValidationError('Debe especificar el kilometraje de llegada.')
        if kilometraje_llegada and not fecha_llegada:
            raise forms.ValidationError('Debe especificar la fecha de llegada.')

        return cleaned_data
