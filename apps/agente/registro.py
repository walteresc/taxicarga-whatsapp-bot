"""Catálogo de capacidades del agente.

Una **capacidad** = una cosa que el agente puede hacer. Se declara con el
decorador `@capacidad(...)`. `ejecutar(nombre, principal, **args)` es el único
punto de entrada: valida el perfil, corre el cuerpo, traduce errores conocidos y
deja siempre una fila en `AccionAgente`.

El cuerpo de una capacidad:
  - recibe `(principal: Principal, **args)`
  - revalida el alcance (lanza `PerfilNoAutorizado` / `FueraDeAlcance` / `NoEncontrado`)
  - llama a una función de servicio que YA existe
  - devuelve un `dict` serializable (los `datos`), o lanza
  - NO atrapa excepciones ni escribe auditoría — de eso se encarga `ejecutar`
"""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404

from .errores import CapacidadError

EFECTO_LECTURA = "lectura"
EFECTO_REVERSIBLE = "escritura_reversible"
EFECTO_CRITICO = "escritura_critica"
_EFECTOS = {EFECTO_LECTURA, EFECTO_REVERSIBLE, EFECTO_CRITICO}

_PERFILES_VALIDOS = {"asesor", "transportista", "cliente", "sistema"}


@dataclass(frozen=True)
class Capacidad:
    nombre: str
    fn: object
    perfiles: frozenset
    efecto: str
    descripcion: str
    params: dict  # {arg: {type, description, required?, enum?}}

    def esquema_openai(self) -> dict:
        props, requeridos = {}, []
        for arg, spec in self.params.items():
            campo = {"type": spec.get("type", "string")}
            if spec.get("description"):
                campo["description"] = spec["description"]
            if spec.get("enum"):
                campo["enum"] = list(spec["enum"])
            props[arg] = campo
            if spec.get("required"):
                requeridos.append(arg)
        return {
            "type": "function",
            "name": self.nombre,
            "description": self.descripcion,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": requeridos,
                "additionalProperties": False,
            },
            "strict": False,
        }


def _derivar_params(fn):
    """Esquema mínimo a partir de la firma: nombres, required = sin default,
    tipo string salvo default int/bool."""
    out = {}
    for nombre, p in inspect.signature(fn).parameters.items():
        if nombre == "principal" or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        tipo = "string"
        if isinstance(p.default, bool):
            tipo = "boolean"
        elif isinstance(p.default, int):
            tipo = "integer"
        out[nombre] = {"type": tipo, "required": p.default is inspect.Parameter.empty}
    return out


@dataclass
class ResultadoCapacidad:
    ok: bool
    datos: dict | None = None
    error: str = ""
    codigo_error: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "datos": self.datos,
            "error": self.error or None,
            "codigo_error": self.codigo_error or None,
        }


_REGISTRO: dict[str, Capacidad] = {}


def capacidad(nombre: str, *, perfiles, efecto: str, params: dict | None = None):
    perfiles = frozenset(perfiles)
    if not perfiles or (perfiles - _PERFILES_VALIDOS):
        raise ValueError(f"Perfiles inválidos para '{nombre}': {perfiles}")
    if efecto not in _EFECTOS:
        raise ValueError(f"Efecto inválido para '{nombre}': {efecto}")

    def deco(fn):
        if nombre in _REGISTRO:
            raise ValueError(f"Capacidad duplicada: '{nombre}'")
        doc = (fn.__doc__ or "").strip().splitlines()
        descripcion = " ".join(l.strip() for l in doc[:3]).strip() if doc else nombre
        esquema = dict(_derivar_params(fn))
        for arg, spec in (params or {}).items():
            esquema.setdefault(arg, {})
            esquema[arg] = {**esquema[arg], **spec}
        _REGISTRO[nombre] = Capacidad(
            nombre=nombre, fn=fn, perfiles=perfiles, efecto=efecto,
            descripcion=descripcion, params=esquema,
        )
        return fn

    return deco


