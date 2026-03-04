from django import forms
from .models import ConfiguracionReporte

_INPUT = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm min-h-[44px] focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200'
_TEXTAREA = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200'
_SELECT = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm min-h-[44px] bg-white focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200'


class ConfiguracionReporteForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionReporte
        fields = [
            'nombre', 'modulo', 'tipo_reporte', 'frecuencia',
            'dia_semana', 'dia_mes', 'destinatarios', 'activo', 'adjuntar_excel',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Ej: Inventario semanal de almacén'}),
            'modulo': forms.Select(attrs={'class': _SELECT}),
            'tipo_reporte': forms.Select(attrs={'class': _SELECT}),
            'frecuencia': forms.Select(attrs={'class': _SELECT, 'id': 'id_frecuencia'}),
            'dia_semana': forms.Select(attrs={'class': _SELECT}),
            'dia_mes': forms.NumberInput(attrs={'class': _INPUT, 'min': 1, 'max': 28, 'placeholder': '1-28'}),
            'destinatarios': forms.Textarea(attrs={
                'class': _TEXTAREA, 'rows': 3,
                'placeholder': 'correo1@empresa.com, correo2@empresa.com',
            }),
            'activo': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-blue-600 rounded'}),
            'adjuntar_excel': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-green-600 rounded'}),
        }
