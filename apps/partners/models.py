import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class SocioComercial(models.Model):
    """Una tienda / plataforma externa que integra la API de envíos."""

    nombre = models.CharField(max_length=160)
    contacto_nombre = models.CharField(max_length=160, blank=True, default="")
    contacto_email = models.EmailField(blank=True, default="")
    contacto_telefono = models.CharField(max_length=30, blank=True, default="")
    activo = models.BooleanField(default=True)

    webhook_url = models.URLField(blank=True, default="")
    webhook_secret = models.CharField(max_length=64, blank=True, default="")

    saldo = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Saldo de la cuenta (wallet). Negativo = le facturamos; positivo = a favor del socio.",
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Socio comercial"
        verbose_name_plural = "Socios comerciales"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


def _nuevo_secreto():
    return secrets.token_urlsafe(32)


def _hash(secreto):
    return hashlib.sha256(secreto.encode()).hexdigest()


class ApiKey(models.Model):
    """Credencial de un socio. El secreto solo se muestra una vez (al crearla);
    acá se guarda su hash. Formato del token: `<prefix>.<secreto>`."""

    ENTORNO_TEST = "test"
    ENTORNO_LIVE = "live"
    ENTORNOS = [(ENTORNO_TEST, "Test"), (ENTORNO_LIVE, "Live")]

    socio = models.ForeignKey(SocioComercial, on_delete=models.CASCADE, related_name="api_keys")
    entorno = models.CharField(max_length=4, choices=ENTORNOS, default=ENTORNO_TEST)
    prefix = models.CharField(max_length=24, unique=True, editable=False)
    secret_hash = models.CharField(max_length=64, editable=False)
    activa = models.BooleanField(default=True)
    ultimo_uso_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Llave de API"
        verbose_name_plural = "Llaves de API"

    def __str__(self):
        return f"{self.socio.nombre} · {self.entorno} · {self.prefix}"

    @classmethod
    def generar(cls, socio, *, entorno=ENTORNO_TEST):
        """Crea la llave y devuelve (instancia, token_completo). El token completo
        NO se guarda — es la única vez que se puede ver."""
        prefix = f"pk_{entorno}_{secrets.token_hex(6)}"
        secreto = _nuevo_secreto()
        key = cls.objects.create(socio=socio, entorno=entorno, prefix=prefix, secret_hash=_hash(secreto))
        return key, f"{prefix}.{secreto}"

    @classmethod
    def resolver(cls, token):
        """Devuelve la ApiKey válida para ese token, o None."""
        if not token or "." not in token:
            return None
        prefix, _, secreto = token.partition(".")
        key = cls.objects.select_related("socio").filter(prefix=prefix, activa=True).first()
        if not key or not key.socio.activo:
            return None
        if _hash(secreto) != key.secret_hash:
            return None
        cls.objects.filter(pk=key.pk).update(ultimo_uso_en=timezone.now())
        return key


class WebhookDelivery(models.Model):
    """Un evento enviado (o por enviar) al webhook del socio."""

    ESTADO_PENDIENTE = "pendiente"
    ESTADO_ENTREGADO = "entregado"
    ESTADO_FALLIDO = "fallido"
    ESTADOS = [(ESTADO_PENDIENTE, "Pendiente"), (ESTADO_ENTREGADO, "Entregado"), (ESTADO_FALLIDO, "Fallido")]

    socio = models.ForeignKey(SocioComercial, on_delete=models.CASCADE, related_name="webhooks")
    evento = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ESTADO_PENDIENTE)
    intentos = models.PositiveSmallIntegerField(default=0)
    ultimo_codigo = models.PositiveSmallIntegerField(null=True, blank=True)
    ultimo_error = models.CharField(max_length=300, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)
    entregado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "Entrega de webhook"
        verbose_name_plural = "Entregas de webhook"

    def __str__(self):
        return f"{self.socio.nombre} · {self.evento} · {self.estado}"


class IdempotencyRecord(models.Model):
    """Evita duplicar un recurso si el socio reintenta un POST con la misma
    `Idempotency-Key` (p.ej. por timeout de red)."""

    socio = models.ForeignKey(SocioComercial, on_delete=models.CASCADE, related_name="idempotency_keys")
    key = models.CharField(max_length=120)
    endpoint = models.CharField(max_length=120)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField(default=dict)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["socio", "key", "endpoint"], name="idempotency_unica_por_socio_endpoint"),
        ]
