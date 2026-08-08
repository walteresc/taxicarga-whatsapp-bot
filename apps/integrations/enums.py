from django.db import models


class OwnerState(models.TextChoices):
    BOT_ACTIVE = "BOT_ACTIVO", "Bot activo"
    WAITING_AGENT = "ESPERANDO_ASESOR", "Esperando asesor"
    AGENT_ACTIVE = "ASESOR_ACTIVO", "Asesor activo"
    RETURNING_TO_BOT = "DEVOLVIENDO_AL_BOT", "Devolviendo al bot"
    CLOSED = "CERRADA", "Cerrada"


class GenerationStatus(models.TextChoices):
    PENDING = "pending", "Pendiente"
    GENERATING = "generating", "Generando"
    READY = "ready", "Lista"
    PUBLISHED = "published", "Publicada"
    CANCELLED = "cancelled", "Cancelada"
    FAILED = "failed", "Fallida"


class InboxStatus(models.TextChoices):
    RECEIVED = "received", "Recibido"
    PROCESSING = "processing", "Procesando"
    PROCESSED = "processed", "Procesado"
    IGNORED = "ignored", "Ignorado"
    RETRY = "retry", "Reintento"
    DEAD_LETTER = "dead_letter", "Fallo definitivo"
    QUARANTINED = "quarantined", "Cuarentena"


class OutboxStatus(models.TextChoices):
    PENDING = "pending", "Pendiente"
    SENDING = "sending", "Enviando"
    SENT = "sent", "Enviado"
    RETRY = "retry", "Reintento"
    DEAD_LETTER = "dead_letter", "Fallo definitivo"
    CANCELLED = "cancelled", "Cancelado"
    RECONCILED = "reconciled", "Conciliado"


class Provider(models.TextChoices):
    META_WHATSAPP = "meta_whatsapp", "Meta WhatsApp"
    CHATWOOT = "chatwoot", "Chatwoot"
    INTERNAL = "internal", "Interno"
    META_MESSENGER = "meta_messenger", "Meta Messenger"
    META_INSTAGRAM = "meta_instagram", "Meta Instagram"
    EMAIL = "email", "Correo"
    WEBCHAT = "webchat", "Chat web"
    WEB_FORM = "web_form", "Formulario web"


class Visibility(models.TextChoices):
    PUBLIC = "public", "Público"
    PRIVATE = "private", "Privado"


class Direction(models.TextChoices):
    INBOUND = "inbound", "Entrante"
    OUTBOUND = "outbound", "Saliente"
    INTERNAL = "internal", "Interno"


class AuthorType(models.TextChoices):
    CUSTOMER = "customer", "Cliente"
    BOT = "bot", "Bot"
    AGENT = "agent", "Asesor"
    EXTERNAL_HUMAN = "external_human", "Humano externo"
    SYSTEM = "system", "Sistema"
    UNKNOWN = "unknown", "Desconocido"


class ContentType(models.TextChoices):
    TEXT = "text", "Texto"
    IMAGE = "image", "Imagen"
    AUDIO = "audio", "Audio"
    DOCUMENT = "document", "Documento"
    VIDEO = "video", "Video"
    LOCATION = "location", "Ubicación"
    CONTACT = "contact", "Contacto"
    INTERACTIVE_REPLY = "interactive_reply", "Respuesta interactiva"
    BUTTON = "button", "Botón"
    LIST = "list", "Lista"
    UNSUPPORTED = "unsupported", "No soportado"


class ProcessingStatus(models.TextChoices):
    RECEIVED = "received", "Recibido"
    NORMALIZED = "normalized", "Normalizado"
    QUEUED = "queued", "En cola"
    PROCESSING = "processing", "Procesando"
    PROCESSED = "processed", "Procesado"
    IGNORED = "ignored", "Ignorado"
    FAILED = "failed", "Fallido"
    QUARANTINED = "quarantined", "Cuarentena"


class CheckpointStatus(models.TextChoices):
    PENDING = "pending", "Pendiente"
    REBUILDING = "rebuilding", "Reconstruyendo"
    READY = "ready", "Listo"
    FAILED = "failed", "Fallido"


class ResumeMode(models.TextChoices):
    WAIT_FOR_CUSTOMER = "wait_for_customer", "Esperar cliente"
    RESPOND_NOW = "respond_now", "Responder ahora"


class SyncStatus(models.TextChoices):
    PENDING = "pending", "Pendiente"
    SYNCED = "synced", "Sincronizado"
    ERROR = "error", "Error"
    STALE = "stale", "Desactualizado"
    ARCHIVED = "archived", "Archivado"
