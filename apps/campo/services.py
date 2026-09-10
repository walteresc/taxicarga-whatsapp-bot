"""Capa de servicio del módulo Campo.

- Personal (conductores / ayudantes): querysets de solo lectura, compartidos por
  el panel viejo (Django) y la API v2 (Vue).
- Pizarra: asignar / mover / desasignar una `ProgramacionServicio`. Extraído de
  `apps/campo/api/views.py::PizarraMutationView` sin cambiar comportamiento — la
  vista delega acá y el catálogo de capacidades del agente (`apps/agente`)
  también. Los `apps/campo/tests/test_pizarra*` son el contrato.
"""
from datetime import datetime, timedelta

from django.db import models

from apps.api.filters import apply_active_filter, apply_ordering, apply_search
from apps.campo.models import Ayudante, Conductor
from apps.servicios.models import Servicio
from apps.servicios.utils import parse_horario

_DRIVER_ORDERING = {
    "name": "nombre", "documentId": "dni", "licenseExpiresOn": "fecha_vencimiento_licencia",
    "active": "activo",
}
_ASSISTANT_ORDERING = {"name": "nombre", "documentId": "dni", "active": "activo"}


def drivers_queryset(params):
    qs = Conductor.objects.select_related("usuario").all()
    qs = apply_search(qs, params.get("search"), ("nombre", "dni", "telefono", "numero_licencia"))
    qs = apply_active_filter(qs, params.get("status"))
    qs = apply_ordering(qs, params.get("ordering"), _DRIVER_ORDERING, ("nombre", "id"))
    return qs


def assistants_queryset(params):
    qs = Ayudante.objects.select_related("usuario").all()
    qs = apply_search(qs, params.get("search"), ("nombre", "dni", "telefono"))
    qs = apply_active_filter(qs, params.get("status"))
    qs = apply_ordering(qs, params.get("ordering"), _ASSISTANT_ORDERING, ("nombre", "id"))
    return qs


# --------------------------------------------------------------------------- #
#  Pizarra
# --------------------------------------------------------------------------- #

class PizarraError(Exception):
    """Conflicto de horario, servicio ya asignado, o falta fecha/hora.

    `.status` sugiere el código HTTP para la vista (409 por defecto)."""

    def __init__(self, mensaje, *, status=409):
        super().__init__(mensaje)
        self.status = status


def resolver_recurso(resource_id):
    """'v<id>' → campo.Vehiculo · 't<id>' → tercerizacion.TransportistaVehiculo."""
    from apps.campo.models import Vehiculo
    from apps.tercerizacion.models import TransportistaVehiculo
    if not resource_id or len(resource_id) < 2:
        return None
    prefijo, resto = resource_id[0], resource_id[1:]
    try:
        pk = int(resto)
    except ValueError:
        return None
    try:
        if prefijo == "v":
            return Vehiculo.objects.get(pk=pk)
        if prefijo == "t":
            return TransportistaVehiculo.objects.select_related("transportista").get(pk=pk)
    except (Vehiculo.DoesNotExist, TransportistaVehiculo.DoesNotExist):
        return None
    return None


def es_tv(obj):
    from apps.tercerizacion.models import TransportistaVehiculo
    return isinstance(obj, TransportistaVehiculo)


def hay_conflicto(recurso, fecha, hora_ini, hora_fin, exclude_id=None):
    from apps.campo.models import ProgramacionServicio
    qs = ProgramacionServicio.objects.filter(fecha=fecha).exclude(estado_operativo="cancelado")
    qs = qs.filter(transportista_vehiculo=recurso) if es_tv(recurso) else qs.filter(vehiculo=recurso)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    qs = qs.filter(models.Q(hora_fin__isnull=True) | models.Q(hora_fin__gt=hora_ini))
    if hora_fin:
        qs = qs.filter(hora_inicio__lt=hora_fin)
    return qs.select_related("servicio").first()


def fila_conductor(tv, fecha):
    from apps.campo.models import FilaPizarraTransportista
    fila = FilaPizarraTransportista.objects.filter(fecha=fecha, transportista_vehiculo=tv).first()
    return fila.conductor_externo if fila else ""


