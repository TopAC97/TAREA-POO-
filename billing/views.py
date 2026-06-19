import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth import login
from .models import *
from .forms import SignUpForm, BrandForm, InvoiceForm, InvoiceDetailFormSet, ProductForm
from shared.mixins import StaffRequiredMixin, ExportMixin
from shared.decorators import audit_action
from decimal import Decimal

# ── Definición de columnas disponibles para el listado de Productos ──────────
# Cada columna tiene: key (identificador JS/URL), label, accessor para export,
# default (visible por defecto o no).
_PRODUCT_COLS_DEF = [
    {'key': 'id',          'label': '#',            'accessor': 'id',                                                          'default': False},
    {'key': 'image',       'label': 'Imagen',       'accessor': lambda obj: 'Si' if obj.image else 'No',                      'default': True},
    {'key': 'name',        'label': 'Nombre',       'accessor': 'name',                                                       'default': True},
    {'key': 'brand',       'label': 'Marca',        'accessor': 'brand.name',                                                 'default': True},
    {'key': 'group',       'label': 'Grupo',        'accessor': 'group.name',                                                 'default': True},
    {'key': 'price',       'label': 'Precio',       'accessor': lambda obj: f'${obj.unit_price}',                             'default': True},
    {'key': 'stock',       'label': 'Stock',        'accessor': lambda obj: str(obj.stock),                                   'default': True},
    {'key': 'balance',     'label': 'Balance',      'accessor': lambda obj: f'${obj.balance}',                                'default': True},
    {'key': 'is_active',   'label': 'Activo',       'accessor': lambda obj: 'Si' if obj.is_active else 'No',                  'default': True},
    {'key': 'suppliers',   'label': 'Proveedores',  'accessor': lambda obj: ', '.join(s.name for s in obj.suppliers.all()),   'default': True},
    {'key': 'description', 'label': 'Descripcion',  'accessor': 'description',                                                'default': False},
    {'key': 'created_at',  'label': 'Creado',       'accessor': lambda obj: obj.created_at.strftime('%d/%m/%Y'),              'default': False},
]
_PRODUCT_COLS_MAP     = {c['key']: c for c in _PRODUCT_COLS_DEF}
_PRODUCT_DEFAULT_COLS = [c['key'] for c in _PRODUCT_COLS_DEF if c['default']]


# === HOME (Página principal) ===
@login_required
def home(request):
    """Vista principal del sistema. Muestra resumen general."""
    context = {
        'total_brands': Brand.objects.count(),
        'total_products': Product.objects.count(),
        'total_customers': Customer.objects.count(),
        'total_invoices': Invoice.objects.count(),
        'recent_invoices': Invoice.objects.all()[:5],  # Últimas 5
        'low_stock': Product.objects.filter(stock__lte=5, is_active=True),
    }
    return render(request, 'billing/home.html', context)

# === REGISTRO ===
class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('billing:brand_list')
    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response

# === BRAND (FBV) ===
_BRAND_COLUMNS = [
    ('Name', 'name'),
    ('Description', 'description'),
    ('Active', lambda obj: 'Yes' if obj.is_active else 'No'),
    ('Created', lambda obj: obj.created_at.strftime('%d/%m/%Y')),
]

@login_required
@audit_action('LIST_BRANDS')
def brand_list(request):
    brands = Brand.objects.all()
    fmt = request.GET.get('format', '').lower()
    if fmt in ('pdf', 'excel'):
        from shared.exports import export_to_pdf, export_to_excel
        fn = export_to_pdf if fmt == 'pdf' else export_to_excel
        return fn(brands, _BRAND_COLUMNS, 'Brands')
    return render(request, 'billing/brand_list.html', {'brands': brands})

@login_required
@audit_action('CREATE_BRAND')
def brand_create(request):
    if request.method == 'POST':
        form = BrandForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brand created!')
            return redirect('billing:brand_list')
    else: form = BrandForm()
    return render(request, 'billing/brand_form.html', {'form':form, 'title':'Create Brand'})

