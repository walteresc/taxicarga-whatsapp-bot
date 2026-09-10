"""El `Principal`: quién le está pidiendo algo al agente.

Se resuelve en el servidor desde la autenticación, NUNCA lo elige el modelo.
Misma fuente de verdad que las clases de permiso de la API v2.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from apps.api.permissions import carrier_for, customer_portal_for, puede_ver_margen, role_names

TIPO_ASESOR = "asesor"
TIPO_TRANSPORTISTA = "transportista"
TIPO_CLIENTE = "cliente"
TIPO_SISTEMA = "sistema"

# Roles de grupo que cuentan como "personal del CRM".
_ROLES_CRM = {
    "Administrador", "Gerencia", "Admin de sistema", "Supervisor",
    "Asesor de Ventas", "Despacho", "Finanzas",
}


class PrincipalNoResoluble(Exception):
    """El usuario autenticado no encaja en ningún perfil del agente."""


@dataclass(frozen=True)
class Principal:
    tipo: str
    user: object | None = None            # django User o None (sistema)
    carrier: object | None = None         # tercerizacion.Transportista
    cliente: object | None = None         # clientes.Cliente (del ClienteUsuario)
    cliente_usuario: object | None = None  # clientes.ClienteUsuario
    roles: tuple[str, ...] = field(default_factory=tuple)

    @property
    def es_interno(self) -> bool:
        return self.tipo in (TIPO_ASESOR, TIPO_SISTEMA)

    @property
    def es_externo(self) -> bool:
        return self.tipo in (TIPO_TRANSPORTISTA, TIPO_CLIENTE)

    def tiene_rol(self, *nombres) -> bool:
        return any(n in self.roles for n in nombres)

    def ve_margen(self) -> bool:
        if self.tipo == TIPO_SISTEMA:
            return True
        return bool(self.user) and puede_ver_margen(self.user)

    def __str__(self) -> str:
        who = getattr(self.user, "username", None) or "sistema"
        return f"Principal({self.tipo}:{who})"


def principal_sistema() -> Principal:
    """Para automatizaciones internas sin request (el futuro orquestador de fondo)."""
    return Principal(tipo=TIPO_SISTEMA)


def principal_desde_usuario(user) -> Principal:
    """Deriva el perfil del usuario autenticado.

    Precedencia (del más acotado al más amplio): transportista → cliente → asesor.
    Un usuario que fuera a la vez transportista y personal del CRM se trata como
    transportista (más restrictivo). Si no encaja en ninguno → PrincipalNoResoluble.
    """
    if not user or not getattr(user, "is_authenticated", False):
        raise PrincipalNoResoluble("Sin usuario autenticado.")

    carrier = carrier_for(user)
    if carrier is not None and carrier.activo:
        return Principal(tipo=TIPO_TRANSPORTISTA, user=user, carrier=carrier)

    cu = customer_portal_for(user)
    if cu is not None:
        return Principal(
            tipo=TIPO_CLIENTE, user=user, cliente=cu.cliente, cliente_usuario=cu,
        )

    roles = tuple(role_names(user))
    if user.is_superuser or (_ROLES_CRM & set(roles)):
        return Principal(tipo=TIPO_ASESOR, user=user, roles=roles)

    raise PrincipalNoResoluble(
        f"El usuario {user.username} no es transportista, ni cliente del portal, "
        "ni tiene un rol del CRM."
    )
