"""Estado comercial del pipeline: derivado, nunca duplicado.

Cuatro bandejas, sin solape. La bandeja de una oportunidad se calcula SIEMPRE por
la condición de abajo — `ConversacionWhatsApp.estado_cotizacion` es un espejo que
se puede desincronizar y NO es fuente de verdad (queda solo por compatibilidad).

Orden de prioridad (una oportunidad cae en la primera que cumple):
    Reservas  >  Cotizaciones  >  Por cotizar  >  Para revisión

    Para revisión : SolicitudCotizacion(tipo=revision, estado activo)
    Por cotizar   : SolicitudCotizacion(tipo=cotizacion, estado activo)
    Cotizaciones  : CotizacionComercial con precio ya enviado al cliente
    Reservas      : existe Servicio (venta cerrada)
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.cotizador.models import CotizacionComercial, SolicitudCotizacion
from apps.leads.models import Lead
from apps.servicios.models import SERVICIO_CANCELADO, SERVICIO_FINALIZADO, Servicio

logger = logging.getLogger(__name__)

_SOLICITUD_ACTIVA = (SolicitudCotizacion.PENDIENTE, SolicitudCotizacion.EN_PROCESO)

# Cotización que ya salió al cliente y sigue en juego.
COTIZACION_EN_JUEGO = ("enviada", "entregada", "en_negociacion")
COTIZACION_VISIBLE = COTIZACION_EN_JUEGO + ("rechazada", "vencida", "aceptada")


# --------------------------------------------------------------------------- #
#  Motivo de una revisión (derivado de flags del lead)
# --------------------------------------------------------------------------- #

def motivo_revision(lead):
    motivos = []
    if lead.es_interprovincial:
        motivos.append("Ruta fuera de Lima (cotizador no fiable)")
    if lead.estado == Lead.DATOS_INCOMPLETOS or not _datos_minimos(lead):
        motivos.append("Datos incompletos")
    detalle = (lead.motivo_derivacion or "").strip()
    if detalle and detalle not in motivos:
        motivos.append(detalle)
    if not motivos:
        motivos.append("Requiere revisión de un asesor")
    return " · ".join(motivos)


def _datos_minimos(lead):
    return bool(lead.tipo_servicio and lead.distrito_origen and lead.distrito_destino)


# --------------------------------------------------------------------------- #
#  Tarifa de ruta frecuente (dato fiable aunque el cotizador general no lo use)
# --------------------------------------------------------------------------- #

def tarifa_ruta_frecuente(distrito_origen, distrito_destino, *, minimo_casos=3):
    """Si la ruta del lead coincide con una ruta interprovincial con histórico
    suficiente, devuelve su tarifa típica. Si no, None.

        {"route": "Lima ↔ Piura", "cases": 71, "typicalPrice": 2500.0,
         "priceMin": 150.0, "priceMax": 5700.0}
    """
    from statistics import median

    from apps.cotizador.models import ServicioHistorico
    from apps.dashboard.services_reportes import (
        _clave_ruta_interprovincial, _ruta_fuera_de_lima,
    )

    if not _ruta_fuera_de_lima(distrito_origen, distrito_destino):
        return None
    objetivo = _clave_ruta_interprovincial(distrito_origen, distrito_destino)

    precios = []
    qs = ServicioHistorico.objects.filter(cerrado=True).values_list(
        "distrito_origen", "distrito_destino", "precio_final", "precio_cotizado",
    )
    for o, d, pf, pc in qs.iterator():
        precio = pf if pf is not None else pc
        if precio is None or precio <= 0:
            continue
        if _clave_ruta_interprovincial(o, d) == objetivo:
            precios.append(float(precio))

    if len(precios) < minimo_casos:
        return None
    return {
        "route": objetivo,
        "cases": len(precios),
        "typicalPrice": round(median(precios), 2),
        "priceMin": round(min(precios), 2),
        "priceMax": round(max(precios), 2),
    }


# --------------------------------------------------------------------------- #
#  Sincronizar la cola de revisión
# --------------------------------------------------------------------------- #

def sync_review_request(lead):
    """Garantiza que un lead que necesita revisión tenga su SolicitudCotizacion
    (tipo=revision) en la cola. Idempotente. Devuelve la solicitud o None.

    Un lead 'necesita revisión' si `requiere_asesor` y aún no está en el pipeline
    (sin solicitud activa, sin cotización, sin servicio) y no está cerrado/perdido.
    """
    if not lead.requiere_asesor or lead.estado in (Lead.CERRADO, Lead.PERDIDO):
        return None

    # Derivación automática de interprovinciales: si está activada en Configuración
    # y la carga ya tiene los datos completos, se publica sola a los transportistas
    # y NO entra a la cola de revisión del asesor.
    try:
        from apps.tercerizacion.services import derivar_interprovincial_si_corresponde
        if derivar_interprovincial_si_corresponde(lead):
            return None
    except Exception:
        logger.exception("Fallo la derivación automática de interprovincial para lead %s", lead.pk)

    activa = SolicitudCotizacion.objects.filter(lead=lead, estado__in=_SOLICITUD_ACTIVA).first()
    if activa:
        # Si aparecieron señales nuevas en un barrido posterior (ej. el cliente
        # pidió un asesor después de la primera extracción), refresca el motivo
        # guardado para que el asesor vea la razón actual, no la de cuando se creó.
        motivo_actual = motivo_revision(lead)
        if activa.motivo != motivo_actual:
            activa.motivo = motivo_actual
            activa.save(update_fields=["motivo"])
        return None
    if CotizacionComercial.objects.filter(lead=lead).exclude(estado__in=("borrador", "cancelada")).exists():
        return None
    if Servicio.objects.filter(lead_origen=lead).exists():
        return None

    conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
    return SolicitudCotizacion.objects.create(
        lead=lead,
        conversacion=conv,
        tipo=SolicitudCotizacion.TIPO_REVISION,
        estado=SolicitudCotizacion.PENDIENTE,
        motivo=motivo_revision(lead),
        prioridad=lead.prioridad,
    )


# --------------------------------------------------------------------------- #
#  Contadores del menú
# --------------------------------------------------------------------------- #

def potenciales_queryset():
    """Leads que siguen conversando (con el bot o un asesor) sin haber escalado
    todavía a ninguna otra bandeja del pipeline. Es la bandeja "de fondo": no
    tiene una condición propia como las demás, es el residuo — cualquier lead
    activo que no calzó en Reservas/Cotizaciones/Por cotizar/Para revisión.
    Sirve para que el asesor note, entre todo lo que el bot está atendiendo
    solo, cuáles ya muestran intención real de compra (por eso existen como
    Lead: se crean recién cuando la extracción encuentra señales suficientes,
    ver apps/whatsapp/services_extraccion.py) y priorizarlos.
    """
    return (
        Lead.objects
        .exclude(estado__in=(Lead.CERRADO, Lead.PERDIDO))
        .filter(requiere_asesor=False)
        # Solo clientes: fuera transportistas, personal de oficina y de campo.
        .filter(cliente__es_transportista=False, cliente__es_oficina=False, cliente__es_campo=False)
        .exclude(id__in=SolicitudCotizacion.objects.filter(estado__in=_SOLICITUD_ACTIVA).values("lead_id"))
        .exclude(
            id__in=CotizacionComercial.objects
            .exclude(estado__in=("borrador", "cancelada"))
            .values("lead_id"),
        )
        .exclude(servicio_generado__isnull=False)
    )


def _lead_ids_por_etapa():
    """{etapa: [lead_id, ...]} de lo que hoy está en cada bandeja."""
    rev = SolicitudCotizacion.objects.filter(
        tipo=SolicitudCotizacion.TIPO_REVISION, estado__in=_SOLICITUD_ACTIVA,
    ).values_list("lead_id", flat=True)
    quo = SolicitudCotizacion.objects.filter(
        tipo=SolicitudCotizacion.TIPO_COTIZACION, estado__in=_SOLICITUD_ACTIVA,
    ).values_list("lead_id", flat=True)
    return {
        "potentials": list(potenciales_queryset().values_list("id", flat=True)),
        "review": list(rev),
        "quoting": list(quo),
        "quotes": list(
            CotizacionComercial.objects.filter(estado__in=COTIZACION_EN_JUEGO)
            .values_list("lead_id", flat=True),
        ),
        "bookings": list(
            Servicio.objects.exclude(estado__in=(SERVICIO_FINALIZADO, SERVICIO_CANCELADO))
            .filter(lead_origen__isnull=False)
            .values_list("lead_origen_id", flat=True),
        ),
    }


def marcar_visto(lead_id, etapa, usuario=None):
    """Registra que alguien abrió el detalle de este lead estando en `etapa`.
    Idempotente (refresca `visto_en`)."""
    from apps.cotizador.models import PipelineVisto

    if not etapa:
        return
    PipelineVisto.objects.update_or_create(
        etapa=etapa, lead_id=lead_id,
        defaults={"visto_por": usuario if getattr(usuario, "pk", None) else None},
    )


def leads_no_vistos(etapa, lead_ids):
    """Set de lead_ids de `lead_ids` que nadie abrió todavía estando en `etapa`."""
    from apps.cotizador.models import PipelineVisto

    if not lead_ids:
        return set()
    vistos = set(
        PipelineVisto.objects.filter(etapa=etapa, lead_id__in=lead_ids)
        .values_list("lead_id", flat=True),
    )
    return {lid for lid in lead_ids if lid not in vistos}


def perdidos_queryset():
    """Leads descartados / marcados perdidos. Fuera del pipeline activo."""
    return (
        Lead.objects.filter(estado=Lead.PERDIDO)
        .select_related("cliente", "vendedor_asignado")
        .order_by("-fecha_cierre", "-fecha_creacion")
    )


def pipeline_counts():
    totales = {
        "potentials": potenciales_queryset().count(),
        "review": SolicitudCotizacion.objects.filter(
            tipo=SolicitudCotizacion.TIPO_REVISION, estado__in=_SOLICITUD_ACTIVA,
        ).count(),
        "quoting": SolicitudCotizacion.objects.filter(
            tipo=SolicitudCotizacion.TIPO_COTIZACION, estado__in=_SOLICITUD_ACTIVA,
        ).count(),
        "quotes": CotizacionComercial.objects.filter(estado__in=COTIZACION_EN_JUEGO).count(),
        "bookings": Servicio.objects.exclude(
            estado__in=(SERVICIO_FINALIZADO, SERVICIO_CANCELADO),
        ).count(),
    }
    por_etapa = _lead_ids_por_etapa()
    no_vistos = {etapa: len(leads_no_vistos(etapa, ids)) for etapa, ids in por_etapa.items()}
    return {**totales, "unseen": no_vistos}


# --------------------------------------------------------------------------- #
#  Etapa actual de un lead + movimiento manual entre etapas
# --------------------------------------------------------------------------- #

# Etapas que el asesor puede fijar a mano desde la bandeja (las otras dos —
# Cotizaciones y Reservas — necesitan datos reales: un precio, una reserva).
ETAPAS_MANUALES = ("potentials", "review", "quoting")

ETAPA_LABEL = {
    "potentials": "Oportunidad",
    "review": "Estancados",
    "quoting": "Por cotizar",
    "quotes": "Cotizados",
    "bookings": "Reserva",
    "lost": "Perdido",
}


def etapa_de_lead(lead):
    """La misma prioridad que pipeline_counts: Reservas > Cotizaciones > Por
    cotizar > Para revisión > Potenciales. Devuelve la clave inglesa."""
    if lead is None:
        return None
    if lead.estado in (Lead.CERRADO, Lead.PERDIDO):
        return "lost"
    if Servicio.objects.filter(lead_origen=lead).exclude(
        estado__in=(SERVICIO_FINALIZADO, SERVICIO_CANCELADO),
    ).exists():
        return "bookings"
    if CotizacionComercial.objects.filter(lead=lead, estado__in=COTIZACION_EN_JUEGO).exists():
        return "quotes"
    solicitud = SolicitudCotizacion.objects.filter(lead=lead, estado__in=_SOLICITUD_ACTIVA).first()
    if solicitud:
        return "review" if solicitud.tipo == SolicitudCotizacion.TIPO_REVISION else "quoting"
    return "potentials"


def mover_lead_a_etapa(lead_id, etapa, actor):
    """Mueve un lead a mano entre Potenciales / Para revisión / Por cotizar.
    Idempotente. Devuelve la etapa resultante."""
    from django.core.exceptions import ValidationError

    if etapa not in ETAPAS_MANUALES:
        raise ValidationError(
            "Cotizaciones y Reservas se generan con los botones Cotizar / Reservar del chat.",
        )
    with transaction.atomic():
        lead = Lead.objects.select_for_update().get(pk=lead_id)
        actual = etapa_de_lead(lead)
        if actual in ("quotes", "bookings"):
            raise ValidationError(
                "Esta conversación ya tiene una cotización o reserva; no se puede volver atrás desde acá.",
            )
        if lead.estado in (Lead.CERRADO, Lead.PERDIDO):
            lead.estado = Lead.NUEVO
            lead.save(update_fields=["estado"])

        activa = SolicitudCotizacion.objects.select_for_update().filter(
            lead=lead, estado__in=_SOLICITUD_ACTIVA,
        ).first()

        if etapa == "potentials":
            if activa:
                activa.estado = SolicitudCotizacion.CANCELADA
                activa.resuelta_en = timezone.now()
                activa.save(update_fields=["estado", "resuelta_en"])
            if lead.requiere_asesor:
                lead.requiere_asesor = False
                lead.save(update_fields=["requiere_asesor"])

        elif etapa == "review":
            if activa:
                activa.tipo = SolicitudCotizacion.TIPO_REVISION
                activa.estado = SolicitudCotizacion.PENDIENTE
                activa.motivo = activa.motivo or motivo_revision(lead)
                activa.save(update_fields=["tipo", "estado", "motivo", "actualizada_en"])
            else:
                conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
                SolicitudCotizacion.objects.create(
                    lead=lead, conversacion=conv,
                    tipo=SolicitudCotizacion.TIPO_REVISION,
                    estado=SolicitudCotizacion.PENDIENTE,
                    motivo=motivo_revision(lead),
                    prioridad=lead.prioridad,
                )
            if not lead.requiere_asesor:
                lead.requiere_asesor = True
                lead.save(update_fields=["requiere_asesor"])

        elif etapa == "quoting":
            if activa:
                activa.tipo = SolicitudCotizacion.TIPO_COTIZACION
                activa.estado = SolicitudCotizacion.PENDIENTE
                if actor and not activa.asignada_a_id:
                    activa.asignada_a = actor
                activa.save(update_fields=["tipo", "estado", "asignada_a", "actualizada_en"])
            else:
                conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
                SolicitudCotizacion.objects.create(
                    lead=lead, conversacion=conv,
                    tipo=SolicitudCotizacion.TIPO_COTIZACION,
                    estado=SolicitudCotizacion.PENDIENTE,
                    asignada_a=actor,
                    prioridad=lead.prioridad,
                )

        _auditar(lead, actor, "movida_a_etapa", {"de": actual, "a": etapa})
        return etapa


# --------------------------------------------------------------------------- #
#  Cotizar / Reservar rápido desde el chat (botones del composer)
# --------------------------------------------------------------------------- #

def cotizar_rapido(lead_id, precio, mensaje, actor, *, vigencia_dias=7):
    """El asesor le pone precio a la conversación y manda la cotización al
    cliente por WhatsApp, en un paso. La conversación queda en 'Cotizaciones'.
    Devuelve {stage, code, sent}."""
    from decimal import Decimal, InvalidOperation

    from django.core.exceptions import ValidationError

    from apps.cotizador.commercial import (
        crear_revision, guardar_borrador, marcar_revision_enviada,
    )
    from apps.whatsapp.services import send_crm_message

    try:
        precio = Decimal(str(precio))
    except (InvalidOperation, TypeError):
        raise ValidationError("Precio inválido.")
    if precio <= 0:
        raise ValidationError("El precio debe ser mayor a cero.")
    mensaje = (mensaje or "").strip()
    if not mensaje:
        raise ValidationError("Escribe el mensaje de la cotización para el cliente.")

    with transaction.atomic():
        lead = Lead.objects.select_for_update().get(pk=lead_id)
        etapa = etapa_de_lead(lead)
        es_recotizacion = etapa == "quotes"
        if etapa == "bookings":
            raise ValidationError(
                "Esta conversación ya tiene una reserva confirmada. El precio se ajusta desde Reservas.",
            )

        # Asignar la conversación al asesor ANTES de tocar nada más, así todos
        # los conversation.updated que dispare el flujo (cotización, etiquetas)
        # ya salen con attention_state='asesor' y el composer no parpadea a
        # "Asignarme".
        conv_pre = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
        if conv_pre:
            _tomar_para_seguir_atendiendo(conv_pre.id, actor)

        if etapa == "quotes":
            # RE-COTIZAR: nueva revisión (nuevo precio) sobre la cotización que ya
            # existe; queda como precio cotizado vigente y se reenvía al cliente.
            cotizacion = (
                CotizacionComercial.objects
                .filter(lead=lead, estado__in=COTIZACION_EN_JUEGO)
                .order_by("-actualizada_en")
                .first()
            )
            revision = crear_revision(
                cotizacion, actor, precio,
                vigencia_dias=vigencia_dias, mensaje_whatsapp=mensaje,
            )
            marcar_revision_enviada(revision)
            _auditar(lead, actor, "re_cotizado_rapido",
                     {"cotizacion": cotizacion.codigo, "precio": str(precio)})
        else:
            # Primera cotización. Garantiza SolicitudCotizacion(tipo=cotizacion).
            mover_lead_a_etapa(lead_id, "quoting", actor)
            solicitud = SolicitudCotizacion.objects.filter(
                lead=lead, estado__in=_SOLICITUD_ACTIVA,
            ).first()
            cotizacion, revision = guardar_borrador(
                solicitud, actor, precio,
                vigencia_dias=vigencia_dias, mensaje_whatsapp=mensaje,
            )
            marcar_revision_enviada(revision)
            _auditar(lead, actor, "cotizado_rapido",
                     {"cotizacion": cotizacion.codigo, "precio": str(precio)})

    conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
    enviado = False
    if conv:
        _tomar_para_seguir_atendiendo(conv.id, actor)
        try:
            enviado = bool(send_crm_message(conv, actor, mensaje).get("success"))
        except Exception:
            enviado = False
    return {
        "stage": "quotes", "code": cotizacion.codigo, "sent": enviado,
        "requoted": es_recotizacion,
    }


def _tomar_para_seguir_atendiendo(conversacion_id, actor):
    """Cotizar/Reservar = el asesor está manejando esta conversación: queda
    asignada a él y en modo asesor para poder seguir chateando (el composer no
    se bloquea). Si ya la tiene otro asesor, se respeta y no se toca."""
    try:
        from apps.whatsapp.domain import ConversacionOcupada, tomar_conversacion
        tomar_conversacion(conversacion_id, actor)
    except ConversacionOcupada:
        pass
    except Exception:
        pass


def reservar_rapido(lead_id, datos, actor):
    """El asesor confirma la reserva a mano cargando los datos mínimos
    (fecha, horario, direcciones, precio). Crea el Servicio. La conversación
    queda en 'Reservas'. Devuelve {stage, code}."""
    from decimal import Decimal, InvalidOperation

    from django.core.exceptions import ValidationError

    from apps.ia.conversation_policy import booking_missing_fields
    from apps.leads.models import LeadUbicacion
    from apps.servicios.services import crear_servicio_desde_lead

    datos = datos or {}
    with transaction.atomic():
        lead = Lead.objects.select_for_update().select_related("cliente").get(pk=lead_id)
        if Servicio.objects.filter(lead_origen=lead).exists():
            raise ValidationError("Esta conversación ya tiene una reserva.")

        if datos.get("nombre_cliente") and not lead.cliente.nombre:
            lead.cliente.nombre = datos["nombre_cliente"].strip()
            lead.cliente.save(update_fields=["nombre"])

        campos_lead = {}
        for k in ("fecha_servicio", "horario_servicio", "tipo_servicio",
                  "distrito_origen", "distrito_destino",
                  "persona_contacto", "telefono_contacto"):
            if datos.get(k):
                campos_lead[k] = str(datos[k]).strip()
        if campos_lead:
            for k, v in campos_lead.items():
                setattr(lead, k, v)
            lead.save(update_fields=list(campos_lead))

        for tipo, orden, dir_key, dist_key in (
            (LeadUbicacion.ORIGEN, 1, "direccion_origen", "distrito_origen"),
            (LeadUbicacion.DESTINO, 2, "direccion_destino", "distrito_destino"),
        ):
            if datos.get(dir_key):
                LeadUbicacion.objects.update_or_create(
                    lead=lead, tipo=tipo,
                    defaults={
                        "orden": orden,
                        "direccion": datos[dir_key].strip(),
                        "distrito": (datos.get(dist_key) or "").strip(),
                    },
                )

        faltan = booking_missing_fields(lead)
        if faltan:
            raise ValidationError(
                "Faltan datos para crear la reserva: " + ", ".join(faltan)
                + ". Las direcciones deben incluir calle/avenida y número.",
            )

        servicio, _creado = crear_servicio_desde_lead(
            lead, usuario=actor, require_accepted_revision=False,
        )
        if datos.get("precio"):
            try:
                servicio.precio = Decimal(str(datos["precio"]))
                servicio.save(update_fields=["precio"])
            except (InvalidOperation, TypeError):
                pass
        _auditar(lead, actor, "reserva_creada_manual", {"reserva": servicio.codigo})

    conv = lead.sesiones_whatsapp.order_by("-actualizada_en").first()
    if conv:
        _tomar_para_seguir_atendiendo(conv.id, actor)
    return {"stage": "bookings", "code": servicio.codigo}


# --------------------------------------------------------------------------- #
#  Acciones de transición entre bandejas
# --------------------------------------------------------------------------- #

def pasar_revision_a_cotizar(solicitud_id, actor):
    """Resuelve una revisión: pasa la MISMA solicitud a tipo=cotizacion.
    El lead queda listo para ponerle precio en 'Por cotizar'."""
    with transaction.atomic():
        solicitud = SolicitudCotizacion.objects.select_for_update().select_related("lead").get(pk=solicitud_id)
        if solicitud.tipo != SolicitudCotizacion.TIPO_REVISION:
            from django.core.exceptions import ValidationError
            raise ValidationError("Esta solicitud no está en revisión.")
        solicitud.tipo = SolicitudCotizacion.TIPO_COTIZACION
        solicitud.estado = SolicitudCotizacion.PENDIENTE
        if actor and not solicitud.asignada_a_id:
            solicitud.asignada_a = actor
        solicitud.save(update_fields=["tipo", "estado", "asignada_a", "actualizada_en"])
        _auditar(solicitud.lead, actor, "revision_a_cotizar", {"solicitud": solicitud.id})
        return solicitud


def descartar_lead(lead_id, actor, motivo):
    """Descarta una oportunidad: lead a PERDIDO, solicitud activa cancelada."""
    from apps.dashboard.views import _close_lost  # reutiliza la lógica existente

    with transaction.atomic():
        lead = Lead.objects.select_for_update().get(pk=lead_id)
        SolicitudCotizacion.objects.filter(
            lead=lead, estado__in=_SOLICITUD_ACTIVA,
        ).update(estado=SolicitudCotizacion.CANCELADA, resuelta_en=timezone.now())
        _close_lost(lead, motivo or "Descartada en revisión", actor)
        _auditar(lead, actor, "descartada", {"motivo": motivo})
        return lead


def _auditar(lead, actor, accion, extra):
    """Traza mínima en nota_interna del lead. (No hay modelo de auditoría propio;
    si se añade uno, este es el único punto a cambiar.)"""
    sello = timezone.localtime().strftime("%Y-%m-%d %H:%M")
    quien = getattr(actor, "username", "sistema")
    linea = f"[{sello}] {quien}: {accion} {extra or ''}".strip()
    lead.nota_interna = f"{lead.nota_interna}\n{linea}".strip() if lead.nota_interna else linea
    lead.save(update_fields=["nota_interna"])
