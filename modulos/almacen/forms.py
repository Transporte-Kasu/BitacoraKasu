from django import forms
from django.core.exceptions import ValidationError
from .models import (
    ProductoAlmacen, EntradaAlmacen, ItemEntradaAlmacen,
    SolicitudSalida, ItemSolicitudSalida, SalidaAlmacen,
    ItemSalidaAlmacen, AlertaStock
)


class ProductoAlmacenForm(forms.ModelForm):
    """Formulario para ProductoAlmacen"""
    
    class Meta:
        model = ProductoAlmacen
        fields = [
            'categoria', 'subcategoria', 'sku', 'codigo_barras', 'descripcion',
            'localidad', 'cantidad', 'unidad_medida', 'stock_minimo', 'stock_maximo',
            'costo_unitario', 'tiene_caducidad', 'fecha_caducidad', 'imagen',
            'producto_compra', 'proveedor_principal', 'tiempo_reorden_dias',
            'notas', 'activo'
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
            'notas': forms.Textarea(attrs={'rows': 3}),
            'fecha_caducidad': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def clean_sku(self):
        """Convertir SKU a mayúsculas"""
        sku = self.cleaned_data.get('sku')
        if sku:
            return sku.upper()
        return sku
    
    def clean_codigo_barras(self):
        """Convertir código de barras a mayúsculas si existe"""
        codigo = self.cleaned_data.get('codigo_barras')
        if codigo:
            return codigo.upper()
        return codigo
    
    def clean(self):
        cleaned_data = super().clean()
        tiene_caducidad = cleaned_data.get('tiene_caducidad')
        fecha_caducidad = cleaned_data.get('fecha_caducidad')
        stock_minimo = cleaned_data.get('stock_minimo')
        stock_maximo = cleaned_data.get('stock_maximo')
        
        # Si tiene caducidad, la fecha es obligatoria
        if tiene_caducidad and not fecha_caducidad:
            raise ValidationError({
                'fecha_caducidad': 'La fecha de caducidad es obligatoria si el producto tiene caducidad.'
            })
        
        # Validar que stock máximo sea mayor que stock mínimo
        if stock_maximo and stock_minimo and stock_maximo > 0:
            if stock_maximo < stock_minimo:
                raise ValidationError({
                    'stock_maximo': 'El stock máximo debe ser mayor o igual al stock mínimo.'
                })
        
        return cleaned_data


class EntradaAlmacenForm(forms.ModelForm):
    """Formulario para EntradaAlmacen"""
    
    class Meta:
        model = EntradaAlmacen
        fields = [
            'tipo', 'fecha_entrada', 'orden_compra', 'orden_trabajo',
            'recepcion_almacen_compras', 'factura_numero', 'factura_archivo',
            'costo_envio', 'costo_adicional', 'observaciones'
        ]
        widgets = {
            'fecha_entrada': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'observaciones': forms.Textarea(attrs={'rows': 3}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        orden_compra = cleaned_data.get('orden_compra')
        orden_trabajo = cleaned_data.get('orden_trabajo')
        
        # Validar que tipo FACTURA tenga orden_compra
        if tipo == 'FACTURA' and not orden_compra:
            raise ValidationError({
                'orden_compra': 'Una entrada tipo FACTURA requiere una orden de compra.'
            })
        
        # Validar que tipo TALLER tenga orden_trabajo
        if tipo in ['TALLER_REPARADO', 'TALLER_RECICLADO'] and not orden_trabajo:
            raise ValidationError({
                'orden_trabajo': f'Una entrada tipo {tipo} requiere una orden de trabajo.'
            })
        
        return cleaned_data


class ItemEntradaAlmacenForm(forms.ModelForm):
    """Formulario para ItemEntradaAlmacen"""
    
    class Meta:
        model = ItemEntradaAlmacen
        fields = [
            'producto_almacen', 'cantidad', 'costo_unitario',
            'lote', 'fecha_caducidad', 'ubicacion_asignada', 'observaciones'
        ]
        widgets = {
            'fecha_caducidad': forms.DateInput(attrs={'type': 'date'}),
            'observaciones': forms.Textarea(attrs={'rows': 2}),
        }
    
    def clean_cantidad(self):
        cantidad = self.cleaned_data.get('cantidad')
        if cantidad and cantidad <= 0:
            raise ValidationError('La cantidad debe ser mayor a 0.')
        return cantidad


class SolicitudSalidaForm(forms.ModelForm):
    """Formulario para SolicitudSalida"""
    
    class Meta:
        model = SolicitudSalida
        fields = [
            'tipo', 'orden_trabajo', 'justificacion'
        ]
        widgets = {
            'justificacion': forms.Textarea(attrs={'rows': 4}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        orden_trabajo = cleaned_data.get('orden_trabajo')
        
        # Validar que tipo ORDEN_TRABAJO tenga orden_trabajo
        if tipo == 'ORDEN_TRABAJO' and not orden_trabajo:
            raise ValidationError({
                'orden_trabajo': 'Una solicitud para orden de trabajo requiere seleccionar la orden.'
            })
        
        # Validar que SOLICITUD_GENERAL no tenga orden_trabajo
        if tipo == 'SOLICITUD_GENERAL' and orden_trabajo:
            raise ValidationError({
                'orden_trabajo': 'Una solicitud general no debe tener orden de trabajo asociada.'
            })
        
        return cleaned_data


class ItemSolicitudSalidaForm(forms.ModelForm):
    """Formulario para ItemSolicitudSalida"""
    
    class Meta:
        model = ItemSolicitudSalida
        fields = [
            'producto_almacen', 'cantidad_solicitada', 'observaciones'
        ]
        widgets = {
            'observaciones': forms.Textarea(attrs={'rows': 2}),
        }
    
    def clean_cantidad_solicitada(self):
        cantidad = self.cleaned_data.get('cantidad_solicitada')
        if cantidad and cantidad <= 0:
            raise ValidationError('La cantidad solicitada debe ser mayor a 0.')
        return cantidad


class AutorizarSolicitudForm(forms.Form):
    """Formulario para autorizar o rechazar una solicitud"""
    accion = forms.ChoiceField(
        choices=[('autorizar', 'Autorizar'), ('rechazar', 'Rechazar')],
        widget=forms.RadioSelect
    )
    comentarios = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Comentarios sobre la autorización o rechazo'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        accion = cleaned_data.get('accion')
        comentarios = cleaned_data.get('comentarios')
        
        # Si se rechaza, los comentarios son obligatorios
        if accion == 'rechazar' and not comentarios:
            raise ValidationError({
                'comentarios': 'Debe proporcionar un motivo para rechazar la solicitud.'
            })
        
        return cleaned_data


class SalidaAlmacenForm(forms.ModelForm):
    """Formulario para SalidaAlmacen"""
    
    class Meta:
        model = SalidaAlmacen
        fields = [
            'fecha_salida', 'entregado_a', 'observaciones'
        ]
        widgets = {
            'fecha_salida': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'observaciones': forms.Textarea(attrs={'rows': 3}),
        }


class ItemSalidaAlmacenForm(forms.ModelForm):
    """Formulario para ItemSalidaAlmacen"""
    
    class Meta:
        model = ItemSalidaAlmacen
        fields = [
            'producto_almacen', 'cantidad_entregada', 'lote', 'ubicacion_origen'
        ]
    
    def __init__(self, *args, **kwargs):
        self.item_solicitud = kwargs.pop('item_solicitud', None)
        super().__init__(*args, **kwargs)
    
    def clean_cantidad_entregada(self):
        cantidad = self.cleaned_data.get('cantidad_entregada')
        producto = self.cleaned_data.get('producto_almacen')
        
        if cantidad and cantidad <= 0:
            raise ValidationError('La cantidad debe ser mayor a 0.')
        
        # Validar que haya stock disponible
        if producto and cantidad:
            if cantidad > producto.cantidad:
                raise ValidationError(
                    f'No hay suficiente stock. Disponible: {producto.cantidad} {producto.unidad_medida}'
                )
        
        # Validar que no exceda la cantidad solicitada
        if self.item_solicitud and cantidad:
            cantidad_pendiente = self.item_solicitud.cantidad_pendiente
            if cantidad > cantidad_pendiente:
                raise ValidationError(
                    f'La cantidad a entregar no puede exceder la cantidad pendiente: {cantidad_pendiente}'
                )
        
        return cantidad


class FiltroProductosForm(forms.Form):
    """Formulario para filtrar productos"""
    categoria = forms.CharField(required=False)
    subcategoria = forms.CharField(required=False)
    sku = forms.CharField(required=False, label='SKU')
    stock_bajo = forms.BooleanField(required=False, label='Solo con stock bajo')
    proximo_caducar = forms.BooleanField(required=False, label='Solo próximos a caducar')
    activo = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos'), ('True', 'Activos'), ('False', 'Inactivos')]
    )


class FiltroEntradasForm(forms.Form):
    """Formulario para filtrar entradas"""
    tipo = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos')] + list(EntradaAlmacen.TIPO_CHOICES)
    )
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )


class FiltroSolicitudesForm(forms.Form):
    """Formulario para filtrar solicitudes"""
    tipo = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos')] + list(SolicitudSalida.TIPO_CHOICES)
    )
    estado = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos')] + list(SolicitudSalida.ESTADO_CHOICES)
    )
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )


class ResolverAlertaForm(forms.Form):
    """Formulario para resolver una alerta"""
    confirmacion = forms.BooleanField(
        required=True,
        label='Confirmo que he revisado y resuelto esta alerta'
    )
