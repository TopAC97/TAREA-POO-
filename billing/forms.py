from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Brand, Product
from django.forms import inlineformset_factory
from .models import Invoice, InvoiceDetail


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class':'form-control'}))
    first_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class':'form-control'}))
    last_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class':'form-control'}))
    class Meta:
        model = User
        fields = ['username','first_name','last_name','email','password1','password2']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields: self.fields[f].widget.attrs['class'] = 'form-control'

class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'description': forms.Textarea(attrs={'class':'form-control','rows':3}),
            'is_active': forms.CheckboxInput(attrs={'class':'form-check-input'}),
        }

class ProductForm(forms.ModelForm):
    """
    Formulario centralizado para crear y editar productos.
    Incluye widgets Bootstrap, help_texts, validaciones y resaltado de errores.
    """

    class Meta:
        model = Product
        fields = [
            'name', 'description', 'brand', 'group', 'suppliers',
            'unit_price', 'stock', 'image', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Laptop Dell XPS 15',
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción detallada del producto...',
            }),
            'brand': forms.Select(attrs={'class': 'form-select'}),
            'group': forms.Select(attrs={'class': 'form-select'}),
            'suppliers': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': 4,
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00',
            }),
            'stock': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '0',
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
        }
        help_texts = {
            'name':        'Nombre único del producto (máx. 200 caracteres).',
            'description': 'Descripción opcional del producto.',
            'suppliers':   'Ctrl+clic para seleccionar varios proveedores.',
            'unit_price':  'Precio de venta por unidad. Debe ser mayor que cero.',
            'stock':       'Cantidad disponible en inventario.',
            'image':       'JPG, PNG o WEBP recomendado.',
            'is_active':   'Desmarcar para desactivar sin eliminar.',
        }
        error_messages = {
            'name':       {'required': 'El nombre del producto es obligatorio.'},
            'brand':      {'required': 'Debe seleccionar una marca.'},
            'group':      {'required': 'Debe seleccionar un grupo.'},
            'unit_price': {
                'required': 'El precio unitario es obligatorio.',
                'invalid':  'Ingrese un valor numérico válido.',
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Resaltar campos con errores con clase Bootstrap is-invalid
        if self.is_bound:
            for field_name, field in self.fields.items():
                if self.errors.get(field_name):
                    cls = field.widget.attrs.get('class', '')
                    if 'is-invalid' not in cls:
                        field.widget.attrs['class'] = cls + ' is-invalid'

    def clean_unit_price(self):
        price = self.cleaned_data.get('unit_price')
        if price is not None and price <= 0:
            raise forms.ValidationError('El precio unitario debe ser mayor que cero.')
        return price


class InvoiceForm(forms.ModelForm):
    """Formulario para cabecera de factura."""
    class Meta:
        model = Invoice
        fields = ['customer']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
        }


# Formset: permite agregar MÚLTIPLES detalles dentro de UNA factura
# extra=3: muestra 3 filas vacías para agregar productos
# can_delete=True: permite eliminar filas
InvoiceDetailFormSet = inlineformset_factory(
    Invoice,           # Modelo padre
    InvoiceDetail,     # Modelo hijo
    fields=['product', 'quantity', 'unit_price'],
    extra=3,           # 3 filas vacías para agregar
    can_delete=True,   # Checkbox para eliminar filas
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    }
)
