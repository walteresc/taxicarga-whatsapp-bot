from dataclasses import dataclass

from django.db import transaction

from ..domain.requirements import ready_to_quote, required_missing
from ..domain.state import Access


@dataclass(frozen=True)
class CRMSyncResult:
    lead_id: int
    request_id: int
    ready_for_quote: bool
    missing: list[str]


class CRMV4Adapter:
    LEAD_FIELDS = (
        "tipo_servicio", "distrito_origen", "distrito_destino", "piso_origen",
        "piso_destino", "acceso_origen", "acceso_destino", "lista_objetos", "estado",
    )

    @transaction.atomic
    def start_new_request(self, conversation):
        from apps.leads.models import Lead
        from apps.whatsapp.models import ConversacionWhatsApp

        lead = Lead.objects.create(
            cliente=conversation.cliente,
            whatsapp_channel=conversation.channel,
            tipo_servicio="mudanza",
            estado=Lead.NUEVO,
        )
        conversation.lead = lead
        conversation.estado_cotizacion = ConversacionWhatsApp.COTIZACION_SIN_INICIAR
        conversation.save(update_fields=["lead", "estado_cotizacion", "actualizada_en"])
        return lead

    @transaction.atomic
    def sync(self, state, lead) -> CRMSyncResult:
        from apps.cotizador.models import SolicitudCotizacion
        from apps.leads.models import Lead

        self.project_state_to_lead(state, lead)
        complete = ready_to_quote(state)
        missing = required_missing(state)
        lead.estado = Lead.EN_CONVERSACION if complete else Lead.DATOS_INCOMPLETOS
        lead.save(update_fields=self.LEAD_FIELDS)
        self._sync_locations(state, lead)
        request = SolicitudCotizacion.objects.filter(
            lead=lead,
            estado__in=[SolicitudCotizacion.PENDIENTE, SolicitudCotizacion.EN_PROCESO],
        ).first()
        if request is None:
            request = SolicitudCotizacion.objects.create(
                lead=lead,
                datos_faltantes=missing,
                motivo="Bot V4: lista para cotizar" if complete else "Bot V4: datos incompletos",
            )
        else:
            request.datos_faltantes = missing
            request.motivo = "Bot V4: lista para cotizar" if complete else "Bot V4: datos incompletos"
            request.save(update_fields=["datos_faltantes", "motivo", "actualizada_en"])
        return CRMSyncResult(lead.pk, request.pk, complete, missing)

    @transaction.atomic
    def apply_quote_decision(self, decision, lead, conversation):
        from django.utils import timezone
        from apps.cotizador.models import SolicitudCotizacion
        from apps.leads.models import Lead
        from apps.whatsapp.models import ConversacionWhatsApp

        if decision.mode == "auto":
            lead.estado = Lead.COTIZADO
            lead.precio_cotizado = decision.price
            lead.precio_recomendado = decision.price
            lead.save(update_fields=["estado", "precio_cotizado", "precio_recomendado"])
            SolicitudCotizacion.objects.filter(
                lead=lead,
                estado__in=[SolicitudCotizacion.PENDIENTE, SolicitudCotizacion.EN_PROCESO],
            ).update(estado=SolicitudCotizacion.TERMINADA, resuelta_en=timezone.now())
            conversation.estado_cotizacion = ConversacionWhatsApp.COTIZACION_PRECIO_ENVIADO
        else:
            lead.estado = Lead.EN_CONVERSACION
            lead.save(update_fields=["estado"])
            conversation.estado_cotizacion = ConversacionWhatsApp.COTIZACION_PENDIENTE
        conversation.save(update_fields=["estado_cotizacion", "actualizada_en"])
        return decision

    @staticmethod
    def project_state_to_lead(state, lead):
        lead.tipo_servicio = "mudanza"
        if state.origin_district:
            lead.distrito_origen = state.origin_district
        if state.destination_district:
            lead.distrito_destino = state.destination_district
        if state.origin_floor is not None:
            lead.piso_origen = state.origin_floor
        if state.destination_floor is not None:
            lead.piso_destino = state.destination_floor
        if state.origin_access is not None:
            lead.acceso_origen = str(state.origin_access)
        if state.destination_access is not None:
            lead.acceso_destino = str(state.destination_access)
        if state.items:
            lead.lista_objetos = "\n".join(state.items)
        return lead

    @staticmethod
    def _sync_locations(state, lead):
        from apps.leads.models import LeadUbicacion

        for order, kind, district, floor, access in (
            (1, LeadUbicacion.ORIGEN, state.origin_district, state.origin_floor, state.origin_access),
            (2, LeadUbicacion.DESTINO, state.destination_district, state.destination_floor, state.destination_access),
        ):
            if not any((district, floor, access)):
                continue
            ascensor = True if access == Access.ELEVATOR else False if access == Access.STAIRS else None
            LeadUbicacion.objects.update_or_create(
                lead=lead,
                tipo=kind,
                defaults={
                    "orden": order,
                    "distrito": district or "",
                    "piso": floor,
                    "ascensor": ascensor,
                    "observaciones_acceso": str(access or ""),
                },
            )
