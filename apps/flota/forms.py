from django import forms

from apps.campo.models import Vehiculo
from .models import MantenimientoVehiculo


class MantenimientoVehiculoForm(forms.ModelForm):
    class Meta:
        model = MantenimientoVehiculo
        fields = [
            "vehiculo", "fecha_mantenimiento",
            "kilometraje_actual", "proximo_mantenimiento_km",
            "descripcion", "observaciones",
        ]
        widgets = {
            "vehiculo": forms.Select(attrs={"class": "form-input"}),
            "fecha_mantenimiento": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "kilometraje_actual": forms.NumberInput(attrs={"class": "form-input"}),
            "proximo_mantenimiento_km": forms.NumberInput(attrs={"class": "form-input"}),
            "descripcion": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
            "observaciones": forms.Textarea(attrs={"class": "form-input", "rows": 2}),
        }
