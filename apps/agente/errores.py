"""Errores del catálogo de capacidades.

Solo se usan dentro de `apps/agente`. El wrapper `registro.ejecutar` los traduce
a un `ResultadoCapacidad` con `codigo_error`; el cuerpo de una capacidad los
lanza y no atrapa nada.
"""


class CapacidadError(Exception):
    """Base — no lanzar directamente, usar una subclase."""

    codigo = "error"


class PerfilNoAutorizado(CapacidadError):
    """El perfil del Principal no puede usar esta capacidad (o esta variante)."""

    codigo = "perfil_no_autorizado"


class FueraDeAlcance(CapacidadError):
    """El objeto pedido existe pero este Principal no puede verlo/tocarlo."""

    codigo = "fuera_de_alcance"


class NoEncontrado(CapacidadError):
    """El objeto pedido no existe (o no existe dentro del alcance del Principal)."""

    codigo = "no_encontrado"


class ArgInvalido(CapacidadError):
    """Un argumento de entrada es inválido (formato, rango, faltante)."""

    codigo = "arg_invalido"
