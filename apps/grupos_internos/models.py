"""Chat de equipo interno — grupos de personal (no clientes de WhatsApp).

WhatsApp Business API no permite crear/administrar grupos reales por API
(confirmado contra la API de YCloud: no existe ningún endpoint de grupos).
Esto es un chat 100% interno de la CRM — nunca sale por WhatsApp, así que los
adjuntos se guardan localmente (MEDIA_ROOT), no vía YCloud.
"""
from django.conf import settings
from django.db import models


class GrupoInterno(models.Model):
    nombre = models.CharField(max_length=100)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="grupos_internos_creados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)
    # Igual que ConversacionWhatsApp.archived — aparece en la bandeja mezclado
    # con las conversaciones; archivarlo solo lo saca de la vista principal,
    # sigue existiendo y se puede desarchivar. No confundir con `activo`
    # (borrado lógico real, controla si sigue siendo visible/usable en absoluto).
    archivado = models.BooleanField(default=False)
    miembros = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="GrupoMiembro", through_fields=("grupo", "usuario"),
        related_name="grupos_internos",
    )

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class GrupoMiembro(models.Model):
    grupo = models.ForeignKey(GrupoInterno, on_delete=models.CASCADE, related_name="membresias")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membresias_grupo_interno",
    )
    agregado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
    )
    agregado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["grupo", "usuario"], name="unico_miembro_por_grupo_interno"),
        ]


class MensajeGrupoInterno(models.Model):
    TEXTO = "texto"
    IMAGEN = "imagen"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENTO = "documento"
    TIPOS = [
        (TEXTO, "Texto"),
        (IMAGEN, "Imagen"),
        (AUDIO, "Audio"),
        (VIDEO, "Video"),
        (DOCUMENTO, "Documento"),
    ]

    grupo = models.ForeignKey(GrupoInterno, on_delete=models.CASCADE, related_name="mensajes")
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="mensajes_grupo_interno",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TEXTO)
    contenido = models.TextField(blank=True)
    archivo = models.FileField(upload_to="grupos_internos/%Y/%m/", blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado_en"]
