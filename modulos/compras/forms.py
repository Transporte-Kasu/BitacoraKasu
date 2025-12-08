from django import forms
from .models import Proveedor, Producto, Requisicion, ItemRequisicion, OrdenCompra, ItemOrdenCompra


class ProveedorForm(forms.ModelForm):
    """Formulario para crear/editar proveedores"""
    
    class Meta:
        model = Proveedor
        fields = ['nombre', 'rfc', 'direccion', 'telefono', 'email', 'contacto', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Nombre del proveedor'
            }),
            'rfc': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'RFC (sin espacios)',
                'maxlength': '13'
            }),
            'direccion': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'rows': '3',
                'placeholder': 'Dirección completa'
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': '(555) 123-4567'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'email@proveedor.com'
            }),
            'contacto': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Nombre del contacto principal'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500'
            })
        }
    
    def clean_rfc(self):
        rfc = self.cleaned_data.get('rfc', '').upper().strip()
        if rfc:
            # Validar longitud
            if len(rfc) not in [12, 13]:
                raise forms.ValidationError('El RFC debe tener 12 o 13 caracteres')
        return rfc


class ProductoForm(forms.ModelForm):
    """Formulario para crear/editar productos"""
    
    class Meta:
        model = Producto
        fields = ['nombre', 'descripcion', 'unidad_medida', 'categoria', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500',
                'placeholder': 'Nombre del producto'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500',
                'rows': '3',
                'placeholder': 'Descripción detallada del producto'
            }),
            'unidad_medida': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500',
                'placeholder': 'Ej: Pieza, Litro, Kg, Caja'
            }),
            'categoria': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500',
                'placeholder': 'Categoría del producto',
                'list': 'categorias-list'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-green-600 border-gray-300 rounded focus:ring-green-500'
            })
        }


class RequisicionForm(forms.ModelForm):
    """Formulario para crear requisiciones"""
    
    class Meta:
        model = Requisicion
        fields = ['fecha_requerida', 'justificacion']
        widgets = {
            'fecha_requerida': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-yellow-500'
            }),
            'justificacion': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-yellow-500',
                'rows': '4',
                'placeholder': 'Motivo de la requisición'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacer que la fecha requerida sea al menos mañana
        from datetime import date, timedelta
        self.fields['fecha_requerida'].widget.attrs['min'] = (date.today() + timedelta(days=1)).isoformat()


class ItemRequisicionForm(forms.ModelForm):
    """Formulario para agregar items a una requisición"""
    
    class Meta:
        model = ItemRequisicion
        fields = ['producto', 'cantidad', 'descripcion_adicional']
        widgets = {
            'producto': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-yellow-500'
            }),
            'cantidad': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-yellow-500',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.01'
            }),
            'descripcion_adicional': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-yellow-500',
                'rows': '2',
                'placeholder': 'Especificaciones adicionales (opcional)'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar solo productos activos
        self.fields['producto'].queryset = Producto.objects.filter(activo=True).order_by('categoria', 'nombre')


class OrdenCompraForm(forms.ModelForm):
    """Formulario para crear órdenes de compra"""
    
    class Meta:
        model = OrdenCompra
        fields = ['requisicion', 'proveedor', 'fecha_estimada_entrega', 'notas']
        widgets = {
            'requisicion': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500'
            }),
            'proveedor': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500'
            }),
            'fecha_estimada_entrega': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500'
            }),
            'notas': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500',
                'rows': '3',
                'placeholder': 'Notas adicionales (opcional)'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar solo requisiciones aprobadas
        self.fields['requisicion'].queryset = Requisicion.objects.filter(estado='APROBADA').order_by('-fecha_solicitud')
        # Filtrar solo proveedores activos
        self.fields['proveedor'].queryset = Proveedor.objects.filter(activo=True).order_by('nombre')
        
        # Hacer que la fecha estimada sea al menos mañana
        from datetime import date, timedelta
        self.fields['fecha_estimada_entrega'].widget.attrs['min'] = (date.today() + timedelta(days=1)).isoformat()
