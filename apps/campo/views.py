import json
from decimal import Decimal
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import make_aware
from django.views.decorators.http import require_http_methods

from apps.dashboard.permissions import can_manage_campo, can_manage_pizarra, role_required
from apps.servicios.models import (
    ESTADOS_SERVICIO,
    SERVICIO_ASIGNADO,
    SERVICIO_CANCELADO,
    SERVICIO_EN_RUTA,
    SERVICIO_FINALIZADO,
    SERVICIO_PENDIENTE,
    SERVICIO_PROGRAMADO,
    Servicio,
)
from .forms import AyudanteForm, ConductorForm, EquipoDiaForm, VehiculoForm
from .models import (
    Ayudante,
    Conductor,
    EquipoDia,
    EquipoFrecuente,
    ProgramacionServicio,
    Vehiculo,
)


@login_required
def campo_index(request):
    return redirect("dashboard-campo-conductores")


# ---------------------------------------------------------------------------
# Vehículos  (field config used by generic_list)
# ---------------------------------------------------------------------------

VEHICULO_FIELDS = [
    {"name": "placa", "label": "Placa"},
    {"name": "marca", "label": "Marca"},
    {"name": "modelo", "label": "Modelo"},
    {"name": "anio", "label": "Año"},
    {"name": "capacidad_toneladas", "label": "Cap. (t)"},
    {"name": "activo", "label": "Activo", "type": "boolean"},
]


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def vehiculo_list(request):
    vehiculos = Vehiculo.objects.all()
    return render(request, "campo/generic_list.html", {
        "title": "Vehículos",
        "items": vehiculos,
        "field_config": VEHICULO_FIELDS,
        "create_url": "vehiculo_create",
        "edit_url_name": "vehiculo_edit",
        "toggle_url_name": "vehiculo_toggle",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def vehiculo_create(request):
    if request.method == "POST":
        form = VehiculoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Vehículo creado correctamente.")
            return redirect("dashboard-campo-vehiculos")
    else:
        form = VehiculoForm()
    return render(request, "campo/generic_form.html", {
        "title": "Nuevo Vehículo",
        "form": form,
        "cancel_url": "dashboard-campo-vehiculos",
        "submit_label": "Crear Vehículo",
        "active_section": "campo",
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
            return redirect("dashboard-campo-vehiculos")
    else:
        form = VehiculoForm(instance=vehiculo)
    return render(request, "campo/generic_form.html", {
        "title": "Editar Vehículo",
        "form": form,
        "cancel_url": "dashboard-campo-vehiculos",
        "submit_label": "Guardar Cambios",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def vehiculo_toggle(request, pk):
    vehiculo = get_object_or_404(Vehiculo, pk=pk)
    vehiculo.activo = not vehiculo.activo
    vehiculo.save(update_fields=["activo"])
    msg = "activado" if vehiculo.activo else "desactivado"
    messages.success(request, f"Vehículo {vehiculo.placa} {msg}.")
    return redirect("dashboard-campo-vehiculos")


# ---------------------------------------------------------------------------
# Conductores
# ---------------------------------------------------------------------------

CONDUCTOR_FIELDS = [
    {"name": "nombre", "label": "Nombre"},
    {"name": "dni", "label": "DNI"},
    {"name": "telefono", "label": "Teléfono"},
    {"name": "numero_licencia", "label": "N° Licencia"},
    {"name": "activo", "label": "Activo", "type": "boolean"},
]


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def conductor_list(request):
    conductores = Conductor.objects.all()
    return render(request, "campo/generic_list.html", {
        "title": "Conductores",
        "items": conductores,
        "field_config": CONDUCTOR_FIELDS,
        "create_url": "conductor_create",
        "edit_url_name": "conductor_edit",
        "toggle_url_name": "conductor_toggle",
        "detail_url_name": "conductor_detail",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def conductor_detail(request, pk):
    conductor = get_object_or_404(Conductor, pk=pk)
    return render(request, "campo/detail.html", {
        "title": "Detalle de Conductor",
        "entity": conductor,
        "fields": [
            ("Nombre", conductor.nombre),
            ("DNI", conductor.dni),
            ("Teléfono", conductor.telefono),
            ("N° Licencia", conductor.numero_licencia or "-"),
            ("Categoría", conductor.categoria_licencia or "-"),
            ("Vencimiento Licencia", conductor.fecha_vencimiento_licencia.strftime("%d/%m/%Y") if conductor.fecha_vencimiento_licencia else "-"),
            ("Usuario asociado", str(conductor.usuario) if conductor.usuario else "-"),
            ("Estado", "Activo" if conductor.activo else "Inactivo"),
            ("Observaciones", conductor.observaciones or "-"),
        ],
        "edit_url_name": "conductor_edit",
        "list_url_name": "dashboard-campo-conductores",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def conductor_create(request):
    if request.method == "POST":
        form = ConductorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Conductor creado correctamente.")
            return redirect("dashboard-campo-conductores")
    else:
        form = ConductorForm()
    return render(request, "campo/generic_form.html", {
        "title": "Nuevo Conductor",
        "form": form,
        "cancel_url": "dashboard-campo-conductores",
        "submit_label": "Crear Conductor",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def conductor_edit(request, pk):
    conductor = get_object_or_404(Conductor, pk=pk)
    if request.method == "POST":
        form = ConductorForm(request.POST, instance=conductor)
        if form.is_valid():
            form.save()
            messages.success(request, "Conductor actualizado correctamente.")
            return redirect("dashboard-campo-conductores")
    else:
        form = ConductorForm(instance=conductor)
    return render(request, "campo/generic_form.html", {
        "title": "Editar Conductor",
        "form": form,
        "cancel_url": "dashboard-campo-conductores",
        "submit_label": "Guardar Cambios",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def conductor_toggle(request, pk):
    conductor = get_object_or_404(Conductor, pk=pk)
    conductor.activo = not conductor.activo
    conductor.save(update_fields=["activo"])
    msg = "activado" if conductor.activo else "desactivado"
    messages.success(request, f"Conductor {conductor.nombre} {msg}.")
    return redirect("dashboard-campo-conductores")


# ---------------------------------------------------------------------------
# Ayudantes
# ---------------------------------------------------------------------------

AYUDANTE_FIELDS = [
    {"name": "nombre", "label": "Nombre"},
    {"name": "dni", "label": "DNI"},
    {"name": "telefono", "label": "Teléfono"},
    {"name": "activo", "label": "Activo", "type": "boolean"},
]


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def ayudante_list(request):
    ayudantes = Ayudante.objects.all()
    return render(request, "campo/generic_list.html", {
        "title": "Ayudantes",
        "items": ayudantes,
        "field_config": AYUDANTE_FIELDS,
        "create_url": "ayudante_create",
        "edit_url_name": "ayudante_edit",
        "toggle_url_name": "ayudante_toggle",
        "detail_url_name": "ayudante_detail",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def ayudante_detail(request, pk):
    ayudante = get_object_or_404(Ayudante, pk=pk)
    return render(request, "campo/detail.html", {
        "title": "Detalle de Ayudante",
        "entity": ayudante,
        "fields": [
            ("Nombre", ayudante.nombre),
            ("DNI", ayudante.dni),
            ("Teléfono", ayudante.telefono),
            ("Usuario asociado", str(ayudante.usuario) if ayudante.usuario else "-"),
            ("Estado", "Activo" if ayudante.activo else "Inactivo"),
            ("Observaciones", ayudante.observaciones or "-"),
        ],
        "edit_url_name": "ayudante_edit",
        "list_url_name": "dashboard-campo-ayudantes",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def ayudante_create(request):
    if request.method == "POST":
        form = AyudanteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Ayudante creado correctamente.")
            return redirect("dashboard-campo-ayudantes")
    else:
        form = AyudanteForm()
    return render(request, "campo/generic_form.html", {
        "title": "Nuevo Ayudante",
        "form": form,
        "cancel_url": "dashboard-campo-ayudantes",
        "submit_label": "Crear Ayudante",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def ayudante_edit(request, pk):
    ayudante = get_object_or_404(Ayudante, pk=pk)
    if request.method == "POST":
        form = AyudanteForm(request.POST, instance=ayudante)
        if form.is_valid():
            form.save()
            messages.success(request, "Ayudante actualizado correctamente.")
            return redirect("dashboard-campo-ayudantes")
    else:
        form = AyudanteForm(instance=ayudante)
    return render(request, "campo/generic_form.html", {
        "title": "Editar Ayudante",
        "form": form,
        "cancel_url": "dashboard-campo-ayudantes",
        "submit_label": "Guardar Cambios",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def ayudante_toggle(request, pk):
    ayudante = get_object_or_404(Ayudante, pk=pk)
    ayudante.activo = not ayudante.activo
    ayudante.save(update_fields=["activo"])
    msg = "activado" if ayudante.activo else "desactivado"
    messages.success(request, f"Ayudante {ayudante.nombre} {msg}.")
    return redirect("dashboard-campo-ayudantes")


# ---------------------------------------------------------------------------
# Equipos por Día (calendario 3 días)
# ---------------------------------------------------------------------------

@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def equipo_calendario(request):
    hoy = datetime.now().date()
    fecha_param = request.GET.get("fecha")
    if fecha_param:
        try:
            fecha = datetime.strptime(fecha_param, "%Y%m%d").date()
        except ValueError:
            fecha = hoy
    else:
        fecha = hoy

    _DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    _DIAS_COMPLETOS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    _MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

    tab_days = [hoy + timedelta(days=i) for i in range(-1, 8)]

    fetch_start = min(tab_days[0], fecha)
    fetch_end   = max(tab_days[-1], fecha)
    all_equipos = list(
        EquipoDia.objects.filter(
            fecha__range=(fetch_start, fetch_end), activo=True,
        ).select_related("vehiculo", "conductor")
        .prefetch_related("ayudantes", "conductores_ayudantes", "servicios")
    )

    n_por_dia = {}
    for eq in all_equipos:
        n_por_dia[eq.fecha] = n_por_dia.get(eq.fecha, 0) + 1

    dias_tabs = []
    for day in tab_days:
        dias_tabs.append({
            "fecha": day,
            "fecha_str": day.strftime("%Y%m%d"),
            "nombre_dia": _DIAS_CORTOS[day.weekday()],
            "fecha_display": day.strftime("%d/%m"),
            "es_hoy": day == hoy,
            "activo": day == fecha,
            "n_equipos": n_por_dia.get(day, 0),
        })

    # Equipos of selected day
    equipos_dia = [eq for eq in all_equipos if eq.fecha == fecha]

    # Build warning maps
    cond_map = {}
    ayu_map  = {}
    cond_ayu_map = {}
    for eq in equipos_dia:
        cond_map.setdefault(eq.conductor_id, []).append(eq.id)
        for a in eq.ayudantes.all():
            ayu_map.setdefault(a.id, []).append(eq.id)
        for ca in eq.conductores_ayudantes.all():
            cond_ayu_map.setdefault(ca.id, []).append(eq.id)

    # Helper: build ayudantes_display combining real ayudantes + conductores_ayudantes
    def _ayudantes_display(eq):
        items = []
        for a in eq.ayudantes.all():
            items.append({
                "id": a.id, "nombre": a.nombre,
                "iniciales": a.nombre[0].upper() if a.nombre else "?",
                "tipo": "ayudante",
                "en_otro_equipo": len(ayu_map.get(a.id, [])) > 1,
            })
        for ca in eq.conductores_ayudantes.all():
            items.append({
                "id": ca.id, "nombre": ca.nombre,
                "iniciales": ca.nombre[0].upper() if ca.nombre else "?",
                "tipo": "conductor_ayudante",
                "en_otro_equipo": len(cond_ayu_map.get(ca.id, [])) > 1,
            })
        return items

    equipos_data = []
    for eq in equipos_dia:
        equipos_data.append({
            "id": eq.id,
            "placa": eq.vehiculo.placa,
            "vehiculo_id": eq.vehiculo.id,
            "conductor_id": eq.conductor.id,
            "conductor_nombre": eq.conductor.nombre,
            "conductor_iniciales": eq.conductor.nombre[0].upper() if eq.conductor.nombre else "C",
            "conductor_en_otro_equipo": len(cond_map.get(eq.conductor_id, [])) > 1,
            "ayudantes_display": _ayudantes_display(eq),
            "ayudante_ids": [a.id for a in eq.ayudantes.all()],
            "conductor_ayudante_ids": [c.id for c in eq.conductores_ayudantes.all()],
            "n_reservas": eq.servicios.count(),
            "observaciones": eq.observaciones or "",
        })

    # Today-equipo counts for status badges
    fecha_equipos_ids = [eq.id for eq in equipos_dia]

    # Vehicle counts
    vehiculos_qs = Vehiculo.objects.filter(activo=True).order_by("placa")
    v_counts = {}
    for eq in equipos_dia:
        v_counts[eq.vehiculo_id] = v_counts.get(eq.vehiculo_id, 0) + 1
    vehiculos_list = []
    for v in vehiculos_qs:
        n = v_counts.get(v.id, 0)
        vehiculos_list.append({
            "id": v.id, "placa": v.placa, "marca": v.marca, "modelo": v.modelo,
            "n_hoy": n,
            "status": "multi" if n >= 2 else ("activo" if n == 1 else "libre"),
        })

    # Conductor counts (including conductores_ayudantes)
    conductores_qs = Conductor.objects.filter(activo=True).order_by("nombre")
    c_counts = {}
    for eq in equipos_dia:
        c_counts[eq.conductor_id] = c_counts.get(eq.conductor_id, 0) + 1
        for ca in eq.conductores_ayudantes.all():
            c_counts[ca.id] = c_counts.get(ca.id, 0) + 1
    conductores_list = []
    for c in conductores_qs:
        n = c_counts.get(c.id, 0)
        conductores_list.append({
            "id": c.id, "nombre": c.nombre, "dni": c.dni,
            "n_hoy": n,
            "status": "multi" if n >= 2 else ("activo" if n == 1 else "libre"),
        })

    # Ayudante counts
    ayudantes_qs = Ayudante.objects.filter(activo=True).order_by("nombre")
    a_counts = {}
    for eq in equipos_dia:
        for a in eq.ayudantes.all():
            a_counts[a.id] = a_counts.get(a.id, 0) + 1
    ayudantes_list = []
    for a in ayudantes_qs:
        n = a_counts.get(a.id, 0)
        ayudantes_list.append({
            "id": a.id, "nombre": a.nombre, "dni": a.dni,
            "n_hoy": n,
            "status": "multi" if n >= 2 else ("activo" if n == 1 else "libre"),
        })

    def _s(qs, fields):
        return json.dumps(list(qs.values(*fields)), default=str)

    combinaciones_existentes_json = json.dumps([
        {
            "equipo_id": eq["id"],
            "vehiculo_id": eq["vehiculo_id"],
            "conductor_id": eq["conductor_id"],
        }
        for eq in equipos_data
    ])

    fecha_display = (
        f"{_DIAS_COMPLETOS[fecha.weekday()]}, "
        f"{fecha.day} de {_MESES_ES[fecha.month - 1]} {fecha.year}"
    )

    return render(request, "campo/equipo_calendario.html", {
        "fecha": fecha,
        "fecha_str": fecha.strftime("%Y%m%d"),
        "fecha_iso": fecha.strftime("%Y-%m-%d"),
        "fecha_display": fecha_display,
        "hoy": hoy,
        "equipos_data": equipos_data,
        "dias_tabs": dias_tabs,
        "vehiculos_list": vehiculos_list,
        "conductores_list": conductores_list,
        "ayudantes_list": ayudantes_list,
        "vehiculos_json": _s(vehiculos_qs, ["id", "placa", "marca", "modelo"]),
        "conductores_json": _s(conductores_qs, ["id", "nombre", "dni"]),
        "combinaciones_existentes_json": combinaciones_existentes_json,
        "prev_fecha": (fecha - timedelta(days=1)).strftime("%Y%m%d"),
        "next_fecha": (fecha + timedelta(days=1)).strftime("%Y%m%d"),
        "hoy_str": hoy.strftime("%Y%m%d"),
        "can_edit": can_manage_pizarra(request.user),
        "active_section": "campo",
    })


# ---------------------------------------------------------------------------
# Equipos por Día (old list)
# ---------------------------------------------------------------------------

EQUIPO_FIELDS = [
    {"name": "fecha", "label": "Fecha", "type": "date"},
    {"name": "vehiculo", "label": "Vehículo"},
    {"name": "conductor", "label": "Conductor"},
    {"name": "activo", "label": "Activo", "type": "boolean"},
]


@login_required
def equipo_list(request):
    user = request.user
    if user.groups.filter(name="Conductor").exists():
        equipos = EquipoDia.objects.filter(conductor__usuario=user)
    elif user.groups.filter(name="Ayudante").exists():
        equipos = EquipoDia.objects.filter(ayudantes__usuario=user)
    else:
        equipos = EquipoDia.objects.all()
    equipos = equipos.select_related("vehiculo", "conductor").prefetch_related("ayudantes")
    return render(request, "campo/generic_list.html", {
        "title": "Equipos de Campo",
        "items": equipos,
        "field_config": EQUIPO_FIELDS,
        "create_url": "equipo_create",
        "edit_url_name": "equipo_edit",
        "toggle_url_name": "equipo_toggle",
        "detail_url_name": "equipo_detail",
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def equipo_detail(request, pk):
    equipo = get_object_or_404(EquipoDia.objects.select_related("vehiculo", "conductor").prefetch_related("ayudantes"), pk=pk)
    servicios = equipo.servicios.select_related("servicio__cliente").all()
    return render(request, "campo/equipo_detail.html", {
        "title": f"Equipo {equipo.fecha} - {equipo.vehiculo.placa}",
        "equipo": equipo,
        "servicios": servicios,
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def equipo_create(request):
    initial = {}
    fecha = request.GET.get("fecha")
    vehiculo_id = request.GET.get("vehiculo")
    if fecha:
        initial["fecha"] = fecha
    if vehiculo_id:
        initial["vehiculo"] = vehiculo_id
    def _serialize(qs, fields):
        return json.dumps(list(qs.values(*fields)), default=str)

    vehiculos = Vehiculo.objects.filter(activo=True)
    conductores = Conductor.objects.filter(activo=True)
    ayudantes = Ayudante.objects.filter(activo=True)

    ctx = {
        "vehiculos_json": _serialize(vehiculos, ["id", "placa", "marca", "modelo"]),
        "conductores_json": _serialize(conductores, ["id", "nombre", "dni"]),
        "ayudantes_json": _serialize(ayudantes, ["id", "nombre", "dni"]),
        "cancel_url": "dashboard-campo-equipos",
        "active_section": "campo",
    }

    init_equipo = None
    if fecha:
        init_equipo = {"fecha": fecha}
    if vehiculo_id:
        try:
            v = Vehiculo.objects.get(id=vehiculo_id)
            if init_equipo is None:
                init_equipo = {}
            init_equipo["vehiculo"] = {"id": v.id, "placa": v.placa, "marca": v.marca, "modelo": v.modelo}
        except Vehiculo.DoesNotExist:
            pass
    ctx["equipo_json"] = json.dumps(init_equipo, default=str) if init_equipo else "null"

    if request.method == "POST":
        form = EquipoDiaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Equipo creado correctamente.")
            return redirect("dashboard-campo-equipos")
        ctx["form"] = form
    else:
        ctx["form"] = EquipoDiaForm(initial=initial or None)
    return render(request, "campo/equipo_drag_form.html", ctx)


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def equipo_edit(request, pk):
    equipo = get_object_or_404(EquipoDia, pk=pk)
    def _serialize(qs, fields):
        return json.dumps(list(qs.values(*fields)), default=str)

    vehiculos = Vehiculo.objects.filter(activo=True)
    conductores = Conductor.objects.filter(activo=True)
    ayudantes = Ayudante.objects.filter(activo=True)

    def _obj(o):
        if o is None: return None
        return {"id": o.id, "nombre": getattr(o, "nombre", ""), "dni": getattr(o, "dni", ""), "placa": getattr(o, "placa", ""), "marca": getattr(o, "marca", ""), "modelo": getattr(o, "modelo", "")}

    ctx = {
        "vehiculos_json": _serialize(vehiculos, ["id", "placa", "marca", "modelo"]),
        "conductores_json": _serialize(conductores, ["id", "nombre", "dni"]),
        "ayudantes_json": _serialize(ayudantes, ["id", "nombre", "dni"]),
        "equipo_json": json.dumps({
            "vehiculo": _obj(equipo.vehiculo),
            "conductor": _obj(equipo.conductor),
            "ayudantes": [_obj(a) for a in equipo.ayudantes.all()],
            "fecha": str(equipo.fecha),
            "activo": "true" if equipo.activo else "",
            "observaciones": equipo.observaciones or "",
        }, default=str),
        "cancel_url": "dashboard-campo-equipos",
        "active_section": "campo",
        "edit_mode": True,
        "equipo_id": pk,
    }

    if request.method == "POST":
        form = EquipoDiaForm(request.POST, instance=equipo)
        if form.is_valid():
            form.save()
            messages.success(request, "Equipo actualizado correctamente.")
            return redirect("dashboard-campo-equipos")
        ctx["form"] = form
    else:
        ctx["form"] = EquipoDiaForm(instance=equipo)
    return render(request, "campo/equipo_drag_form.html", ctx)


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def equipo_toggle(request, pk):
    equipo = get_object_or_404(EquipoDia, pk=pk)
    equipo.activo = not equipo.activo
    equipo.save(update_fields=["activo"])
    msg = "activado" if equipo.activo else "desactivado"
    messages.success(request, f"Equipo del {equipo.fecha} {msg}.")
    return redirect("dashboard-campo-equipos")


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def equipo_validar_ajax(request):
    """GET — devuelve si la combinación fecha+vehiculo+conductor ya existe."""
    fecha_str    = request.GET.get("fecha", "")
    vehiculo_id  = request.GET.get("vehiculo_id", "")
    conductor_id = request.GET.get("conductor_id", "")

    if not all([fecha_str, vehiculo_id, conductor_id]):
        return JsonResponse({"combinacion_existe": False, "mismo_vehiculo": False, "mismo_conductor": False})

    try:
        fecha        = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        vehiculo_id  = int(vehiculo_id)
        conductor_id = int(conductor_id)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Parámetros inválidos"}, status=400)

    equipos = EquipoDia.objects.filter(fecha=fecha, activo=True)
    combinacion_existe = equipos.filter(vehiculo_id=vehiculo_id, conductor_id=conductor_id).exists()
    mismo_vehiculo     = (not combinacion_existe) and equipos.filter(vehiculo_id=vehiculo_id).exists()
    mismo_conductor    = (not combinacion_existe) and equipos.filter(conductor_id=conductor_id).exists()

    return JsonResponse({
        "combinacion_existe": combinacion_existe,
        "mismo_vehiculo": mismo_vehiculo,
        "mismo_conductor": mismo_conductor,
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def equipo_crear_ajax(request):
    """POST — crea un EquipoDia y devuelve JSON."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    fecha_str       = data.get("fecha", "")
    vehiculo_id     = data.get("vehiculo_id")
    conductor_id    = data.get("conductor_id")
    ayudante_ids    = data.get("ayudante_ids", [])
    conductor_ayudante_ids = data.get("conductor_ayudante_ids", [])
    observaciones   = (data.get("observaciones") or "").strip()

    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return JsonResponse({"error": "Fecha inválida"}, status=400)

    vehiculo  = get_object_or_404(Vehiculo,  pk=vehiculo_id,  activo=True)
    conductor = get_object_or_404(Conductor, pk=conductor_id, activo=True)

    # Regla 1 — misma combinación vehiculo+conductor → bloqueante
    if EquipoDia.objects.filter(fecha=fecha, vehiculo=vehiculo, conductor=conductor).exists():
        return JsonResponse(
            {"error": f"El vehículo {vehiculo.placa} ya tiene asignado a {conductor.nombre} ese día."},
            status=409,
        )

    # Regla 2 — conductor principal no puede ser también ayudante
    if int(conductor_id) in [int(x) for x in conductor_ayudante_ids]:
        return JsonResponse(
            {"error": "El conductor principal no puede estar también como ayudante."},
            status=409,
        )

    warnings = []
    if EquipoDia.objects.filter(fecha=fecha, vehiculo=vehiculo).exists():
        warnings.append(f"El vehículo {vehiculo.placa} ya opera en otro equipo ese día.")
    if EquipoDia.objects.filter(fecha=fecha, conductor=conductor).exists():
        warnings.append(f"{conductor.nombre} ya está asignado a otro equipo ese día.")

    equipo = EquipoDia.objects.create(
        fecha=fecha, vehiculo=vehiculo, conductor=conductor,
        observaciones=observaciones, activo=True,
    )
    if ayudante_ids:
        equipo.ayudantes.set(Ayudante.objects.filter(pk__in=ayudante_ids, activo=True))
    if conductor_ayudante_ids:
        equipo.conductores_ayudantes.set(
            Conductor.objects.filter(pk__in=conductor_ayudante_ids, activo=True)
        )

    return JsonResponse({
        "status": "ok",
        "warnings": warnings,
        "equipo": {"id": equipo.id, "placa": vehiculo.placa, "conductor": conductor.nombre},
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def equipo_editar_ajax(request, pk):
    equipo = get_object_or_404(EquipoDia, pk=pk)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON invalido"}, status=400)

    vehiculo_id = data.get("vehiculo_id")
    conductor_id = data.get("conductor_id")
    ayudante_ids = data.get("ayudante_ids", [])
    conductor_ayudante_ids = data.get("conductor_ayudante_ids", [])
    observaciones = (data.get("observaciones") or "").strip()

    vehiculo = get_object_or_404(Vehiculo, pk=vehiculo_id, activo=True)
    conductor = get_object_or_404(Conductor, pk=conductor_id, activo=True)

    try:
        conductor_ayudante_ids = [int(value) for value in conductor_ayudante_ids]
    except (TypeError, ValueError):
        return JsonResponse({"error": "Conductores ayudantes invalidos"}, status=409)
    if conductor.id in conductor_ayudante_ids:
        return JsonResponse(
            {"error": "El conductor principal no puede estar tambien como ayudante."},
            status=409,
        )

    otros = EquipoDia.objects.filter(fecha=equipo.fecha, activo=True).exclude(pk=equipo.pk)
    if otros.filter(vehiculo=vehiculo, conductor=conductor).exists():
        return JsonResponse(
            {"error": f"La combinacion {vehiculo.placa} + {conductor.nombre} ya existe ese dia."},
            status=409,
        )

    warnings = []
    if otros.filter(vehiculo=vehiculo).exists():
        warnings.append(f"El vehiculo {vehiculo.placa} ya opera en otro equipo ese dia.")
    if otros.filter(conductor=conductor).exists():
        warnings.append(f"{conductor.nombre} ya esta asignado a otro equipo ese dia.")

    equipo.vehiculo = vehiculo
    equipo.conductor = conductor
    equipo.observaciones = observaciones
    equipo.save(update_fields=["vehiculo", "conductor", "observaciones"])
    equipo.ayudantes.set(Ayudante.objects.filter(pk__in=ayudante_ids, activo=True))
    equipo.conductores_ayudantes.set(
        Conductor.objects.filter(pk__in=conductor_ayudante_ids, activo=True)
    )

    return JsonResponse({
        "status": "ok",
        "warnings": warnings,
        "equipo": {
            "id": equipo.id,
            "placa": vehiculo.placa,
            "conductor": conductor.nombre,
        },
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def equipo_eliminar_ajax(request, pk):
    """POST — elimina el EquipoDia; las programaciones quedan con equipo_dia=NULL."""
    equipo = get_object_or_404(EquipoDia, pk=pk)
    n_reservas = equipo.servicios.count()
    equipo.delete()
    return JsonResponse({"status": "ok", "n_reservas": n_reservas})


# ---------------------------------------------------------------------------
# Pizarra — tablero operativo tipo calendario
# ---------------------------------------------------------------------------

ESTADO_A_OPERATIVO = {
    SERVICIO_PENDIENTE: ProgramacionServicio.ESTADO_PROGRAMADO,
    SERVICIO_PROGRAMADO: ProgramacionServicio.ESTADO_PROGRAMADO,
    SERVICIO_ASIGNADO: ProgramacionServicio.ESTADO_PROGRAMADO,
    SERVICIO_EN_RUTA: ProgramacionServicio.ESTADO_EN_RUTA,
    SERVICIO_FINALIZADO: ProgramacionServicio.ESTADO_FINALIZADO,
    SERVICIO_CANCELADO: ProgramacionServicio.ESTADO_CANCELADO,
}

HORAS_PIZARRA = []
for _h in range(24):
    HORAS_PIZARRA.append(f'{_h:02d}:00')
    HORAS_PIZARRA.append(f'{_h:02d}:30')


def _slot_label(s):
    hh, mm = int(s[:2]), int(s[3:])
    amp = "am" if hh < 12 else "pm"
    h12 = hh if hh <= 12 else hh - 12
    h12 = 12 if h12 == 0 else h12
    return f"{h12}:{mm:02d} {amp}"


HORAS_CABECERA = [
    {"hora": f"{h:02d}:00", "label": _slot_label(f"{h:02d}:00")}
    for h in range(24)
]
HORAS_SLOTS = [{"hora": s, "label": _slot_label(s)} for s in HORAS_PIZARRA]
_N_SLOTS = len(HORAS_PIZARRA)


def _servicio_hora(servicio):
    valor = (servicio.horario_servicio or "").strip()
    for formato in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(valor, formato).time()
        except ValueError:
            continue
    return None

_DIAS_ES = ['LUNES', 'MARTES', 'MIÉRCOLES', 'JUEVES', 'VIERNES', 'SÁBADO', 'DOMINGO']
_MESES_ES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
             'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
_ESTADO_LABELS = {
    'pendiente': 'Pendiente', 'programado': 'Programado', 'asignado': 'Asignado',
    'en_ruta': 'En ruta', 'finalizado': 'Finalizado', 'cancelado': 'Cancelado',
}
_DIA_GRADIENTS = {
    0: 'linear-gradient(135deg,#20A477,#15805D)',
    1: 'linear-gradient(135deg,#3B82D0,#2866AA)',
    2: 'linear-gradient(135deg,#8B6FC2,#6F54A5)',
    3: 'linear-gradient(135deg,#D9902F,#B8721F)',
    4: 'linear-gradient(135deg,#D95762,#B83E49)',
    5: 'linear-gradient(135deg,#2798B1,#1D758B)',
    6: 'linear-gradient(135deg,#64748B,#475569)',
}
_HOY_GRADIENT = 'linear-gradient(135deg,#7C3AED,#5B21B6)'


def _time_to_slot(t):
    slot = t.hour * 2 + (1 if t.minute >= 30 else 0)
    return max(0, min(_N_SLOTS - 1, slot))


def _calc_rowspan(ps):
    if ps.hora_fin:
        ini = datetime.combine(ps.fecha, ps.hora_inicio)
        fin = datetime.combine(ps.fecha, ps.hora_fin)
        mins = (fin - ini).total_seconds() / 60
        return max(1, round(mins / 30))
    return 2


def _build_equipo_cells(eq_obj, fecha):
    fecha_iso = fecha.strftime('%Y-%m-%d')
    cells = [
        {
            'tipo': 'empty',
            'hora': s['hora'],
            'hora_display': s['label'],
            'equipo_id': eq_obj.id,
            'equipo_fecha': fecha_iso,
        }
        for s in HORAS_SLOTS
    ]
    for ps in getattr(eq_obj, 'servicios_list', []):
        slot = _time_to_slot(ps.hora_inicio)
        rowspan = min(_calc_rowspan(ps), _N_SLOTS - slot)
        s = ps.servicio
        estado = s.estado if s else 'pendiente'
        hora_str = ps.hora_inicio.strftime('%I:%M %p').lower().lstrip('0')
        hora_fin_str = ps.hora_fin.strftime('%I:%M %p').lower().lstrip('0') if ps.hora_fin else ''
        duracion_hs = rowspan / 2
        cells[slot] = {
            'tipo': 'booking',
            'rowspan': rowspan,
            'ps_id': ps.id,
            'equipo_id': eq_obj.id,
            'servicio_estado': estado,
            'servicio_estado_label': _ESTADO_LABELS.get(estado, estado),
            'servicio_pk': s.pk if s else None,
            'servicio_codigo': s.codigo if s else '—',
            'cliente': s.cliente.nombre if s and s.cliente else '—',
            'origen': s.direccion_origen if s else '',
            'destino': s.direccion_destino if s else '',
            'hora_display': hora_str,
            'hora_fin_display': hora_fin_str,
            'start_minute': ps.hora_inicio.minute,
            'precio': f"S/ {ps.monto:.0f}" if ps.monto else '',
            'duracion': f"{duracion_hs:.1f}h".replace('.0h', 'h'),
            'duracion_hs': duracion_hs,
        }
        for j in range(1, rowspan):
            if slot + j < _N_SLOTS:
                cells[slot + j] = {'tipo': 'spanned'}
    return cells


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas", "Conductor", "Ayudante")
def pizarra(request):
    today = datetime.now().date()
    date_param = request.GET.get("date")
    start_param = request.GET.get("start")
    selected_date = today
    if date_param:
        try:
            selected_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            selected_date = today
    elif start_param:
        try:
            selected_date = datetime.strptime(start_param, "%Y%m%d").date()
        except ValueError:
            selected_date = today

    start_date = selected_date
    days = [start_date]
    prev_start = (start_date - timedelta(days=1)).strftime("%Y%m%d")
    next_start = (start_date + timedelta(days=1)).strftime("%Y%m%d")

    user = request.user

    nav_days_dates = [
        selected_date + timedelta(days=offset)
        for offset in range(-1, 8)
    ]
    nav_counts = {
        item["fecha"]: item["total"]
        for item in ProgramacionServicio.objects.filter(
            fecha__range=(nav_days_dates[0], nav_days_dates[-1]),
        ).values("fecha").annotate(total=Count("id"))
    }
    for item in Servicio.objects.filter(
        fecha_servicio__range=(nav_days_dates[0], nav_days_dates[-1]),
        programaciones__isnull=True,
    ).exclude(
        estado=SERVICIO_CANCELADO,
    ).values("fecha_servicio").annotate(total=Count("id")):
        nav_counts[item["fecha_servicio"]] = (
            nav_counts.get(item["fecha_servicio"], 0) + item["total"]
        )
    nav_days = [
        {
            "fecha_iso": day.strftime("%Y-%m-%d"),
            "nombre": _DIAS_ES[day.weekday()][:3],
            "fecha_corta": day.strftime("%d/%m"),
            "total": nav_counts.get(day, 0),
            "seleccionado": day == selected_date,
            "es_hoy": day == today,
        }
        for day in nav_days_dates
    ]

    equipos_qs = EquipoDia.objects.filter(
        fecha__range=(days[0], days[-1]), activo=True,
    ).select_related("vehiculo", "conductor").prefetch_related(
        "ayudantes", "conductores_ayudantes",
        Prefetch(
            "servicios",
            queryset=ProgramacionServicio.objects.select_related(
                "servicio", "servicio__cliente",
            ).order_by("hora_inicio"),
            to_attr="servicios_list",
        ),
    )

    if user.groups.filter(name="Conductor").exists():
        equipos_qs = equipos_qs.filter(conductor__usuario=user)
    elif user.groups.filter(name="Ayudante").exists():
        equipos_qs = equipos_qs.filter(ayudantes__usuario=user)

    equipos_por_fecha = {day: [] for day in days}
    legacy_programaciones_asignadas = set()
    for eq in equipos_qs:
        legacy = list(
            ProgramacionServicio.objects.filter(
                equipo_dia__isnull=True,
                fecha=eq.fecha,
                vehiculo_id=eq.vehiculo_id,
                conductor_id=eq.conductor_id,
            ).select_related("servicio", "servicio__cliente").order_by("hora_inicio")
        )
        if legacy:
            eq.servicios_list.extend(legacy)
            legacy_programaciones_asignadas.update(item.id for item in legacy)
        if eq.fecha in equipos_por_fecha:
            equipos_por_fecha[eq.fecha].append(eq)

    # Programaciones without equipo_dia (orphans) — per day in header
    orphan_progs = list(
        ProgramacionServicio.objects.filter(
            fecha__range=(days[0], days[-1]),
            equipo_dia__isnull=True,
        ).exclude(id__in=legacy_programaciones_asignadas)
        .select_related("servicio", "servicio__cliente").order_by("fecha", "hora_inicio")
    )
    orphan_por_fecha = {day: [] for day in days}
    for ps in orphan_progs:
        if ps.fecha not in orphan_por_fecha:
            continue
        servicio = ps.servicio
        orphan_por_fecha[ps.fecha].append({
            "ps_id": ps.id,
            "servicio_id": servicio.pk if servicio else None,
            "servicio_pk": servicio.pk if servicio else None,
            "codigo": servicio.codigo if servicio else "—",
            "cliente": (
                servicio.cliente.nombre
                if servicio and servicio.cliente
                else "Sin cliente"
            ),
            "hora": ps.hora_inicio.strftime("%H:%M"),
            "hora_display": ps.hora_inicio.strftime("%I:%M %p").lower().lstrip("0"),
            "monto": f"S/ {ps.monto:.0f}" if ps.monto else "Sin precio",
            "fecha_iso": ps.fecha.strftime("%Y-%m-%d"),
            "editar_url": reverse("dashboard-servicios-edit", args=[servicio.pk]) if servicio else "",
        })

    servicios_sin_programar = Servicio.objects.filter(
        fecha_servicio__range=(days[0], days[-1]),
        programaciones__isnull=True,
    ).exclude(
        estado=SERVICIO_CANCELADO,
    ).select_related("cliente").order_by("fecha_servicio", "horario_servicio", "id")
    for servicio in servicios_sin_programar:
        hora = _servicio_hora(servicio)
        orphan_por_fecha[servicio.fecha_servicio].append({
            "ps_id": None,
            "servicio_id": servicio.pk,
            "servicio_pk": servicio.pk,
            "codigo": servicio.codigo,
            "cliente": servicio.cliente.nombre if servicio.cliente else "Sin cliente",
            "hora": hora.strftime("%H:%M") if hora else "",
            "hora_display": hora.strftime("%I:%M %p").lower().lstrip("0") if hora else "Sin hora",
            "monto": f"S/ {servicio.precio:.0f}" if servicio.precio else "Sin precio",
            "fecha_iso": servicio.fecha_servicio.strftime("%Y-%m-%d"),
            "editar_url": reverse("dashboard-servicios-edit", args=[servicio.pk]),
        })

    dias_data = []
    total_equipos = total_activas = total_pendientes = 0

    for day in days:
        equipos_dia = equipos_por_fecha[day]
        total_equipos += len(equipos_dia)
        gradient = _HOY_GRADIENT if day == today else _DIA_GRADIENTS[day.weekday()]
        fecha_display = f"{day.day} de {_MESES_ES[day.month-1]} {day.year}"

        equipos_list = []
        for eq in equipos_dia:
            cells = _build_equipo_cells(eq, day)
            for cell in cells:
                if cell['tipo'] == 'booking':
                    total_activas += 1
                    if cell.get('servicio_estado') == 'pendiente':
                        total_pendientes += 1

            # Calcular indicadores de criticidad
            saldo_pendiente = Decimal('0')
            sin_precio = False
            for ps in getattr(eq, 'servicios_list', []):
                servicio = ps.servicio if hasattr(ps, 'servicio') else None
                if servicio:
                    if not servicio.precio:
                        sin_precio = True
                    else:
                        total_pagado = getattr(servicio, 'total_pagado', Decimal('0')) or Decimal('0')
                        saldo = (servicio.precio or Decimal('0')) - total_pagado
                        if saldo > 0:
                            saldo_pendiente += saldo

            equipos_list.append({
                'id': eq.id,
                'placa': eq.vehiculo.placa,
                'vehiculo_id': eq.vehiculo_id,
                'conductor': eq.conductor.nombre,
                'conductor_id': eq.conductor_id,
                'ayudantes': ", ".join(a.nombre for a in eq.ayudantes.all()),
                'ayudante_ids': [a.id for a in eq.ayudantes.all()],
                'conductor_ayudante_ids': [
                    c.id for c in eq.conductores_ayudantes.all()
                ],
                'observaciones': eq.observaciones or "",
                'horas': cells,
                'n_servicios': len(getattr(eq, 'servicios_list', [])),
                'saldo_pendiente': str(saldo_pendiente) if saldo_pendiente > 0 else None,
                'sin_precio': sin_precio,
            })

        dias_data.append({
            'fecha': day,
            'fecha_str': day.strftime('%Y%m%d'),
            'fecha_iso': day.strftime('%Y-%m-%d'),
            'nombre_dia': _DIAS_ES[day.weekday()],
            'fecha_display': fecha_display,
            'es_hoy': day == today,
            'gradient': gradient,
            'n_equipos': len(equipos_list),
            'colspan': len(equipos_list) + 1,
            'equipos': equipos_list,
            'sin_asignar': orphan_por_fecha[day],
            'filas_relleno': range(max(0, 8 - len(equipos_list))),
        })

    # Flat rows for template — avoids complex template indexing logic
    rows = []
    for i, hora in enumerate(HORAS_PIZARRA):
        cells = []
        for dia in dias_data:
            for eq in dia['equipos']:
                cells.append(eq['horas'][i])
            cells.append({'tipo': 'spacer', 'fecha_str': dia['fecha_str'], 'fecha_iso': dia['fecha_iso']})
        rows.append({'hora': hora, 'cells': cells})

    def _s(qs, fields):
        return list(qs.values(*fields))

    equipos_formados = []
    composiciones_vistas = set()
    equipos_recientes = EquipoDia.objects.filter(
        activo=True,
        vehiculo__activo=True,
        conductor__activo=True,
    ).select_related("vehiculo", "conductor").prefetch_related(
        "ayudantes", "conductores_ayudantes",
    ).order_by("-fecha", "-id")[:100]
    for equipo in equipos_recientes:
        ayudantes = list(equipo.ayudantes.filter(activo=True).order_by("nombre"))
        conductores_ayudantes = list(
            equipo.conductores_ayudantes.filter(activo=True).order_by("nombre")
        )
        composicion = (
            equipo.vehiculo_id,
            equipo.conductor_id,
            tuple(a.id for a in ayudantes),
            tuple(c.id for c in conductores_ayudantes),
        )
        if composicion in composiciones_vistas:
            continue
        composiciones_vistas.add(composicion)
        equipos_formados.append({
            "id": equipo.id,
            "placa": equipo.vehiculo.placa,
            "vehiculo": f"{equipo.vehiculo.marca} {equipo.vehiculo.modelo}".strip(),
            "conductor": equipo.conductor.nombre,
            "ayudantes": [a.nombre for a in ayudantes],
            "conductores_ayudantes": [c.nombre for c in conductores_ayudantes],
            "fecha": equipo.fecha.strftime("%Y-%m-%d"),
        })

    start_display = (
        f"{_DIAS_ES[start_date.weekday()].capitalize()}, "
        f"{start_date.day} de {_MESES_ES[start_date.month-1]} {start_date.year}"
    )

    servicios_periodo = Servicio.objects.filter(
        Q(programaciones__fecha__range=(days[0], days[-1]))
        | Q(fecha_servicio__range=(days[0], days[-1])),
    ).exclude(
        estado=SERVICIO_CANCELADO,
    ).distinct().prefetch_related("pagos")
    monto_total = Decimal("0")
    cobrado_total = Decimal("0")
    saldo_total = Decimal("0")
    for servicio in servicios_periodo:
        precio = servicio.precio or Decimal("0")
        cobrado = Decimal("0")
        descuentos = Decimal("0")
        for pago in servicio.pagos.all():
            if pago.concepto in {"adelanto", "parcial", "final"}:
                cobrado += pago.monto
            elif pago.concepto in {"descuento", "ajuste"}:
                descuentos += pago.monto
        monto_total += precio
        cobrado_total += cobrado
        saldo_total += max(precio - cobrado - descuentos, Decimal("0"))

    can_edit = can_manage_pizarra(user) or user.is_superuser
    equipos_edicion = [
        {
            "id": equipo["id"],
            "vehiculo_id": equipo["vehiculo_id"],
            "conductor_id": equipo["conductor_id"],
            "ayudante_ids": equipo["ayudante_ids"],
            "conductor_ayudante_ids": equipo["conductor_ayudante_ids"],
            "observaciones": equipo["observaciones"],
        }
        for dia in dias_data
        for equipo in dia["equipos"]
    ]

    return render(request, "campo/pizarra.html", {
        'dias_data': dias_data,
        'rows': rows,
        'horas_pizarra': HORAS_PIZARRA,
        'horas_cabecera': HORAS_CABECERA,
        'horas_slots': HORAS_SLOTS,
        'orphan_progs': orphan_progs,
        'start_str': start_date.strftime('%Y%m%d'),
        'prev_start': prev_start,
        'next_start': next_start,
        'selected_date_iso': selected_date.strftime("%Y-%m-%d"),
        'navigation_period': "Día" if request.GET.get("view") == "day" else "Semana",
        'nav_days': nav_days,
        'start_display': start_display,
        'total_equipos': total_equipos,
        'total_activas': total_activas,
        'total_pendientes': total_pendientes,
        'total_reservas': servicios_periodo.count(),
        'monto_total': monto_total,
        'cobrado_total': cobrado_total,
        'saldo_total': saldo_total,
        'can_edit': can_edit,
        'vehiculos_json': _s(Vehiculo.objects.filter(activo=True).order_by("placa"), ['id', 'placa', 'marca', 'modelo']),
        'conductores_json': _s(Conductor.objects.filter(activo=True).order_by("nombre"), ['id', 'nombre', 'dni']),
        'ayudantes_json': _s(Ayudante.objects.filter(activo=True).order_by("nombre"), ['id', 'nombre', 'dni']),
        'equipos_formados_json': equipos_formados,
        'equipos_edicion_json': equipos_edicion,
        'equipos_dia_json': [
            {
                "id": eq["id"], "placa": eq["placa"],
                "fecha": dia["fecha_iso"],
                "conductor": eq["conductor"],
                "ayudantes": eq.get("ayudantes", "").split(", ") if eq.get("ayudantes") else [],
                "n_reservas": eq.get("n_reservas", 0),
            }
            for dia in dias_data for eq in dia.get("equipos", [])
        ],
        'equipos_frecuentes_json': [
            {
                "id": ef.id, "nombre": ef.nombre,
                "placa": ef.vehiculo.placa,
                "vehiculo": f"{ef.vehiculo.marca} {ef.vehiculo.modelo}".strip(),
                "conductor": ef.conductor.nombre,
                "ayudantes": [a.nombre for a in ef.ayudantes.filter(activo=True)],
                "conductores_ayudantes": [c.nombre for c in ef.conductores_ayudantes.filter(activo=True)],
            }
            for ef in EquipoFrecuente.objects.filter(activo=True)
            .select_related("vehiculo", "conductor")
            .prefetch_related("ayudantes", "conductores_ayudantes")
            .order_by("orden", "nombre")
        ],
        'active_section': 'pizarra',
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
def equipos_frecuentes_list(request):
    frecuentes = (
        EquipoFrecuente.objects
        .filter(activo=True)
        .select_related("vehiculo", "conductor")
        .prefetch_related("ayudantes", "conductores_ayudantes")
        .order_by("orden", "nombre")
    )
    frecuentes_data = []
    for ef in frecuentes:
        ayudantes = list(ef.ayudantes.filter(activo=True))
        cond_ay = list(ef.conductores_ayudantes.filter(activo=True))
        frecuentes_data.append({
            "id": ef.id,
            "nombre": ef.nombre,
            "placa": ef.vehiculo.placa,
            "vehiculo_str": f"{ef.vehiculo.marca} {ef.vehiculo.modelo}".strip(),
            "vehiculo_id": ef.vehiculo_id,
            "conductor": ef.conductor.nombre,
            "conductor_id": ef.conductor_id,
            "ayudantes": [a.nombre for a in ayudantes],
            "ayudante_ids": [a.id for a in ayudantes],
            "conductores_ayudantes": [c.nombre for c in cond_ay],
            "conductor_ayudante_ids": [c.id for c in cond_ay],
        })
    return render(request, "campo/equipos_frecuentes.html", {
        "frecuentes_json": frecuentes_data,
        "vehiculos_json": list(Vehiculo.objects.filter(activo=True).order_by("placa").values("id", "placa", "marca", "modelo")),
        "conductores_json": list(Conductor.objects.filter(activo=True).order_by("nombre").values("id", "nombre", "dni")),
        "ayudantes_json": list(Ayudante.objects.filter(activo=True).order_by("nombre").values("id", "nombre", "dni")),
        "active_section": "campo",
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def equipos_frecuentes_crear_ajax(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return JsonResponse({"error": "El nombre es requerido"}, status=400)
    vehiculo = get_object_or_404(Vehiculo, pk=data.get("vehiculo_id"), activo=True)
    conductor = get_object_or_404(Conductor, pk=data.get("conductor_id"), activo=True)
    ayudante_ids = [int(x) for x in (data.get("ayudante_ids") or [])]
    cond_ay_ids = [int(x) for x in (data.get("conductor_ayudante_ids") or [])]
    ef = EquipoFrecuente.objects.create(nombre=nombre, vehiculo=vehiculo, conductor=conductor)
    if ayudante_ids:
        ef.ayudantes.set(Ayudante.objects.filter(pk__in=ayudante_ids, activo=True))
    if cond_ay_ids:
        ef.conductores_ayudantes.set(Conductor.objects.filter(pk__in=cond_ay_ids, activo=True))
    return JsonResponse({"status": "ok", "id": ef.id, "nombre": ef.nombre})


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def equipos_frecuentes_editar_ajax(request, pk):
    ef = get_object_or_404(EquipoFrecuente, pk=pk)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return JsonResponse({"error": "El nombre es requerido"}, status=400)
    vehiculo = get_object_or_404(Vehiculo, pk=data.get("vehiculo_id"), activo=True)
    conductor = get_object_or_404(Conductor, pk=data.get("conductor_id"), activo=True)
    ayudante_ids = [int(x) for x in (data.get("ayudante_ids") or [])]
    cond_ay_ids = [int(x) for x in (data.get("conductor_ayudante_ids") or [])]
    ef.nombre = nombre
    ef.vehiculo = vehiculo
    ef.conductor = conductor
    ef.save(update_fields=["nombre", "vehiculo", "conductor"])
    ef.ayudantes.set(Ayudante.objects.filter(pk__in=ayudante_ids, activo=True))
    ef.conductores_ayudantes.set(Conductor.objects.filter(pk__in=cond_ay_ids, activo=True))
    return JsonResponse({"status": "ok"})


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def equipos_frecuentes_eliminar_ajax(request, pk):
    ef = get_object_or_404(EquipoFrecuente, pk=pk)
    ef.activo = False
    ef.save(update_fields=["activo"])
    return JsonResponse({"status": "ok"})


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def api_crear_equipo_desde_frecuente(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)
    ef = get_object_or_404(EquipoFrecuente, pk=data.get("frecuente_id"), activo=True)
    try:
        fecha = datetime.strptime(data.get("fecha"), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return JsonResponse({"error": "Fecha inválida"}, status=400)
    if EquipoDia.objects.filter(fecha=fecha, vehiculo=ef.vehiculo, conductor=ef.conductor).exists():
        return JsonResponse(
            {"error": f"Ya existe ese equipo para el {fecha.strftime('%d/%m/%Y')}"},
            status=409,
        )
    warnings = []
    if EquipoDia.objects.filter(fecha=fecha, vehiculo=ef.vehiculo).exists():
        warnings.append(f"El vehículo {ef.vehiculo.placa} ya opera en otro equipo ese día.")
    if EquipoDia.objects.filter(fecha=fecha, conductor=ef.conductor).exists():
        warnings.append(f"{ef.conductor.nombre} ya está asignado a otro equipo ese día.")
    equipo = EquipoDia.objects.create(fecha=fecha, vehiculo=ef.vehiculo, conductor=ef.conductor)
    ay_ids = list(ef.ayudantes.values_list("id", flat=True))
    ca_ids = list(ef.conductores_ayudantes.values_list("id", flat=True))
    if ay_ids:
        equipo.ayudantes.set(Ayudante.objects.filter(pk__in=ay_ids, activo=True))
    if ca_ids:
        equipo.conductores_ayudantes.set(Conductor.objects.filter(pk__in=ca_ids, activo=True))
    return JsonResponse({"status": "ok", "warnings": warnings, "equipo": {"id": equipo.id}})


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def api_crear_equipo_pizarra(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    fecha_str = data.get("fecha")
    equipo_origen_id = data.get("equipo_origen_id")
    vehiculo_id = data.get("vehiculo_id")
    conductor_id = data.get("conductor_id")
    ayudante_ids = data.get("ayudante_ids", [])
    conductor_ayudante_ids = data.get("conductor_ayudante_ids", [])

    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return JsonResponse({"error": "Fecha inválida"}, status=400)

    if equipo_origen_id:
        equipo_origen = get_object_or_404(
            EquipoDia.objects.prefetch_related("ayudantes", "conductores_ayudantes"),
            pk=equipo_origen_id,
            activo=True,
        )
        vehiculo_id = equipo_origen.vehiculo_id
        conductor_id = equipo_origen.conductor_id
        ayudante_ids = list(equipo_origen.ayudantes.values_list("id", flat=True))
        conductor_ayudante_ids = list(
            equipo_origen.conductores_ayudantes.values_list("id", flat=True)
        )

    vehiculo = get_object_or_404(Vehiculo, pk=vehiculo_id, activo=True)
    conductor = get_object_or_404(Conductor, pk=conductor_id, activo=True)

    try:
        conductor_ayudante_ids = [int(pk) for pk in conductor_ayudante_ids]
    except (TypeError, ValueError):
        return JsonResponse({"error": "Conductores ayudantes invalidos"}, status=409)
    if conductor.id in conductor_ayudante_ids:
        return JsonResponse(
            {"error": "El conductor principal no puede estar tambien como ayudante."},
            status=409,
        )

    if EquipoDia.objects.filter(
        fecha=fecha, vehiculo=vehiculo, conductor=conductor,
    ).exists():
        return JsonResponse(
            {"error": f"El vehículo {vehiculo.placa} ya tiene equipo ese día"}, status=409
        )

    warnings = []
    if EquipoDia.objects.filter(fecha=fecha, vehiculo=vehiculo).exists():
        warnings.append(f"El vehiculo {vehiculo.placa} ya opera en otro equipo ese dia.")
    if EquipoDia.objects.filter(fecha=fecha, conductor=conductor).exists():
        warnings.append(f"{conductor.nombre} ya está asignado a otro equipo ese día.")

    equipo = EquipoDia.objects.create(fecha=fecha, vehiculo=vehiculo, conductor=conductor)
    if ayudante_ids:
        equipo.ayudantes.set(Ayudante.objects.filter(pk__in=ayudante_ids, activo=True))
    if conductor_ayudante_ids:
        equipo.conductores_ayudantes.set(
            Conductor.objects.filter(pk__in=conductor_ayudante_ids, activo=True)
        )

    return JsonResponse({
        "status": "ok",
        "warnings": warnings,
        "equipo": {
            "id": equipo.id,
            "placa": vehiculo.placa,
            "conductor": conductor.nombre,
            "ayudantes": [a.nombre for a in equipo.ayudantes.all()],
            "conductores_ayudantes": [
                c.nombre for c in equipo.conductores_ayudantes.all()
            ],
            "fecha_iso": fecha.strftime("%Y-%m-%d"),
        },
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def api_crear_programacion_pizarra(request):
    from decimal import Decimal, InvalidOperation
    from django.db import transaction
    from django.db.models import Q
    from apps.clientes.models import Cliente as ClienteModel
    from apps.servicios.models import Servicio as ServicioModel, SERVICIO_PROGRAMADO

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    equipo_id = data.get("equipo_id")
    fecha_str = data.get("fecha")
    hora_str = data.get("hora")
    duracion = data.get("duracion", 1)
    nombre = (data.get("nombre") or "").strip()
    telefono = (data.get("telefono") or "").strip()
    documento = (data.get("documento") or "").strip()
    correo = (data.get("correo") or "").strip()
    ruc = (data.get("ruc") or "").strip()
    razon_social = (data.get("razon_social") or "").strip()
    monto_str = data.get("precio", "")
    tipo_comprobante = (data.get("tipo_comprobante") or "ninguno").strip()
    origen = (data.get("origen") or "").strip()
    destino = (data.get("destino") or "").strip()
    piso_origen = (data.get("piso_origen") or "").strip()
    piso_destino = (data.get("piso_destino") or "").strip()
    acceso_origen = data.get("acceso_origen") or []
    acceso_destino = data.get("acceso_destino") or []
    detalle_carga = (data.get("detalle_carga") or "").strip()
    tipo_embalaje = (data.get("tipo_embalaje") or "sin_embalaje").strip()
    requisitos = data.get("requisitos") or []
    observaciones = (data.get("observaciones") or "").strip()

    if not nombre or not telefono or not origen or not destino:
        return JsonResponse(
            {"error": "Nombre, teléfono, origen y destino son requeridos"}, status=400
        )

    equipo = get_object_or_404(EquipoDia, pk=equipo_id)

    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        hora_inicio = datetime.strptime(hora_str, "%H:%M").time()
        duracion_h = float(duracion)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Fecha, hora o duración inválida"}, status=400)

    try:
        monto = Decimal(str(monto_str)) if monto_str else Decimal("0")
    except InvalidOperation:
        monto = Decimal("0")

    ini_dt = datetime.combine(fecha, hora_inicio)
    hora_fin = (ini_dt + timedelta(hours=duracion_h)).time()

    from django.db.models import Q as DQ
    conflictos = ProgramacionServicio.objects.filter(
        equipo_dia=equipo, fecha=fecha,
    ).filter(
        DQ(hora_fin__isnull=True) | DQ(hora_fin__gt=hora_inicio)
    ).filter(hora_inicio__lt=hora_fin)

    if conflictos.exists():
        c = conflictos.first()
        codigo = c.servicio.codigo if c.servicio else 'otra reserva'
        return JsonResponse(
            {"error": f"Conflicto con {codigo} ({c.hora_inicio}–{c.hora_fin or '?'})"},
            status=409,
        )

    with transaction.atomic():
        cliente_defaults = {"nombre": nombre}
        if documento:
            cliente_defaults["documento"] = documento
        if correo:
            cliente_defaults["correo"] = correo
        if ruc:
            cliente_defaults["ruc"] = ruc
        if razon_social:
            cliente_defaults["razon_social"] = razon_social
        cliente, created = ClienteModel.objects.get_or_create(
            telefono=telefono, defaults=cliente_defaults,
        )
        if not created:
            upd = []
            if not cliente.nombre and nombre:
                cliente.nombre = nombre; upd.append("nombre")
            if documento and not cliente.documento:
                cliente.documento = documento; upd.append("documento")
            if correo and not cliente.correo:
                cliente.correo = correo; upd.append("correo")
            if ruc and not cliente.ruc:
                cliente.ruc = ruc; upd.append("ruc")
            if razon_social and not cliente.razon_social:
                cliente.razon_social = razon_social; upd.append("razon_social")
            if upd:
                cliente.save(update_fields=upd)

        servicio = ServicioModel.objects.create(
            cliente=cliente,
            estado=SERVICIO_PROGRAMADO,
            precio=monto if monto else None,
            fecha_servicio=fecha,
            horario_servicio=hora_str,
            direccion_origen=origen,
            direccion_destino=destino,
            piso_origen=piso_origen,
            piso_destino=piso_destino,
            acceso_origen_opciones=acceso_origen if isinstance(acceso_origen, list) else [],
            acceso_destino_opciones=acceso_destino if isinstance(acceso_destino, list) else [],
            detalle_carga=detalle_carga,
            tipo_embalaje=tipo_embalaje if tipo_embalaje in dict(ServicioModel.TIPO_EMBALAJE_CHOICES) else "sin_embalaje",
            requisitos_especiales=requisitos if isinstance(requisitos, list) else [],
            tipo_comprobante=tipo_comprobante if tipo_comprobante in dict(ServicioModel.TIPO_COMPROBANTE_CHOICES) else "ninguno",
            observaciones=observaciones,
        )

        ps = ProgramacionServicio.objects.create(
            servicio=servicio,
            equipo_dia=equipo,
            vehiculo=equipo.vehiculo,
            conductor=equipo.conductor,
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            monto=monto,
            estado_operativo=ProgramacionServicio.ESTADO_PROGRAMADO,
        )
        ps.ayudantes.set(equipo.ayudantes.all())

    return JsonResponse({"status": "ok", "ps_id": ps.id, "servicio_codigo": servicio.codigo})


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def api_mover_programacion_pizarra(request):
    from django.db.models import Q as DQ

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    try:
        ps = ProgramacionServicio.objects.select_related("servicio").get(pk=data.get("ps_id"))
    except (ProgramacionServicio.DoesNotExist, TypeError, ValueError):
        return JsonResponse({"error": "Programación no encontrada"}, status=404)
    try:
        equipo = EquipoDia.objects.get(pk=data.get("equipo_id"))
    except (EquipoDia.DoesNotExist, TypeError, ValueError):
        return JsonResponse({"error": "Equipo no encontrado"}, status=404)

    try:
        nueva_fecha = datetime.strptime(data.get("fecha"), "%Y-%m-%d").date()
        nueva_hora = datetime.strptime(data.get("hora"), "%H:%M").time()
    except (ValueError, TypeError):
        return JsonResponse({"error": "Fecha u hora inválida"}, status=400)

    if ps.hora_fin:
        dur = (
            datetime.combine(ps.fecha, ps.hora_fin)
            - datetime.combine(ps.fecha, ps.hora_inicio)
        )
        nueva_hora_fin = (datetime.combine(nueva_fecha, nueva_hora) + dur).time()
    else:
        nueva_hora_fin = None

    qs_conflict = ProgramacionServicio.objects.filter(
        equipo_dia=equipo, fecha=nueva_fecha,
    ).exclude(pk=ps.pk).filter(
        DQ(hora_fin__isnull=True) | DQ(hora_fin__gt=nueva_hora)
    )
    if nueva_hora_fin:
        qs_conflict = qs_conflict.filter(hora_inicio__lt=nueva_hora_fin)

    if qs_conflict.exists():
        c = qs_conflict.first()
        codigo = c.servicio.codigo if c.servicio else 'otra reserva'
        return JsonResponse(
            {"error": f"Conflicto con {codigo} ({c.hora_inicio}–{c.hora_fin or '?'})"},
            status=409,
        )

    ps.equipo_dia = equipo
    ps.vehiculo = equipo.vehiculo
    ps.conductor = equipo.conductor
    ps.fecha = nueva_fecha
    ps.hora_inicio = nueva_hora
    ps.hora_fin = nueva_hora_fin
    ps.save(update_fields=["equipo_dia", "vehiculo", "conductor", "fecha", "hora_inicio", "hora_fin"])
    ps.ayudantes.set(equipo.ayudantes.all())

    return JsonResponse({"status": "ok"})


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def api_asignar_servicio_pizarra(request):
    from django.db import transaction
    from django.db.models import Q as DQ

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    servicio = get_object_or_404(Servicio, pk=data.get("servicio_id"))
    equipo = get_object_or_404(EquipoDia, pk=data.get("equipo_id"), activo=True)
    hora_inicio = _servicio_hora(servicio)

    if not servicio.fecha_servicio or not hora_inicio:
        return JsonResponse(
            {"error": "Reserva necesita fecha y hora antes de asignarla."},
            status=409,
        )
    if equipo.fecha != servicio.fecha_servicio:
        return JsonResponse(
            {"error": "Equipo y reserva deben pertenecer a la misma fecha."},
            status=409,
        )

    hora_fin = (
        datetime.combine(servicio.fecha_servicio, hora_inicio) + timedelta(hours=1)
    ).time()
    conflictos = ProgramacionServicio.objects.filter(
        equipo_dia=equipo,
        fecha=servicio.fecha_servicio,
    ).filter(
        DQ(hora_fin__isnull=True) | DQ(hora_fin__gt=hora_inicio),
        hora_inicio__lt=hora_fin,
    )
    if conflictos.exists():
        conflicto = conflictos.select_related("servicio").first()
        return JsonResponse(
            {
                "error": (
                    f"Conflicto con {conflicto.servicio.codigo} "
                    f"({conflicto.hora_inicio}–{conflicto.hora_fin or '?'})"
                )
            },
            status=409,
        )

    with transaction.atomic():
        if ProgramacionServicio.objects.select_for_update().filter(
            servicio=servicio,
        ).exists():
            return JsonResponse(
                {"error": "Reserva ya fue asignada o programada."},
                status=409,
            )
        programacion = ProgramacionServicio.objects.create(
            servicio=servicio,
            equipo_dia=equipo,
            vehiculo=equipo.vehiculo,
            conductor=equipo.conductor,
            fecha=servicio.fecha_servicio,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            monto=servicio.precio or Decimal("0"),
            estado_operativo=ProgramacionServicio.ESTADO_PROGRAMADO,
        )
        programacion.ayudantes.set(equipo.ayudantes.all())
        servicio.estado = SERVICIO_ASIGNADO
        servicio.save(update_fields=["estado"])

    return JsonResponse({"status": "ok", "ps_id": programacion.pk})


@login_required
def api_buscar_clientes(request):
    from django.db.models import Q as DQ
    from apps.clientes.models import Cliente as ClienteModel

    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"clientes": []})
    qs = ClienteModel.objects.filter(
        DQ(nombre__icontains=q) | DQ(telefono__icontains=q)
    ).values("id", "nombre", "telefono")[:10]
    return JsonResponse({"clientes": list(qs)})


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def api_eliminar_equipo_pizarra(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    equipo_id = data.get("equipo_id")
    try:
        equipo = EquipoDia.objects.get(pk=equipo_id)
    except EquipoDia.DoesNotExist:
        return JsonResponse({"error": "Equipo no encontrado"}, status=404)

    n_servicios = equipo.servicios.count()
    equipo.delete()  # SET_NULL on_delete: programaciones quedan con equipo_dia=NULL
    action = "desasignado" if n_servicios > 0 else "eliminado"
    return JsonResponse({"status": "ok", "action": action, "n_servicios": n_servicios})


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def api_actualizar_duracion(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    ps_id        = data.get("ps_id")
    hora_fin_str = data.get("hora_fin")
    duracion_raw = data.get("duracion")

    try:
        ps = ProgramacionServicio.objects.get(pk=ps_id)
    except (ProgramacionServicio.DoesNotExist, TypeError, ValueError):
        return JsonResponse({"error": "Programación no encontrada"}, status=404)

    inicio_dt = datetime.combine(ps.fecha, ps.hora_inicio)

    if hora_fin_str:
        try:
            hora_fin = datetime.strptime(hora_fin_str, "%H:%M").time()
        except ValueError:
            return JsonResponse({"error": "Formato de hora inválido (HH:MM)"}, status=400)
        fin_dt = datetime.combine(ps.fecha, hora_fin)
        if fin_dt <= inicio_dt:
            return JsonResponse({"error": "La hora fin debe ser posterior a la hora inicio"}, status=400)
    elif duracion_raw is not None:
        try:
            duracion = float(duracion_raw)
        except (ValueError, TypeError):
            return JsonResponse({"error": "Duración inválida"}, status=400)
        if duracion <= 0 or duracion > 24:
            return JsonResponse({"error": "Duración debe ser entre 0 y 24 horas"}, status=400)
        fin_dt = inicio_dt + timedelta(hours=duracion)
    else:
        return JsonResponse({"error": "Indica hora_fin o duracion"}, status=400)

    ps.hora_fin = fin_dt.time()
    ps.save(update_fields=["hora_fin"])

    return JsonResponse({
        "status": "ok",
        "hora_fin": fin_dt.strftime("%H:%M"),
    })


@login_required
@role_required("Administrador", "Supervisor", "Asesor de Ventas")
@require_http_methods(["POST"])
def api_cambiar_estado(request):
    try:
        data = json.loads(request.body)
        ps_pk = data.get("pk")
        nuevo_estado = data.get("estado")
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    estados_validos = {k for k, _ in ESTADOS_SERVICIO}
    if nuevo_estado not in estados_validos:
        return JsonResponse({"error": f"Estado inválido: {nuevo_estado}"}, status=400)

    ps = get_object_or_404(
        ProgramacionServicio.objects.select_related("servicio"),
        pk=ps_pk,
    )
    if not ps.servicio:
        return JsonResponse({"error": "La programación no tiene servicio asociado"}, status=400)

    ps.servicio.estado = nuevo_estado
    ps.servicio.save(update_fields=["estado"])

    op_estado = ESTADO_A_OPERATIVO.get(nuevo_estado, ProgramacionServicio.ESTADO_PROGRAMADO)
    ps.estado_operativo = op_estado
    ps.save(update_fields=["estado_operativo"])

    return JsonResponse({
        "status": "ok",
        "servicio_estado": nuevo_estado,
        "operativo_estado": op_estado,
    })
