"""Capacidades de operación: asignar en la Pizarra, registrar pago."""
from datetime import datetime

from apps.agente.errores import ArgInvalido
from apps.agente.registro import EFECTO_CRITICO, EFECTO_REVERSIBLE, capacidad

from . import _alcance


def _hora(v):
    if not v:
        return None
    try:
        return datetime.strptime(v, "%H:%M").time()
    except (ValueError, TypeError):
        raise ArgInvalido(f"Hora inválida: {v!r} (formato HH:MM).")


@capacidad("asignar", perfiles=["asesor", "sistema"], efecto=EFECTO_CRITICO)
def asignar(principal, reserva_codigo, recurso, hora_inicio=None, hora_fin=None,
           conductor_id=None, conductor_externo=""):
    """Asigna una reserva a un recurso de la Pizarra. `recurso`: 'v<id>' (vehículo
    propio) o 't<id>' (vehículo de transportista)."""
    from apps.campo.models import Conductor
    from apps.campo.services import asignar_servicio, es_tv, resolver_recurso

    svc = _alcance.reserva_para(principal, reserva_codigo)
    rec = resolver_recurso(recurso)
    if rec is None:
        raise ArgInvalido(f"Recurso no encontrado: {recurso!r}.")
    conductor = None
    if conductor_id and not es_tv(rec):
        conductor = Conductor.objects.filter(pk=conductor_id).first()
    ps = asignar_servicio(
        svc, rec, hora_inicio=_hora(hora_inicio), hora_fin=_hora(hora_fin),
        conductor=conductor, conductor_externo=conductor_externo, actor=principal.user,
    )
    return {"programacion_id": ps.id, "reserva": svc.codigo, "_servicio": svc,
            "_lead": svc.lead_origen}


@capacidad("desasignar", perfiles=["asesor", "sistema"], efecto=EFECTO_REVERSIBLE)
def desasignar(principal, programacion_id):
    """Quita una asignación de la Pizarra."""
    from apps.campo.models import ProgramacionServicio
    from apps.campo.services import desasignar as _des

    ps = ProgramacionServicio.objects.select_related("servicio").filter(pk=programacion_id).first()
    if ps is None:
        from apps.agente.errores import NoEncontrado
        raise NoEncontrado(f"No se encontró la programación {programacion_id}.")
    svc = ps.servicio
    _des(ps)
    return {"ok": True, "_servicio": svc}


@capacidad("registrar_pago", perfiles=["asesor", "sistema"], efecto=EFECTO_CRITICO)
def registrar_pago(principal, reserva_codigo, concepto, metodo_pago, monto):
    """Registra un pago de una reserva."""
    from apps.servicios.services import registrar_pago as _pago

    svc = _alcance.reserva_para(principal, reserva_codigo)
    pago = _pago(svc, concepto=concepto, metodo_pago=metodo_pago, monto=monto, usuario=principal.user)
    return {"pago_id": pago.id, "reserva": svc.codigo, "monto": float(pago.monto),
            "_servicio": svc}
