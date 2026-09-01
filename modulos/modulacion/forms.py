from django import forms

from modulos.bitacoras.models import Cliente
from modulos.operadores.models import Operador
from modulos.unidades.models import Unidad

from .models import Agencia, Modulacion, TerminalPortuaria


class AgenciaForm(forms.ModelForm):
    class Meta:
        model = Agencia
        fields = ['nombre', 'email_contacto', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la agencia'}),
            'email_contacto': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'avisos@agencia.com'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class TerminalPortuariaForm(forms.ModelForm):
    class Meta:
        model = TerminalPortuaria
        fields = ['nombre', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la terminal'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ModulacionForm(forms.ModelForm):
    """Formulario de captura manual (origen='MANUAL')."""

    class Meta:
        model = Modulacion
        fields = [
            'agencia', 'terminal_portuaria', 'tipo_contenedor', 'peso_toneladas',
            'contenedor', 'cliente', 'num_pedimento', 'num_doda', 'observaciones',
        ]
        widgets = {
            'agencia': forms.Select(attrs={'class': 'form-control'}),
            'terminal_portuaria': forms.Select(attrs={'class': 'form-control'}),
            'tipo_contenedor': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. 40HC, 20DC',
            }),
            'peso_toneladas': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'contenedor': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ABCU1234567',
                'oninput': 'this.value=this.value.toUpperCase()',
            }),
            'cliente': forms.Select(attrs={'class': 'form-control'}),
            'num_pedimento': forms.TextInput(attrs={'class': 'form-control'}),
            'num_doda': forms.TextInput(attrs={'class': 'form-control'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['agencia'].queryset = Agencia.objects.filter(activo=True)
        self.fields['terminal_portuaria'].queryset = TerminalPortuaria.objects.filter(activo=True)
        self.fields['cliente'].queryset = Cliente.objects.filter(activo=True)
        self.fields['cliente'].required = False


class AsignarUnidadOperadorForm(forms.ModelForm):
    """
    Asigna una unidad y un operador local a una Modulación desde una acción
    dedicada en el detalle. El operador se auto-llena en el navegador cuando
    la unidad elegida tiene un operador ligado (Operador.unidad_asignada),
    pero sigue siendo editable: permite reasignar solamente el operador.
    """

    class Meta:
        model = Modulacion
        fields = ['unidad', 'operador']
        widgets = {
            'unidad': forms.Select(attrs={'class': 'form-control', 'id': 'id_unidad'}),
            'operador': forms.Select(attrs={'class': 'form-control', 'id': 'id_operador'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unidad'].queryset = Unidad.objects.filter(tipo='LOCAL', activa=True)
        self.fields['unidad'].required = True
        self.fields['operador'].queryset = Operador.objects.filter(tipo='LOCAL', activo=True)
        self.fields['operador'].required = True


class PromoverBitacoraForm(forms.Form):
    """
    Datos operativos requeridos para crear el BitacoraViaje (modalidad
    SENCILLO / foráneo) al promover una Modulación: operador, unidad, destino
    y fechas — los datos del contenedor (cliente, contenedor, peso, tipo) ya
    vienen de la Modulación. Operador y unidad se listan solo entre los
    foráneos.
    """
    operador = forms.ModelChoiceField(
        queryset=Operador.objects.filter(tipo='FORANEO', activo=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    unidad = forms.ModelChoiceField(
        queryset=Unidad.objects.filter(tipo='FORANEA', activa=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    fecha_carga = forms.DateTimeField(
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
            'class': 'form-control', 'type': 'datetime-local',
        }),
    )
    fecha_salida = forms.DateTimeField(
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={
            'class': 'form-control', 'type': 'datetime-local',
        }),
    )
    destino = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Dirección de entrega'}),
    )
    cp_destino = forms.CharField(
        max_length=10, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Código postal de destino'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ocultar unidades con 2 contenedores en curso (capacidad llena).
        from modulos.bitacoras.services_full import unidades_bloqueadas_ids
        bloqueadas = unidades_bloqueadas_ids()
        if bloqueadas:
            self.fields['unidad'].queryset = self.fields['unidad'].queryset.exclude(
                id__in=bloqueadas
            )

    def clean(self):
        cleaned_data = super().clean()
        fecha_carga = cleaned_data.get('fecha_carga')
        fecha_salida = cleaned_data.get('fecha_salida')
        if fecha_carga and fecha_salida and fecha_salida < fecha_carga:
            self.add_error('fecha_salida', 'La fecha de salida no puede ser anterior a la de carga.')
        return cleaned_data


class RetiroExternoForm(forms.Form):
    """Datos requeridos cuando el retiro del Patio Esperanza lo hace un tercero."""
    transportista_externo = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del transportista'}),
    )
