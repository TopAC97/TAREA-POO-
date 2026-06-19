from django.contrib import messages
from django.shortcuts import redirect


class ExportMixin:
    """
    Mixin genérico de exportación a PDF / Excel para vistas CBV ListView.

    En la subclase define:
        export_title   = 'Nombre del listado'
        export_columns = [('Encabezado', 'field_o_callable'), ...]

    Agrega ?format=pdf o ?format=excel a cualquier URL del listado.
    Los filtros GET activos se preservan automáticamente en `export_qs`.
    """

    export_title = 'Listado'
    export_columns = []

    def get_export_columns(self):
        """Devuelve las columnas a exportar. Sobreescribir en subclases para columnas dinámicas."""
        return self.export_columns

    def get(self, request, *args, **kwargs):
        fmt = request.GET.get('format', '').lower()
        if fmt in ('pdf', 'excel'):
            from shared.exports import export_to_pdf, export_to_excel
            qs = self.get_queryset()
            columns = self.get_export_columns()
            fn = export_to_pdf if fmt == 'pdf' else export_to_excel
            return fn(qs, columns, self.export_title)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop('format', None)
        params.pop('page', None)
        params.pop('cols', None)
        ctx['export_qs'] = params.urlencode()
        return ctx


class StaffRequiredMixin:
    """
    Mixin que verifica si el usuario es miembro del staff.
    Si no es staff, redirige con mensaje de error.
    
    Uso:
        class BrandDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
            ...
    
    ¿POR QUÉ?
    Porque solo el personal autorizado (staff) debe poder
    eliminar registros. Un usuario normal puede ver y crear,
    pero no borrar información importante del sistema.
    
    ¿CÓMO FUNCIONA?
    1. El usuario intenta acceder a una vista protegida
    2. dispatch() se ejecuta ANTES que la vista
    3. Si user.is_staff es False → redirige con mensaje de error
    4. Si user.is_staff es True → ejecuta la vista normalmente
    """

    # URL a donde redirigir si no es staff
    # Se puede sobreescribir en cada vista
    staff_redirect_url = '/'
    staff_error_message = 'You do not have permission to perform this action. Staff access required.'

    def dispatch(self, request, *args, **kwargs):
        """
        dispatch() es el primer método que se ejecuta en una CBV.
        Interceptamos aquí para verificar permisos ANTES de
        procesar la petición (GET o POST).
        """
        # Verificar si el usuario es staff
        if not request.user.is_staff:
            # Mostrar mensaje de error al usuario
            messages.error(request, self.staff_error_message)
            # Redirigir a la URL configurada
            return redirect(self.staff_redirect_url)

        # Si es staff, continuar con el flujo normal de la vista
        return super().dispatch(request, *args, **kwargs)