def catalogo() -> list[Capacidad]:
    return sorted(_REGISTRO.values(), key=lambda c: (c.efecto, c.nombre))


def herramientas_para(principal_tipo: str) -> list[dict]:
    """Specs OpenAI de las capacidades que ese perfil puede usar."""
    return [
        c.esquema_openai() for c in catalogo()
        if principal_tipo in c.perfiles
    ]


def _recortar(valor, _prof=0):
    """Recorta un resultado para guardarlo en auditoría (sin volcados enormes)."""
    if _prof > 4:
        return "…"
    if isinstance(valor, dict):
        return {k: _recortar(v, _prof + 1) for k, v in list(valor.items())[:40]}
    if isinstance(valor, (list, tuple)):
        return [_recortar(v, _prof + 1) for v in valor[:20]]
    if isinstance(valor, str):
        return valor if len(valor) <= 500 else valor[:500] + "…"
    return valor


def ejecutar(nombre: str, principal, **args) -> ResultadoCapacidad:
    from .models import AccionAgente

    cap = _REGISTRO.get(nombre)
    if cap is None:
        return ResultadoCapacidad(ok=False, error=f"Capacidad desconocida: {nombre}.",
                                  codigo_error="no_encontrado")

    if principal.tipo not in cap.perfiles:
        res = ResultadoCapacidad(
            ok=False, codigo_error="perfil_no_autorizado",
            error=f"El perfil '{principal.tipo}' no puede usar '{nombre}'.",
        )
        _auditar(AccionAgente, cap, principal, args, res, lead=None, servicio=None)
        return res

    lead = servicio = None
    try:
        datos = cap.fn(principal, **args) or {}
        lead = datos.pop("_lead", None) if isinstance(datos, dict) else None
        servicio = datos.pop("_servicio", None) if isinstance(datos, dict) else None
        res = ResultadoCapacidad(ok=True, datos=datos)
    except CapacidadError as e:
        res = ResultadoCapacidad(ok=False, error=str(e) or e.codigo, codigo_error=e.codigo)
    except Http404:
        res = ResultadoCapacidad(ok=False, error="No se encontró.", codigo_error="no_encontrado")
    except DjangoValidationError as e:
        msg = "; ".join(e.messages) if hasattr(e, "messages") else str(e)
        res = ResultadoCapacidad(ok=False, error=msg, codigo_error="regla_negocio")
    except _reglas_negocio() as e:
        res = ResultadoCapacidad(ok=False, error=str(e), codigo_error="regla_negocio")
    except TypeError as e:
        # firma incorrecta (arg de más/menos) — error del que llama, no 500
        res = ResultadoCapacidad(ok=False, error=str(e), codigo_error="arg_invalido")

    _auditar(AccionAgente, cap, principal, args, res, lead=lead, servicio=servicio)
    return res


def _reglas_negocio():
    """Excepciones de reglas de negocio de las capas de servicio."""
    from apps.tercerizacion.adjudicacion import AdjudicacionError
    from apps.tercerizacion.negociacion import NegociacionError
    try:
        from apps.campo.services import PizarraError
    except Exception:
        PizarraError = type("PizarraError", (Exception,), {})
    return (NegociacionError, AdjudicacionError, PizarraError)


def _auditar(AccionAgente, cap, principal, args, res, *, lead, servicio):
    AccionAgente.objects.create(
        principal_tipo=principal.tipo,
        usuario=getattr(principal, "user", None) if getattr(principal, "user", None)
        and getattr(principal.user, "pk", None) else None,
        capacidad=cap.nombre,
        efecto=cap.efecto,
        args=_recortar(_jsonable(args)),
        ok=res.ok,
        codigo_error=res.codigo_error,
        error=res.error,
        resultado=_recortar(_jsonable(res.datos or {})),
        lead=lead if getattr(lead, "pk", None) else None,
        servicio=servicio if getattr(servicio, "pk", None) else None,
    )


def _jsonable(valor):
    try:
        json.dumps(valor, default=str)
        return valor
    except (TypeError, ValueError):
        return json.loads(json.dumps(valor, default=str))
