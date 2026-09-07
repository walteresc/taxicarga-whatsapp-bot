import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.leads.models import Lead
from .models import ServicioHistorico
from .services import crear_servicio_historico_desde_lead

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Lead)
def lead_requiere_revision_entra_a_cola(sender, instance, **kwargs):
    """Un lead que necesita mirada humana entra a la bandeja 'Para revisión'
    (SolicitudCotizacion tipo=revision). Idempotente, se ejecuta tras el commit
    para no cargar la transacción del webhook."""
    if not instance.requiere_asesor:
        return

    lead_id = instance.id

    def _sync():
        from .pipeline import sync_review_request
        try:
            sync_review_request(Lead.objects.get(pk=lead_id))
        except Exception:
            logger.exception("sync_review_request falló para lead %s", lead_id)

    transaction.on_commit(_sync)


@receiver(post_save, sender=Lead)
def lead_cerrado_alimenta_historico(sender, instance, **kwargs):
    if instance.estado != Lead.CERRADO:
        return

    if ServicioHistorico.objects.filter(lead_origen=instance).exists():
        historico = ServicioHistorico.objects.get(lead_origen=instance)
        if historico.precio_final == instance.precio_final:
            return

    crear_servicio_historico_desde_lead(instance)
