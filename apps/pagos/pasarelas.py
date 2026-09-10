"""Contrato de pasarela de pago + providers.

`FakeProvider` (default) permite probar todo el flujo sin credenciales.
`CulqiProvider` queda listo: se activa poniendo `PASARELA_PAGO=culqi` y las
llaves en el entorno. El resto del sistema solo habla con `PasarelaPago`.
"""
import hashlib
import hmac
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from django.conf import settings


@dataclass
class ResultadoCargo:
    ok: bool
    external_id: str = ""
    estado: str = "fallida"          # "pagada" | "fallida" | "procesando"
    mensaje: str = ""
    raw: dict = field(default_factory=dict)


class PasarelaPago(ABC):
    nombre = "abstract"

    @property
    def config_publica(self) -> dict:
        """Lo que necesita el frontend para montar el checkout (llave pública, etc.)."""
        return {"provider": self.nombre}

    @abstractmethod
    def crear_cargo(self, orden, *, source_token: str, email: str) -> ResultadoCargo:
        ...

    @abstractmethod
    def verificar_webhook(self, headers: dict, body: bytes) -> dict | None:
        """Devuelve el evento parseado si la firma es válida, o None."""

    @abstractmethod
    def parsear_evento(self, evento: dict) -> tuple[str, str] | None:
        """(external_id, estado) del evento, o None si no interesa."""


class FakeProvider(PasarelaPago):
    """Simula la pasarela. `source_token`:
      - "fail" / "tkn_fail"  → cargo rechazado
      - cualquier otra cosa  → cargo aprobado
    Webhook: acepta cualquier body JSON {external_id, status}.
    """
    nombre = "fake"

    def crear_cargo(self, orden, *, source_token, email):
        if (source_token or "").lower() in ("fail", "tkn_fail", "rechazar"):
            return ResultadoCargo(ok=False, estado="fallida", mensaje="Tarjeta rechazada (simulado).")
        cid = f"fake_chg_{orden.token[:12]}"
        return ResultadoCargo(ok=True, external_id=cid, estado="pagada", mensaje="Aprobado (simulado).",
                              raw={"id": cid, "amount": float(orden.monto), "email": email})

    def verificar_webhook(self, headers, body):
        try:
            return json.loads(body or b"{}")
        except (ValueError, TypeError):
            return None

    def parsear_evento(self, evento):
        ext = evento.get("external_id") or evento.get("id")
        estado = {"succeeded": "pagada", "paid": "pagada", "failed": "fallida"}.get(
            evento.get("status", "succeeded"), "pagada")
        return (ext, estado) if ext else None


class CulqiProvider(PasarelaPago):
    """Culqi v2. `crear_cargo` hace POST /v2/charges con el token de Culqi.js.
    Requiere `CULQI_SECRET_KEY` / `CULQI_PUBLIC_KEY` / `CULQI_WEBHOOK_SECRET`.
    """
    nombre = "culqi"
    _API = "https://api.culqi.com/v2"

    @property
    def config_publica(self):
        return {"provider": self.nombre, "publicKey": getattr(settings, "CULQI_PUBLIC_KEY", "")}

    def crear_cargo(self, orden, *, source_token, email):
        import requests  # dependencia ya presente en el proyecto

        sk = getattr(settings, "CULQI_SECRET_KEY", "")
        if not sk:
            return ResultadoCargo(ok=False, mensaje="Culqi sin configurar (falta CULQI_SECRET_KEY).")
        try:
            r = requests.post(
                f"{self._API}/charges",
                json={
                    "amount": int(round(float(orden.monto) * 100)),  # céntimos
                    "currency_code": orden.moneda,
                    "email": email or orden.email_pagador or "sin-correo@limaexpress.pe",
                    "source_id": source_token,
                    "metadata": {"orden": orden.token, "servicio": orden.servicio.codigo},
                },
                headers={"Authorization": f"Bearer {sk}"},
                timeout=getattr(settings, "AI_REQUEST_TIMEOUT_SECONDS", 30),
            )
            data = r.json()
        except Exception as e:  # noqa: BLE001
            return ResultadoCargo(ok=False, mensaje=f"Error de red con Culqi: {e}")
        if r.status_code in (200, 201) and data.get("id"):
            return ResultadoCargo(ok=True, external_id=data["id"], estado="pagada",
                                  mensaje="Aprobado.", raw=data)
        return ResultadoCargo(ok=False, mensaje=data.get("user_message") or data.get("merchant_message")
                              or "Cargo rechazado.", raw=data)

    def verificar_webhook(self, headers, body):
        secret = getattr(settings, "CULQI_WEBHOOK_SECRET", "")
        firma = headers.get("HTTP_X_CULQI_SIGNATURE") or headers.get("X-Culqi-Signature", "")
        if secret:
            esperado = hmac.new(secret.encode(), body or b"", hashlib.sha256).hexdigest()
            if not hmac.compare_digest(esperado, firma):
                return None
        try:
            return json.loads(body or b"{}")
        except (ValueError, TypeError):
            return None

    def parsear_evento(self, evento):
        tipo = evento.get("type") or evento.get("object", "")
        data = evento.get("data") or evento
        ext = data.get("id")
        if not ext:
            return None
        estado = "pagada" if "succeeded" in tipo or data.get("outcome", {}).get("type") == "sale_success" else "fallida"
        return (ext, estado)


_PROVIDERS = {"fake": FakeProvider, "culqi": CulqiProvider}


def build_pasarela(nombre=None) -> PasarelaPago:
    nombre = (nombre or getattr(settings, "PASARELA_PAGO", "fake")).strip().lower()
    return _PROVIDERS.get(nombre, FakeProvider)()
