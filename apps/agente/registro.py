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


def capacidad(nombre: str, *, perfiles, efecto: str):
    perfiles = frozenset(perfiles)
    if not perfiles or (perfiles - _PERFILES_VALIDOS):
        raise ValueError(f"Perfiles inválidos para '{nombre}': {perfiles}")
    if efecto not in _EFECTOS:
        raise ValueError(f"Efecto inválido para '{nombre}': {efecto}")

    def deco(fn):
        if nombre in _REGISTRO:
            raise ValueError(f"Capacidad duplicada: '{nombre}'")
        doc = (fn.__doc__ or "").strip().splitlines()
        _REGISTRO[nombre] = Capacidad(
            nombre=nombre, fn=fn, perfiles=perfiles, efecto=efecto,
            descripcion=(doc[0].strip() if doc else ""),
        )
        return fn

    return deco


def catalogo() -> list[Capacidad]:
    return sorted(_REGISTRO.values(), key=lambda c: (c.efecto, c.nombre))


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