def set_modalidad(servicio, modalidad):
    if servicio.modalidad_ejecucion != modalidad:
        servicio.modalidad_ejecucion = modalidad
        servicio.save(update_fields=["modalidad_ejecucion"])


def _choca_msg(c):
    return f"Choca con {c.servicio.codigo if c.servicio else 'otra'} ({c.hora_inicio:%H:%M})"


def asignar_servicio(servicio, recurso, *, hora_inicio=None, hora_fin=None,
                     conductor=None, conductor_externo="", actor=None):
    """Crea la `ProgramacionServicio` de `servicio` sobre `recurso` (Vehiculo o
    TransportistaVehiculo). Si el recurso es de transportista, marca el servicio
    como tercerizado. Lanza `PizarraError` en conflicto / datos faltantes."""
    from apps.campo.models import ProgramacionServicio

    if ProgramacionServicio.objects.filter(servicio=servicio).exclude(
        estado_operativo="cancelado").exists():
        raise PizarraError("El servicio ya está asignado.")

    hora_ini = hora_inicio or parse_horario(servicio.horario_servicio)
    if not servicio.fecha_servicio or not hora_ini:
        raise PizarraError("El servicio necesita fecha y hora.")
    if hora_fin is None:
        hora_fin = (datetime.combine(servicio.fecha_servicio, hora_ini) + timedelta(hours=1)).time()

    c = hay_conflicto(recurso, servicio.fecha_servicio, hora_ini, hora_fin)
    if c:
        raise PizarraError(_choca_msg(c))

    if es_tv(recurso):
        cond_ext = (conductor_externo or "").strip() or fila_conductor(recurso, servicio.fecha_servicio)
        ps = ProgramacionServicio.objects.create(
            servicio=servicio, vehiculo=None,
            transportista=recurso.transportista, transportista_vehiculo=recurso,
            conductor_externo=cond_ext,
            fecha=servicio.fecha_servicio, hora_inicio=hora_ini, hora_fin=hora_fin,
            monto=servicio.precio or 0,
        )
        set_modalidad(servicio, Servicio.MODALIDAD_TERCERIZADO)
    else:
        ps = ProgramacionServicio.objects.create(
            servicio=servicio, vehiculo=recurso, conductor=conductor,
            fecha=servicio.fecha_servicio, hora_inicio=hora_ini, hora_fin=hora_fin,
            monto=servicio.precio or 0,
        )
    return ps


def mover_programacion(ps, destino, *, hora_inicio=None, actor=None):
    """Mueve una `ProgramacionServicio` a otro recurso y/u otra hora. Permite
    cualquier par propio↔tercerizado y ajusta `modalidad_ejecucion`."""
    if destino is None:
        destino = ps.transportista_vehiculo or ps.vehiculo

    hora_ini = hora_inicio or ps.hora_inicio
    dur = timedelta(hours=1)
    if ps.hora_fin:
        dur = datetime.combine(ps.fecha, ps.hora_fin) - datetime.combine(ps.fecha, ps.hora_inicio)
    hora_fin = (datetime.combine(ps.fecha, hora_ini) + dur).time()

    c = hay_conflicto(destino, ps.fecha, hora_ini, hora_fin, exclude_id=ps.pk)
    if c:
        raise PizarraError(_choca_msg(c))

    fields = ["hora_inicio", "hora_fin"]
    ps.hora_inicio = hora_ini
    ps.hora_fin = hora_fin
    if es_tv(destino):
        ps.vehiculo = None
        ps.conductor = None
        ps.transportista = destino.transportista
        ps.transportista_vehiculo = destino
        ps.conductor_externo = fila_conductor(destino, ps.fecha)
        nueva_mod = Servicio.MODALIDAD_TERCERIZADO
    else:
        ps.transportista = None
        ps.transportista_vehiculo = None
        ps.conductor_externo = ""
        ps.vehiculo = destino
        nueva_mod = Servicio.MODALIDAD_PROPIO
    fields += ["vehiculo", "conductor", "transportista", "transportista_vehiculo", "conductor_externo"]
    ps.save(update_fields=fields)
    set_modalidad(ps.servicio, nueva_mod)
    return ps


def desasignar(ps):
    ps.delete()
