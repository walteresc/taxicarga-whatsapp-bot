from django import forms
from django.contrib.auth.models import User

from .models import Ayudante, Conductor, EquipoDia, Vehiculo


class VehiculoForm(forms.ModelForm):
    class Meta:
        model = Vehiculo
        fields = [
            "placa", "marca", "modelo", "anio",
            "capacidad_toneladas", "capacidad_m3",
            "fecha_vencimiento_soat", "fecha_vencimiento_rtv", "fecha_vencimiento_extintor",
            "activo", "observaciones",
        ]
        widgets = {
            "placa": forms.TextInput(attrs={"class": "form-input", "placeholder": "ABC-123"}),
            "marca": forms.TextInput(attrs={"class": "form-input", "placeholder": "Volvo"}),
            "modelo": forms.TextInput(attrs={"class": "form-input", "placeholder": "FH 460"}),
            "anio": forms.NumberInput(attrs={"class": "form-input", "min": 1990, "max": 2030}),
            "capacidad_toneladas": forms.NumberInput(attrs={"class": "form-input", "step": "0.1"}),
            "capacidad_m3": forms.NumberInput(attrs={"class": "form-input", "step": "0.1"}),
            "fecha_vencimiento_soat": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "fecha_vencimiento_rtv": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "fecha_vencimiento_extintor": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "observaciones": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
        }


class ConductorForm(forms.ModelForm):
    usuario = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-input"}),
    )

    class Meta:
        model = Conductor
        fields = [
            "nombre", "dni", "telefono",
            "numero_licencia", "categoria_licencia", "fecha_vencimiento_licencia",
            "usuario", "activo", "observaciones",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-input", "placeholder": "Juan Pérez"}),
            "dni": forms.TextInput(attrs={"class": "form-input", "placeholder": "12345678"}),
            "telefono": forms.TextInput(attrs={"class": "form-input", "placeholder": "51970000001"}),
            "numero_licencia": forms.TextInput(attrs={"class": "form-input", "placeholder": "L12345678"}),
            "categoria_licencia": forms.Select(attrs={"class": "form-input"}),
            "fecha_vencimiento_licencia": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "observaciones": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
        }


class AyudanteForm(forms.ModelForm):
    usuario = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-input"}),
    )

    class Meta:
        model = Ayudante
        fields = ["nombre", "dni", "telefono", "usuario", "activo", "observaciones"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-input", "placeholder": "Pedro Gómez"}),
            "dni": forms.TextInput(attrs={"class": "form-input", "placeholder": "87654321"}),
            "telefono": forms.TextInput(attrs={"class": "form-input", "placeholder": "51970000002"}),
            "observaciones": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
        }


class EquipoDiaForm(forms.ModelForm):
    class Meta:
        model = EquipoDia
        fields = ["fecha", "vehiculo", "conductor", "ayudantes", "activo", "observaciones"]
        widgets = {
            "fecha": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "ayudantes": forms.SelectMultiple(attrs={"class": "form-input multi-select", "size": 6}),
            "observaciones": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
        }
