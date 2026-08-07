from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.campo.forms import VehiculoForm
from apps.campo.models import Vehiculo
from apps.dashboard.permissions import role_required
from .forms import MantenimientoVehiculoForm
from .models import MantenimientoVehiculo


# ---------------------------------------------------------------------------
# Vehículos (for Flota section)
# ---------------------------------------------------------------------------

VEHICULO_FIELDS = [
    {"name": "placa", "label": "Placa"},
    {"name": "marca", "label": "Marca"},
    {"name": "modelo", "label": "Modelo"},
    {"name": "anio", "label": "Año"},
    {"name": "capacidad_toneladas", "label": "Cap. (t)"},
    {"name": "capacidad_m3", "label": "Cap. (m³)"},
    {"name": "activo", "label": "Activo", "type": "boolean"},
]


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def vehiculo_list(request):
    vehiculos = Vehiculo.objects.all()
    return render(request, "flota/vehiculo_list.html", {
        "title": "Vehículos",
        "items": vehiculos,
        "active_section": "flota",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def vehiculo_detail(request, pk):
    vehiculo = get_object_or_404(Vehiculo, pk=pk)
    mantenimientos = vehiculo.mantenimientos.all()
    return render(request, "flota/vehiculo_detail.html", {
        "title": f"Vehículo {vehiculo.placa}",
        "vehiculo": vehiculo,
        "mantenimientos": mantenimientos,
        "active_section": "flota",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def vehiculo_create(request):
    if request.method == "POST":
        form = VehiculoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Vehículo creado correctamente.")
            return redirect("dashboard-flota-vehiculos")
    else:
        form = VehiculoForm()
    return render(request, "flota/vehiculo_form.html", {
        "title": "Nuevo Vehículo",
        "form": form,
        "cancel_url": "dashboard-flota-vehiculos",
        "submit_label": "Crear Vehículo",
        "active_section": "flota",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def vehiculo_edit(request, pk):
    vehiculo = get_object_or_404(Vehiculo, pk=pk)
    if request.method == "POST":
        form = VehiculoForm(request.POST, instance=vehiculo)
        if form.is_valid():
            form.save()
            messages.success(request, "Vehículo actualizado correctamente.")
            return redirect("dashboard-flota-vehiculos")
    else:
        form = VehiculoForm(instance=vehiculo)
    return render(request, "flota/vehiculo_form.html", {
        "title": "Editar Vehículo",
        "form": form,
        "cancel_url": "dashboard-flota-vehiculos",
        "submit_label": "Guardar Cambios",
        "active_section": "flota",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def vehiculo_toggle(request, pk):
    vehiculo = get_object_or_404(Vehiculo, pk=pk)
    vehiculo.activo = not vehiculo.activo
    vehiculo.save(update_fields=["activo"])
    msg = "activado" if vehiculo.activo else "desactivado"
    messages.success(request, f"Vehículo {vehiculo.placa} {msg}.")
    return redirect("dashboard-flota-vehiculos")


# ---------------------------------------------------------------------------
# Mantenimientos
# ---------------------------------------------------------------------------


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def mantenimiento_list(request):
    mantenimientos = MantenimientoVehiculo.objects.select_related("vehiculo").all()
    return render(request, "flota/mantenimiento_list.html", {
        "title": "Mantenimientos",
        "items": mantenimientos,
        "active_section": "flota",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def mantenimiento_create(request):
    vehiculo_id = request.GET.get("vehiculo")
    initial = {}
    if vehiculo_id:
        initial["vehiculo"] = vehiculo_id
    if request.method == "POST":
        form = MantenimientoVehiculoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Mantenimiento registrado correctamente.")
            return redirect("dashboard-flota-mantenimientos")
    else:
        form = MantenimientoVehiculoForm(initial=initial or None)
    return render(request, "flota/mantenimiento_form.html", {
        "title": "Registrar Mantenimiento",
        "form": form,
        "cancel_url": "dashboard-flota-mantenimientos",
        "submit_label": "Guardar Mantenimiento",
        "active_section": "flota",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def mantenimiento_edit(request, pk):
    mantenimiento = get_object_or_404(MantenimientoVehiculo, pk=pk)
    if request.method == "POST":
        form = MantenimientoVehiculoForm(request.POST, instance=mantenimiento)
        if form.is_valid():
            form.save()
            messages.success(request, "Mantenimiento actualizado correctamente.")
            return redirect("dashboard-flota-mantenimientos")
    else:
        form = MantenimientoVehiculoForm(instance=mantenimiento)
    return render(request, "flota/mantenimiento_form.html", {
        "title": "Editar Mantenimiento",
        "form": form,
        "cancel_url": "dashboard-flota-mantenimientos",
        "submit_label": "Guardar Cambios",
        "active_section": "flota",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def mantenimiento_delete(request, pk):
    mantenimiento = get_object_or_404(MantenimientoVehiculo, pk=pk)
    vehiculo_placa = mantenimiento.vehiculo.placa
    if request.method == "POST":
        mantenimiento.delete()
        messages.success(request, "Mantenimiento eliminado correctamente.")
        return redirect("dashboard-flota-mantenimientos")
    return render(request, "flota/mantenimiento_confirm_delete.html", {
        "title": "Eliminar Mantenimiento",
        "mantenimiento": mantenimiento,
        "active_section": "flota",
    })
