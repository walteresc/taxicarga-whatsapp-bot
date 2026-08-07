from django import forms

from apps.clientes.models import Cliente
from .models import CONCEPTO_PAGO_CHOICES, METODO_PAGO_CHOICES, PagoReserva, Servicio


ACCESO_CHOICES = [
    ("ascensor", "Ascensor"),
    ("escaleras", "Escaleras"),
    ("sogas", "Sogas"),
]

REQUISITOS_CHOICES = [
    ("ninguno", "Ninguno"),
    ("epp", "EPP"),
    ("sctr", "SCTR"),
    ("otros", "Otros"),
]


class ReservaForm(forms.ModelForm):
    # Cliente fields (inline creation)
    cliente_nombre = forms.CharField(
        max_length=160, required=True,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Nombre del cliente"}),
    )
    cliente_telefono = forms.CharField(
        max_length=30, required=True,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Teléfono"}),
    )
    cliente_documento = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "DNI / CE"}),
    )
    cliente_correo = forms.EmailField(
        max_length=200, required=False,
        widget=forms.EmailInput(attrs={"class": "form-input", "placeholder": "correo@ejemplo.com"}),
    )
    cliente_ruc = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "RUC"}),
    )
    cliente_razon_social = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Razón social"}),
    )

    # hidden field to store selected existing client id
    cliente_id = forms.IntegerField(required=False, widget=forms.HiddenInput())

    # Override JSON model fields as MultipleChoiceField for proper form handling
    acceso_origen_opciones = forms.MultipleChoiceField(
        choices=ACCESO_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        required=True,
    )
    acceso_destino_opciones = forms.MultipleChoiceField(
        choices=ACCESO_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        required=True,
    )
    requisitos_especiales = forms.MultipleChoiceField(
        choices=REQUISITOS_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )

    class Meta:
        model = Servicio
        fields = [
            "direccion_origen", "piso_origen",
            "direccion_destino", "piso_destino",
            "detalle_carga",
            "tipo_embalaje",
            "tipo_comprobante",
            "fecha_servicio", "horario_servicio",
            "precio",
            "observaciones",
            "lead_origen",
        ]
        widgets = {
            "direccion_origen": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "Av. Ejemplo 123"}
            ),
            "piso_origen": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "Piso 3"}
            ),
            "direccion_destino": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "Av. Destino 456"}
            ),
            "piso_destino": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "Piso 5"}
            ),
            "detalle_carga": forms.Textarea(
                attrs={"class": "form-input", "rows": 3, "placeholder": "Describa la carga a transportar"}
            ),
            "tipo_embalaje": forms.RadioSelect(),
            "tipo_comprobante": forms.RadioSelect(),
            "fecha_servicio": forms.DateInput(
                attrs={"class": "form-input", "type": "date"}
            ),
            "horario_servicio": forms.TimeInput(
                attrs={"class": "form-input", "type": "time"}
            ),
            "precio": forms.NumberInput(
                attrs={"class": "form-input", "step": "0.01", "placeholder": "0.00"}
            ),
            "observaciones": forms.Textarea(
                attrs={"class": "form-input", "rows": 2, "placeholder": "Notas internas..."}
            ),
            "lead_origen": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # pre-fill client fields if editing
        if self.instance and self.instance.pk and self.instance.cliente:
            c = self.instance.cliente
            self.fields["cliente_id"].initial = c.pk
            self.fields["cliente_nombre"].initial = c.nombre
            self.fields["cliente_telefono"].initial = c.telefono
            self.fields["cliente_documento"].initial = c.documento
            self.fields["cliente_correo"].initial = c.correo
            self.fields["cliente_ruc"].initial = c.ruc
            self.fields["cliente_razon_social"].initial = c.razon_social
            # Pre-fill JSON-based MultipleChoiceFields
            if self.instance.acceso_origen_opciones:
                self.fields["acceso_origen_opciones"].initial = self.instance.acceso_origen_opciones
            if self.instance.acceso_destino_opciones:
                self.fields["acceso_destino_opciones"].initial = self.instance.acceso_destino_opciones
            if self.instance.requisitos_especiales:
                self.fields["requisitos_especiales"].initial = self.instance.requisitos_especiales

    def clean_cliente_telefono(self):
        telefono = self.cleaned_data.get("cliente_telefono", "").strip()
        if not telefono:
            raise forms.ValidationError("El teléfono es obligatorio.")
        return telefono

    def clean_cliente_nombre(self):
        nombre = self.cleaned_data.get("cliente_nombre", "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre es obligatorio.")
        return nombre

    def clean(self):
        cleaned = super().clean()

        # Validate access options at least one
        for field in ("acceso_origen_opciones", "acceso_destino_opciones"):
            val = cleaned.get(field)
            if not val or len(val) == 0:
                self.add_error(field, "Seleccione al menos una opción de acceso.")

        # Validate if client_id is provided, it must exist
        cliente_id = cleaned.get("cliente_id")
        if cliente_id:
            try:
                Cliente.objects.get(pk=cliente_id)
            except Cliente.DoesNotExist:
                self.add_error("cliente_id", "Cliente no encontrado.")

        return cleaned

    def _save_m2m(self):
        """Save ManyToMany / JSON fields after instance is saved."""
        pass

    def save(self, commit=True):
        servicio = super().save(commit=False)
        cliente_id = self.cleaned_data.get("cliente_id")
        nombre = self.cleaned_data.get("cliente_nombre", "").strip()
        telefono = self.cleaned_data.get("cliente_telefono", "").strip()

        # Save JSON fields from MultipleChoiceField data
        servicio.acceso_origen_opciones = list(self.cleaned_data.get("acceso_origen_opciones", []))
        servicio.acceso_destino_opciones = list(self.cleaned_data.get("acceso_destino_opciones", []))
        servicio.requisitos_especiales = list(self.cleaned_data.get("requisitos_especiales", []))

        if cliente_id:
            cliente = Cliente.objects.get(pk=cliente_id)
            cliente.nombre = nombre
            cliente.telefono = telefono
            if self.cleaned_data.get("cliente_documento"):
                cliente.documento = self.cleaned_data["cliente_documento"]
            if self.cleaned_data.get("cliente_correo"):
                cliente.correo = self.cleaned_data["cliente_correo"]
            if self.cleaned_data.get("cliente_ruc"):
                cliente.ruc = self.cleaned_data["cliente_ruc"]
            if self.cleaned_data.get("cliente_razon_social"):
                cliente.razon_social = self.cleaned_data["cliente_razon_social"]
            if commit:
                cliente.save()
        else:
            cliente, _ = Cliente.objects.get_or_create(
                telefono=telefono,
                defaults={
                    "nombre": nombre,
                    "documento": self.cleaned_data.get("cliente_documento", ""),
                    "correo": self.cleaned_data.get("cliente_correo", ""),
                    "ruc": self.cleaned_data.get("cliente_ruc", ""),
                    "razon_social": self.cleaned_data.get("cliente_razon_social", ""),
                },
            )

        servicio.cliente = cliente

        if commit:
            servicio.save()
        return servicio


class PagoReservaForm(forms.ModelForm):
    class Meta:
        model = PagoReserva
        fields = ["concepto", "metodo_pago", "monto", "fecha_pago", "observaciones"]
        widgets = {
            "concepto": forms.Select(attrs={"class": "form-input"}),
            "metodo_pago": forms.Select(attrs={"class": "form-input"}),
            "monto": forms.NumberInput(attrs={"class": "form-input", "step": "0.01", "placeholder": "0.00"}),
            "fecha_pago": forms.DateTimeInput(attrs={"class": "form-input", "type": "datetime-local"}),
            "observaciones": forms.Textarea(attrs={"class": "form-input", "rows": 2, "placeholder": "Motivo / observación"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["concepto"].empty_label = None
        self.fields["metodo_pago"].empty_label = None

    def clean(self):
        cleaned = super().clean()
        concepto = cleaned.get("concepto")
        observaciones = cleaned.get("observaciones", "").strip()
        if concepto in ("descuento", "ajuste") and not observaciones:
            self.add_error("observaciones", "Observaciones obligatorias para descuento o ajuste.")
        return cleaned
