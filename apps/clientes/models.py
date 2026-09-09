from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.clientes.phone_normalizer import normalize_phone


def _contar_alfanumericos(texto):
    """Nº de caracteres alfanuméricos (Unicode) en el texto. Emojis y signos de
    puntuación no cuentan — str.isalnum() ya los excluye."""
    return sum(1 for c in (texto or "") if c.isalnum())


class Cliente(models.Model):
    SOURCE_MANUAL = "manual"
    SOURCE_CRM = "crm"
    SOURCE_CHANNEL = "channel"
    SOURCE_IMPORT = "import"
    SOURCE_FALLBACK = "fallback"

    NAME_SOURCES = [
        (SOURCE_MANUAL, "Manual (CRM)"),
        (SOURCE_CRM, "CRM/Lead"),
        (SOURCE_CHANNEL, "WhatsApp Channel"),
        (SOURCE_IMPORT, "Import"),
        (SOURCE_FALLBACK, "Fallback (phone)"),
    ]

    TIPO_OCASIONAL = "ocasional"
    TIPO_FRECUENTE = "frecuente"
    TIPO_EMPRESA = "empresa"
    TIPOS_CLIENTE = [
        (TIPO_OCASIONAL, "Ocasional"),
        (TIPO_FRECUENTE, "Frecuente"),
        (TIPO_EMPRESA, "Empresa"),
    ]

    nombre = models.CharField(max_length=160, blank=True)
    telefono = models.CharField(max_length=30, unique=True)
    tipo = models.CharField(
        max_length=12, choices=TIPOS_CLIENTE, default=TIPO_OCASIONAL, db_index=True,
        help_text="Ocasional (guest), Frecuente (carga recurrente) o Empresa (con cuenta/portal).",
    )
    documento = models.CharField(max_length=20, blank=True, default="")
    correo = models.EmailField(max_length=200, blank=True, default="")
    ruc = models.CharField(max_length=20, blank=True, default="")
    razon_social = models.CharField(max_length=200, blank=True, default="")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    ultima_interaccion = models.DateTimeField(default=timezone.now)

    phone_e164 = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        db_index=True,
        help_text="Normalized phone in E.164 format (+51995403320)"
    )
    display_name = models.CharField(
        max_length=160,
        blank=True,
        help_text="Name displayed in CRM (manual or best-match)"
    )
    channel_profile_name = models.CharField(
        max_length=160,
        blank=True,
        help_text="Name from WhatsApp profile"
    )
    name_source = models.CharField(
        max_length=20,
        choices=NAME_SOURCES,
        default=SOURCE_FALLBACK,
        help_text="Source of display_name"
    )
    aliases = models.JSONField(
        default=list,
        blank=True,
        help_text="List of historical names: ['TEST Stage 7', 'ELI ESCOBAR', ...]"
    )
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="merged_from",
        help_text="If not null, this cliente has been merged into another"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Deactivated if merged or duplicate"
    )
    ycloud_user_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="YCloud internal fromUserId — fallback identity when the webhook omits 'from' (e.g. reply/quote messages)"
    )
    es_transportista = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Marcado automáticamente al detectar un mensaje 'OFERTA-<código>' "
                   "(tercerización de cargas). Reversible manualmente desde la ficha "
                   "del contacto — no es un estado que deba quedar atrapado por error.",
    )
    es_transportista_marcado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Quién marcó/desmarcó es_transportista. NULL = detección "
                   "automática (Fase 2, por código OFERTA-<código> válido).",
    )
    es_transportista_marcado_en = models.DateTimeField(null=True, blank=True)

    # Personal de oficina (asesores/administración) que escribe por WhatsApp —
    # partición de la bandeja igual que Transportistas. A mano porque, a
    # diferencia de "Campo" (Conductor/Ayudante ya tienen teléfono guardado),
    # no hay hoy una lista de teléfonos de oficina de la que auto-detectar.
    es_oficina = models.BooleanField(default=False, db_index=True)

    # Refuerzo manual de "Campo" — la detección automática (teléfono contra
    # Conductor/Ayudante activo, ver api_active_conversations) sigue siendo la
    # vía principal y NO se toca; esto es solo para agregar a alguien a mano
    # desde "Gestionar Campo" cuando todavía no está registrado como personal
    # de campo con ese mismo teléfono.
    es_campo = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-ultima_interaccion"]
        indexes = [
            models.Index(fields=["phone_e164"]),
            models.Index(fields=["is_active", "-ultima_interaccion"]),
        ]

    def save(self, *args, **kwargs):
        # Normalize phone to E.164 format AND update telefono field
        if self.telefono:
            result = normalize_phone(self.telefono)
            if result["is_valid"]:
                # Store both the E.164 version and update original field for consistency
                self.phone_e164 = result["normalized_e164"]
                # IMPORTANT: Also update telefono to E.164 so phone_identity queries work consistently
                self.telefono = result["normalized_e164"]

        # Set display_name if not set
        if not self.display_name:
            self.display_name = self.nombre or ""

        super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name or self.nombre or self.telefono

    @property
    def profile_name(self):
        """Nombre que se muestra del contacto (el editado en el CRM o, si no, el
        de perfil de WhatsApp), sin juzgar si es útil."""
        return (self.display_name or self.nombre or "").strip()

    @property
    def name_is_manual(self):
        """El nombre lo fijó un asesor en el CRM (tiene prioridad sobre el de
        WhatsApp y no se sobrescribe al llegar mensajes nuevos)."""
        return self.name_source == self.SOURCE_MANUAL

    @property
    def profile_name_usable(self):
        """False cuando el nombre de perfil no sirve para identificar al contacto:
        vacío, solo emojis, solo signos de puntuación, con menos de 2 caracteres
        alfanuméricos, o cuando el "nombre" es en realidad el propio teléfono
        (fallback). En ese caso el CRM muestra solo el teléfono.

        Un nombre puesto a mano por un asesor SIEMPRE se considera utilizable
        (aunque escriba "🏪 cliente difícil"): fue una decisión humana."""
        name = self.profile_name
        if not name:
            return False
        if self.name_is_manual:
            return True
        # "nombre" que coincide con el teléfono → no identifica, mostrar solo el número
        name_digits = "".join(c for c in name if c.isdigit())
        phone_digits = "".join(c for c in self.contact_phone if c.isdigit())
        if name_digits and phone_digits and name_digits == phone_digits:
            return False
        return _contar_alfanumericos(name) >= 2

    @property
    def has_real_phone(self):
        """False para contactos que no exponen número — su Cliente.telefono lleva
        el prefijo 'YCID:' (identidad opaca de YCloud, no un E.164)."""
        return not (self.telefono or "").startswith("YCID:")

    @property
    def contact_phone(self):
        """Identificador de contacto para mostrar/buscar.

        Contacto normal      -> teléfono E.164 (telefono ya se normaliza en save()).
        Contacto sin número  -> el user id de WhatsApp (BSUID, p.ej. 'PE.1041501801847001'),
                                que es como YCloud identifica y direcciona a ese contacto.
                                NUNCA vacío: el asesor necesita un identificador estable
                                (y puede renombrarlo a mano). El front lo marca como
                                "ID de WhatsApp", no como teléfono."""
        tel = (self.telefono or "").strip()
        if tel.startswith("YCID:"):
            return self.ycloud_user_id or tel[len("YCID:"):]
        return tel or self.phone_e164 or ""


class Conversacion(models.Model):
    CANAL_WHATSAPP = "whatsapp"
    CANALES = [(CANAL_WHATSAPP, "WhatsApp")]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="conversaciones",
    )
    mensaje_entrada = models.TextField(blank=True)
    mensaje_salida = models.TextField(blank=True)
    canal = models.CharField(max_length=30, choices=CANALES, default=CANAL_WHATSAPP)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.cliente} - {self.fecha:%Y-%m-%d %H:%M}"

# Create your models here.
