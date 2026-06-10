import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.leads.models import Lead
from .models import ServicioHistorico
from .services import crear_servicio_historico_desde_lead

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Lead)
def lead_cerrado_alimenta_historico(sender, instance, **kwargs):
    if instance.estado != Lead.CERRADO:
        return

    if ServicioHistorico.objects.filter(lead_origen=instance).exists():
        historico = ServicioHistorico.objects.get(lead_origen=instance)
        if historico.precio_final == instance.precio_final:
            return

    crear_servicio_historico_desde_lead(instance)