@login_required
@audit_action('UPDATE_BRAND')
def brand_update(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brand updated!')
            return redirect('billing:brand_list')
    else: form = BrandForm(instance=brand)
    return render(request, 'billing/brand_form.html', {'form':form, 'title':'Edit Brand'})

@login_required
@audit_action('DELETE_BRAND')
def brand_delete(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        brand.delete()
        messages.success(request, 'Brand deleted!')
        return redirect('billing:brand_list')
    return render(request, 'billing/brand_confirm_delete.html', {'object': brand})


# =============================================
# CRUD DE INVOICE - VISTAS BASADAS EN FUNCIONES
# (Requiere FBV porque usa formsets complejos)
# =============================================

_INVOICE_COLUMNS = [
    ('#', 'id'),
    ('Customer', lambda obj: str(obj.customer)),
    ('Date', lambda obj: obj.invoice_date.strftime('%d/%m/%Y')),
    ('Subtotal', lambda obj: f'${obj.subtotal}'),
    ('Tax', lambda obj: f'${obj.tax}'),
    ('Total', lambda obj: f'${obj.total}'),
]

@login_required
def invoice_list(request):
    """Lista todas las facturas con sus totales."""
    invoices = Invoice.objects.select_related('customer').all()
    fmt = request.GET.get('format', '').lower()
    if fmt in ('pdf', 'excel'):
        from shared.exports import export_to_pdf, export_to_excel
        fn = export_to_pdf if fmt == 'pdf' else export_to_excel
        return fn(invoices, _INVOICE_COLUMNS, 'Invoices')
    return render(request, 'billing/invoice_list.html', {'items': invoices})


@login_required
def invoice_create(request):
    """Crea factura con sus líneas de detalle."""
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceDetailFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            # Guardar factura (sin commit para asignar totales)
            invoice = form.save(commit=False)
            invoice.save()

            # Asignar la factura al formset y guardar detalles
            formset.instance = invoice
            details = formset.save()

            # Calcular totales
            subtotal = sum(d.subtotal for d in invoice.details.all())
            invoice.subtotal = subtotal
            invoice.tax = subtotal * Decimal('0.15')  # IVA 15%
            invoice.total = invoice.subtotal + invoice.tax
            invoice.save()

            messages.success(request, f'Invoice #{invoice.id} created! Total: ${invoice.total}')
            return redirect('billing:invoice_list')
    else:
        form = InvoiceForm()
        formset = InvoiceDetailFormSet()

    return render(request, 'billing/invoice_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create Invoice',
    })


@login_required
def invoice_detail(request, pk):
    """Muestra el detalle completo de una factura."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer')
                       .prefetch_related('details__product'),
        pk=pk
    )
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})


@login_required
def invoice_delete(request, pk):
    """Elimina una factura y todos sus detalles (CASCADE)."""
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        invoice_id = invoice.id
        invoice.delete()
        messages.success(request, f'Invoice #{invoice_id} deleted!')
        return redirect('billing:invoice_list')
    return render(request, 'billing/invoice_confirm_delete.html', {'object': invoice})


# === PRODUCTGROUP (CBV) ===
class ProductGroupListView(LoginRequiredMixin, ExportMixin, ListView):
    model = ProductGroup
    template_name = 'billing/productgroup_list.html'
    context_object_name = 'items'
    export_title = 'Product Groups'
    export_columns = [
        ('Name', 'name'),
        ('Active', lambda obj: 'Yes' if obj.is_active else 'No'),
    ]

class ProductGroupCreateView(LoginRequiredMixin, CreateView):
    model = ProductGroup; fields = ['name','is_active']; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')
class ProductGroupUpdateView(LoginRequiredMixin, UpdateView):
    model = ProductGroup; fields = ['name','is_active']; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')
class ProductGroupDeleteView(LoginRequiredMixin, DeleteView):
    model = ProductGroup; template_name = 'billing/productgroup_confirm_delete.html'; success_url = reverse_lazy('billing:productgroup_list'); staff_redirect_url = '/groups/'

# === SUPPLIER (CBV) ===
class SupplierListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Supplier
    template_name = 'billing/supplier_list.html'
    context_object_name = 'items'
    export_title = 'Suppliers'
    export_columns = [
        ('Name', 'name'),
        ('Contact', 'contact_name'),
        ('Email', 'email'),
        ('Phone', 'phone'),
        ('Active', lambda obj: 'Yes' if obj.is_active else 'No'),
    ]

class SupplierCreateView(LoginRequiredMixin, CreateView):
    model = Supplier; fields = ['name','contact_name','email','phone','address','is_active']; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')
class SupplierUpdateView(LoginRequiredMixin, UpdateView):
    model = Supplier; fields = ['name','contact_name','email','phone','address','is_active']; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')
class SupplierDeleteView(LoginRequiredMixin, DeleteView):
    model = Supplier; template_name = 'billing/supplier_confirm_delete.html'; success_url = reverse_lazy('billing:supplier_list'); staff_redirect_url = '/suppliers/'

# === PRODUCT (CBV) ===
class ProductListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Product
    template_name = 'billing/product_list.html'
    context_object_name = 'items'
    paginate_by = 10
    export_title = 'Products'

    def get_export_columns(self):
        """Filtra las columnas de exportación según el parámetro ?cols= de la URL."""
        cols_param = self.request.GET.get('cols', '')
        keys = [k.strip() for k in cols_param.split(',') if k.strip()] if cols_param else _PRODUCT_DEFAULT_COLS
        result = []
        for k in keys:
            col = _PRODUCT_COLS_MAP.get(k)
            if col:
                result.append((col['label'], col['accessor']))
        return result or [(c['label'], c['accessor']) for c in _PRODUCT_COLS_DEF if c['default']]

    def get_queryset(self):
        qs = Product.objects.select_related('brand', 'group').prefetch_related('suppliers')

        name = self.request.GET.get('name', '').strip()
        brand = self.request.GET.get('brand', '')
        group = self.request.GET.get('group', '')
        price_min = self.request.GET.get('price_min', '').strip()
        price_max = self.request.GET.get('price_max', '').strip()
        stock_min = self.request.GET.get('stock_min', '').strip()
        stock_max = self.request.GET.get('stock_max', '').strip()
        supplier = self.request.GET.get('supplier', '')
        is_active = self.request.GET.get('is_active', '')

        if name:
            qs = qs.filter(name__icontains=name)
        if brand:
            qs = qs.filter(brand_id=brand)
        if group:
            qs = qs.filter(group_id=group)
        if price_min:
            qs = qs.filter(unit_price__gte=price_min)
        if price_max:
            qs = qs.filter(unit_price__lte=price_max)
        if stock_min:
            qs = qs.filter(stock__gte=stock_min)
        if stock_max:
            qs = qs.filter(stock__lte=stock_max)
        if supplier:
            qs = qs.filter(suppliers__id=supplier).distinct()
        if is_active != '':
            qs = qs.filter(is_active=(is_active == '1'))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['brands'] = Brand.objects.order_by('name')
        ctx['groups'] = ProductGroup.objects.order_by('name')
        ctx['suppliers'] = Supplier.objects.order_by('name')
        ctx['q'] = self.request.GET
        ctx['all_columns_json'] = json.dumps([
            {'key': c['key'], 'label': c['label'], 'default': c['default']}
            for c in _PRODUCT_COLS_DEF
        ])
        ctx['default_cols_json'] = json.dumps(_PRODUCT_DEFAULT_COLS)
        return ctx

class ProductDetailView(LoginRequiredMixin, DetailView):
    model = Product
    template_name = 'billing/product_detail.html'
    context_object_name = 'product'

    def get_queryset(self):
        return Product.objects.select_related('brand', 'group').prefetch_related('suppliers')

class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')

class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')
class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Product; template_name = 'billing/product_confirm_delete.html'; success_url = reverse_lazy('billing:product_list'); staff_redirect_url = '/products/'

# === CUSTOMER (CBV) ===
class CustomerListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Customer
    template_name = 'billing/customer_list.html'
    context_object_name = 'items'
    export_title = 'Customers'
    export_columns = [
        ('DNI', 'dni'),
        ('Last Name', 'last_name'),
        ('First Name', 'first_name'),
        ('Email', 'email'),
        ('Phone', 'phone'),
        ('Active', lambda obj: 'Yes' if obj.is_active else 'No'),
    ]

class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer; fields = ['dni','first_name','last_name','email','phone','address','is_active']; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')
class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer; fields = ['dni','first_name','last_name','email','phone','address','is_active']; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')
class CustomerDeleteView(LoginRequiredMixin, DeleteView):
    model = Customer; template_name = 'billing/customer_confirm_delete.html'; success_url = reverse_lazy('billing:customer_list'); staff_redirect_url = '/customers/'

# === INVOICE (CBV) ===
class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice; template_name = 'billing/invoice_list.html'; context_object_name = 'items'
class InvoiceCreateView(LoginRequiredMixin, CreateView):
    model = Invoice; fields = ['customer']; template_name = 'billing/invoice_form.html'; success_url = reverse_lazy('billing:invoice_list')
class InvoiceDeleteView(LoginRequiredMixin, DeleteView):
    model = Invoice; template_name = 'billing/invoice_confirm_delete.html'; success_url = reverse_lazy('billing:invoice_list'); staff_redirect_url = '/invoices/'
