from django.db import models


class ConfiguracionMarca(models.Model):
    """Nombre y logo mostrados al cliente (sidebar, login, cotizador) — dato
    de negocio editable desde Configuración → Marca, sin redeploy. Reemplaza
    en tiempo de ejecución el VITE_BRAND_NAME de build
    (frontend_materio/src/utils/brand.js), que solo sirve de valor por
    defecto cuando todavía no se configuró nada acá.

    El logo se guarda en base64 dentro de la fila (no como FileField/media)
    a propósito: es una sola imagen chica (se valida tamaño al subirla) y así
    el mismo endpoint de lectura pública la sirve completa sin necesitar un
    location nuevo en nginx ni acceso compartido a MEDIA_ROOT entre
    contenedores."""

    MAX_LOGO_BYTES = 500 * 1024

    nombre = models.CharField(max_length=60, blank=True, help_text="Vacío = usa el nombre por defecto del deploy.")
    logo_base64 = models.TextField(blank=True)
    logo_content_type = models.CharField(max_length=40, blank=True)

    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de marca"
        verbose_name_plural = "Configuración de marca"

    def __str__(self):
        return f"Marca: {self.nombre or '(default)'}"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def logo_data_url(self):
        if not self.logo_base64:
            return None
        return f"data:{self.logo_content_type};base64,{self.logo_base64}"
