"""El orquestador (Capa 2): loop LLM que decide qué capacidades llamar.

- lectura + escritura_reversible → se ejecutan y el resultado vuelve al modelo.
- escritura_critica → se crea una `PropuestaAccion` pendiente; el modelo recibe
  "esperando confirmación humana" y NO se ejecuta nada.
Cada turno del modelo se persiste en `TurnoAgente`; cada tool en `AccionAgente`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from django.utils import timezone

from apps.ia.providers import build_provider

from . import registro
from .models import ConversacionAgente, PropuestaAccion, TurnoAgente
from .principal import principal_desde_usuario
from .prompts import system_prompt
from .registro import EFECTO_CRITICO


@dataclass
class RespuestaAgente:
    texto: str
    ejecutadas: list = field(default_factory=list)
    propuestas: list = field(default_factory=list)
    iteraciones: int = 0
    conversacion_id: int | None = None

    def as_dict(self):
        return asdict(self)


_RESUMEN_TPL = {
    "crear_reserva": "Crear la reserva de la carga {codigo}.",
    "cerrar_precio": "Cerrar el precio de {codigo} en S/ {monto} y crear la reserva.",
    "derivar_a_tercerizacion": "Derivar {codigo} a tercerización (modo de precio: {modo_precio}).",
    "publicar_a_transportistas": "Publicar {publicacion_codigo} a los transportistas.",
    "adjudicar": "Adjudicar {publicacion_codigo} a la oferta {oferta_id}.",
    "registrar_pago": "Registrar un pago de S/ {monto} ({concepto}) en {reserva_codigo}.",
    "enviar_whatsapp": "Enviar un WhatsApp al cliente de {carga_codigo}.",
    "encolar_revision_whatsapp": "Enviar por WhatsApp la última revisión de {cotizacion_codigo}.",
}


def _resumen(nombre, args):
    tpl = _RESUMEN_TPL.get(nombre)
    if tpl:
        try:
            return tpl.format(**{k: args.get(k, "?") for k in _campos(tpl)})
        except Exception:
            pass
    return f"{nombre}({', '.join(f'{k}={v}' for k, v in args.items())})"


def _campos(tpl):
    import string
    return [f for _, f, _, _ in string.Formatter().parse(tpl) if f]


class Orquestador:
    MAX_ITER = 6
    HISTORIA_TURNOS = 12
    MAX_OUTPUT_TOKENS = 1400

    def __init__(self, principal, conversacion=None):
        self.principal = principal
        self.conversacion = conversacion
        self.provider = build_provider("copilot")

    # -- API pública --------------------------------------------------------- #

    def responder(self, mensaje_usuario: str) -> RespuestaAgente:
        conv = self._asegurar_conversacion(mensaje_usuario)
        TurnoAgente.objects.create(conversacion=conv, rol=TurnoAgente.ROL_USUARIO,
                                   contenido=mensaje_usuario)

        messages = self._construir_mensajes(conv, mensaje_usuario)
        tools = registro.herramientas_para(self.principal.tipo)

        ejecutadas, propuestas, tool_calls_log = [], [], []
        tokens_in = tokens_out = 0
        texto = ""
        it = 0
        for it in range(1, self.MAX_ITER + 1):
            resp = self.provider.generar_con_tools(
                messages, tools, max_output_tokens=self.MAX_OUTPUT_TOKENS,
            )
            usage = getattr(resp, "usage", None)
            tokens_in += getattr(usage, "input_tokens", 0) or 0
            tokens_out += getattr(usage, "output_tokens", 0) or 0

            calls = [o for o in (resp.output or []) if getattr(o, "type", None) == "function_call"]
            if not calls:
                texto = (getattr(resp, "output_text", "") or "").strip()
                break

            messages += [o.model_dump() if hasattr(o, "model_dump") else o for o in resp.output]
            for call in calls:
                salida, registro_call = self._resolver_call(call, conv, ejecutadas, propuestas)
                tool_calls_log.append(registro_call)
                messages.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(salida, ensure_ascii=False, default=str),
                })
        else:
            texto = ("Perdón, no pude completar la consulta en los pasos disponibles. "
                     "¿Podés reformularla o pedir que te contacte un asesor?")

        TurnoAgente.objects.create(
            conversacion=conv, rol=TurnoAgente.ROL_AGENTE, contenido=texto,
            tool_calls=tool_calls_log, iteraciones=it,
            tokens_in=tokens_in or None, tokens_out=tokens_out or None,
        )
        conv.save(update_fields=["actualizado_en"])
        return RespuestaAgente(
            texto=texto, ejecutadas=ejecutadas, propuestas=propuestas,
            iteraciones=it, conversacion_id=conv.id,
        )

    # -- internos ---------------------------------------------------------- #

    def _asegurar_conversacion(self, primer_mensaje):
        if self.conversacion:
            return self.conversacion
        titulo = " ".join(primer_mensaje.split()[:10])[:120]
        self.conversacion = ConversacionAgente.objects.create(
            usuario=getattr(self.principal, "user", None) if getattr(self.principal, "user", None)
            and getattr(self.principal.user, "pk", None) else None,
            principal_tipo=self.principal.tipo, titulo=titulo,
        )
        return self.conversacion

    def _construir_mensajes(self, conv, mensaje_nuevo):
        msgs = [{"role": "system", "content": system_prompt(self.principal.tipo)}]
        turnos = list(conv.turnos.order_by("-creado_en")[: self.HISTORIA_TURNOS + 1])
        turnos.reverse()
        for t in turnos:
            if t.rol == TurnoAgente.ROL_USUARIO and t.contenido == mensaje_nuevo and t is turnos[-1]:
                continue
            role = "user" if t.rol == TurnoAgente.ROL_USUARIO else "assistant"
            if t.contenido:
                msgs.append({"role": role, "content": t.contenido})
        msgs.append({"role": "user", "content": mensaje_nuevo})
        return msgs

    def _resolver_call(self, call, conv, ejecutadas, propuestas):
        nombre = call.name
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "error": "Argumentos no válidos."}, {"capacidad": nombre, "ok": False}

        cap = registro._REGISTRO.get(nombre)
        if cap is None or self.principal.tipo not in cap.perfiles:
            return (
                {"ok": False, "error": f"No podés usar '{nombre}'."},
                {"capacidad": nombre, "ok": False, "codigo_error": "perfil_no_autorizado"},
            )

        if cap.efecto == EFECTO_CRITICO:
            prop = PropuestaAccion.objects.create(
                conversacion=conv,
                usuario=getattr(self.principal, "user", None) if getattr(self.principal, "user", None)
                and getattr(self.principal.user, "pk", None) else None,
                capacidad=nombre, efecto=cap.efecto, args=args,
                resumen=_resumen(nombre, args),
            )
            propuestas.append({"id": prop.id, "capacidad": nombre, "resumen": prop.resumen})
            return (
                {"propuesta_creada": prop.id, "estado": "pendiente_confirmacion_humana",
                 "resumen": prop.resumen},
                {"capacidad": nombre, "propuesta_id": prop.id, "ok": True},
            )

        res = registro.ejecutar(nombre, self.principal, **args)
        ejecutadas.append({"capacidad": nombre, "ok": res.ok, "codigo_error": res.codigo_error or None})
        return res.as_dict(), {"capacidad": nombre, "ok": res.ok, "codigo_error": res.codigo_error or None}


# --------------------------------------------------------------------------- #
#  Propuestas
# --------------------------------------------------------------------------- #

def aplicar_propuesta(propuesta: PropuestaAccion, usuario):
    """Confirma una propuesta: la ejecuta como `usuario` y setea el estado."""
    from .errores import PerfilNoAutorizado
    from .principal import PrincipalNoResoluble
    from .registro import ResultadoCapacidad

    if propuesta.estado != PropuestaAccion.ESTADO_PENDIENTE:
        raise PerfilNoAutorizado(f"La propuesta ya está {propuesta.estado}.")
    try:
        principal = principal_desde_usuario(usuario)
    except PrincipalNoResoluble as e:
        raise PerfilNoAutorizado(str(e))

    res = registro.ejecutar(propuesta.capacidad, principal, **propuesta.args)
    propuesta.estado = (
        PropuestaAccion.ESTADO_APLICADA if res.ok else PropuestaAccion.ESTADO_RECHAZADA
    )
    if not res.ok:
        propuesta.motivo_rechazo = (res.error or "")[:200]
    propuesta.resuelta_por = usuario
    propuesta.resuelta_en = timezone.now()
    propuesta.resultado = res.datos or {"error": res.error}
    propuesta.save(update_fields=[
        "estado", "motivo_rechazo", "resuelta_por", "resuelta_en", "resultado",
    ])
    return res


def rechazar_propuesta(propuesta: PropuestaAccion, usuario, motivo=""):
    from .errores import PerfilNoAutorizado

    if propuesta.estado != PropuestaAccion.ESTADO_PENDIENTE:
        raise PerfilNoAutorizado(f"La propuesta ya está {propuesta.estado}.")
    propuesta.estado = PropuestaAccion.ESTADO_RECHAZADA
    propuesta.motivo_rechazo = (motivo or "")[:200]
    propuesta.resuelta_por = usuario
    propuesta.resuelta_en = timezone.now()
    propuesta.save(update_fields=["estado", "motivo_rechazo", "resuelta_por", "resuelta_en"])
    return propuesta
