import logging
import re
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING

from django.utils import timezone
from django.conf import settings

from apps.cotizador.services import cotizar_lead
from apps.leads.models import Lead
from apps.leads.route import remove_stop, replace_lead_route, sync_legacy_endpoints

from .data_extractor import (
    extract_lead_data,
    extract_route_locations,
    has_explicit_floor_reference,
    normalize_district,
)
from .conversation_policy import (
    BOOKING,
    apply_quote_defaults,
    booking_missing_fields,
    decide_conversation,
    quote_missing_fields,
)
from .history import conversation_examples_for, format_examples_for_prompt
from .openai_client import extract_lead_with_ai, generate_reply
from .prompts import CONVERSATIONAL_RESPONSE_SYSTEM_PROMPT, POST_RESERVATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def delta_shadow_enabled():
    return settings.AI_DELTA_SHADOW_MODE

BASE_QUESTIONS = [
    ("tipo_servicio", "Hola, que deseas trasladar?"),
    (
        "datos_ruta",
        "Cual es el distrito de partida y llegada?",
    ),
]

MOVING_QUESTIONS = [
    (
        "datos_niveles",
        "De que piso sale y a que piso llega?",
    ),
    (
        "lista_objetos",
        "Que cosas llevarias? Puedes mandarme una lista o fotos. Avisame si hay algo pesado, como refri de dos puertas, ropero o aparador.",
    ),
    (
        "incluye_personal_carga",
        "Lo necesitas solo con transporte o tambien con personal para cargar y descargar?",
    ),
    (
        "modalidad_servicio",
        "Lo llevarias sin embalaje, con embalaje basico (solo lo mas fragil), "
        "embalaje de muebles y artefactos, o embalaje full "
        "(muebles, artefactos y empaquetado de cajas)?",
    ),
    (
        "requiere_desarmado",
        "Hay muebles que tengamos que desarmar y volver a armar?",
    ),
]

CARGO_QUESTIONS = [
    ("lista_objetos", "Que tipo de carga es y cuanta cantidad aproximadamente?"),
    (
        "dimension_carga",
        "Tienes un peso aproximado o medidas/volumen? Con eso veo que camion conviene.",
    ),
    (
        "datos_niveles",
        "De que piso sale y a que piso llega?",
    ),
]

TRUCK_ACCESS_QUESTION = (
    "acceso_camion",
    "En el origen y destino, el camion puede acercarse a la puerta o hay que trasladar las cosas cierta distancia?",
)

FINAL_QUOTE_QUESTIONS = [
    ("fecha_servicio", "Para que fecha lo necesitas?"),
]

RESERVATION_QUESTIONS = [
    (
        "datos_cliente",
        "Buenazo. A nombre de quien registramos el servicio y cual es su DNI?",
    ),
    (
        "datos_direcciones",
        "Me indica la direccion exacta de partida y de llegada? "
        "Necesito calle o avenida y numero, o manzana y lote.",
    ),
    ("fecha_hora", "Me indica la fecha y hora del traslado?"),
]

PRICING_FIELDS = {
    "tipo_servicio",
    "distrito_origen",
    "distrito_destino",
    "piso_origen",
    "piso_destino",
    "ascensor_origen",
    "ascensor_destino",
    "lista_objetos",
    "objetos_pesados",
    "incluye_personal_carga",
    "modalidad_servicio",
    "requiere_desarmado",
    "acceso_origen",
    "acceso_destino",
    "camion_llega_origen",
    "camion_llega_destino",
    "distancia_carga_origen_m",
    "distancia_carga_destino_m",
    "peso_carga_kg",
    "volumen_carga_m3",
    "tipo_camion",
    "capacidad_camion",
}

LOCAL_LIMA_CALLAO_AREAS = {
    "ancon",
    "ate",
    "barranco",
    "bellavista",
    "brena",
    "callao",
    "carabayllo",
    "carmen de la legua reynoso",
    "cercado de lima",
    "chaclacayo",
    "chorrillos",
    "cieneguilla",
    "comas",
    "el agustino",
    "independencia",
    "jesus maria",
    "la molina",
    "la perla",
    "la punta",
    "la victoria",
    "lima",
    "lince",
    "los olivos",
    "lurigancho",
    "lurigancho chosica",
    "magdalena",
    "magdalena del mar",
    "mi peru",
    "miraflores",
    "pachacamac",
    "pucusana",
    "pueblo libre",
    "puente piedra",
    "punta hermosa",
    "punta negra",
    "rimac",
    "san bartolo",
    "san borja",
    "san isidro",
    "san juan de lurigancho",
    "san juan de miraflores",
    "san luis",
    "san martin de porres",
    "san miguel",
    "santa anita",
    "santa maria del mar",
    "santa rosa",
    "santiago de surco",
    "surco",
    "surquillo",
    "ventanilla",
    "villa el salvador",
    "villa maria del triunfo",
}

PAYMENT_INFORMATION = (
    "Puedes pagar por Yape al 996797907, a nombre de Walter Escobar, "
    "o mediante deposito o transferencia a la cuenta BCP 19409223621088."
)


def handle_incoming_message(cliente, message, canonical_context=None, generation_id=None):
    lead = _get_active_lead(cliente)
    account_holder_reply = _account_holder_information(message)
    if account_holder_reply:
        return account_holder_reply
    if _asks_about_payment(message):
        return PAYMENT_INFORMATION

    if (
        lead.etapa_conversacion == Lead.ETAPA_RESERVA
        and lead.horario_por_confirmar
    ):
        if _is_acceptance(message):
            lead.horario_por_confirmar = False
            lead.save(update_fields=["horario_por_confirmar"])
            return _complete_reservation(lead)
        if _is_rejection(message):
            lead.fecha_servicio = None
            lead.horario_servicio = ""
            lead.horario_por_confirmar = False
            lead.save(
                update_fields=[
                    "fecha_servicio",
                    "horario_servicio",
                    "horario_por_confirmar",
                ]
            )
            return "De acuerdo. Que fecha y hora prefieres?"
        lead.horario_por_confirmar = False
        lead.save(update_fields=["horario_por_confirmar"])

    if lead.etapa_conversacion == Lead.ETAPA_RESERVADO:
        return _answer_post_reservation_question(lead, message)

    packing_info = _packing_information(message)
    if packing_info:
        next_question = _next_missing_question(lead)
        if next_question:
            return f"{packing_info} {next_question}"
        return packing_info

    packaging_inquiry = _handle_packaging_inquiry(lead, message)
    if packaging_inquiry:
        return packaging_inquiry

    availability_reply = _handle_availability_inquiry(lead, message)
    if availability_reply:
        return availability_reply

    # Run AI extraction early so it's available for both COTIZADO and normal flows.
    if canonical_context is not None:
        recent_history = [
            {"author": entry.author, "text": entry.text}
            for entry in canonical_context.entries
        ]
    else:
        recent_history = list(
            lead.cliente.conversaciones.order_by("-fecha").values_list(
                "mensaje_entrada",
                "mensaje_salida",
            )[:4]
        )
        recent_history.reverse()
    ai_extracted = extract_lead_with_ai(message, lead, recent_history)
    preview_extracted = extract_lead_data(message)
    if (
        delta_shadow_enabled()
        and canonical_context is not None
    ):
        try:
            from apps.whatsapp.models import MensajeWhatsApp
            from .delta_extractor import queue_delta_shadow

            trigger = MensajeWhatsApp.objects.only("conversacion_id").get(
                pk=canonical_context.trigger_message_id
            )
            queue_delta_shadow(
                trigger_message_id=trigger.id,
                legacy_extraction=preview_extracted,
            )
        except Exception as exc:
            logger.warning(
                "AI delta shadow skipped error_type=%s", type(exc).__name__
            )
    extracted_locations = extract_route_locations(message)
    preview_extracted.update(_extract_route_correction(message))
    route_with_stops = len(extracted_locations) > 2 or _route_with_stops(message)
    has_explicit_pricing_update = route_with_stops or any(
        field in PRICING_FIELDS and value not in (None, "")
        for field, value in preview_extracted.items()
    )

    if lead.estado == Lead.COTIZADO:
        closure_reply = _handle_conversation_closure(lead, message)
        if closure_reply:
            logger.info(
                "Rechazo detectado: lead %s marcado PERDIDO", lead.id,
            )
            return closure_reply
        price_reply = _handle_price_conversation(lead, message)
        if price_reply:
            return price_reply
        if _is_acceptance(message):
            from apps.cotizador.commercial import aceptar_cotizacion_para_lead
            aceptar_cotizacion_para_lead(lead)
            lead.etapa_conversacion = Lead.ETAPA_RESERVA
            lead.esperando_motivo_no_reserva = False
            lead.save(
                update_fields=[
                    "etapa_conversacion",
                    "esperando_motivo_no_reserva",
                ]
            )
            return _next_missing_question(lead)

        # If no price/closure/acceptance matched, check AI for new quote intent.
        if _ai_detects_new_quote(ai_extracted):
            logger.info(
                "AI nueva cotizacion: lead %s -> PERDIDO, se crea nuevo lead",
                lead.id,
            )
            lead.estado = Lead.PERDIDO
            lead.motivo_perdida = "Cliente inicio nueva cotizacion"
            lead.save(update_fields=["estado", "motivo_perdida"])
            return handle_incoming_message(cliente, message)

        # Safety guard: if nothing matched in COTIZADO, return current price
        # instead of falling through to cotizar_lead which would restore max price.
        # Exclude RESERVA stage — those leads still need normal data processing.
        if lead.etapa_conversacion != Lead.ETAPA_RESERVA and not has_explicit_pricing_update:
            price = lead.precio_cotizado or lead.precio_estimado_max
            if price is not None:
                return (
                    f"En que puedo ayudarte? El precio actual del servicio es "
                    f"S/ {price:.0f}. "
                    "Te gustaria reservarlo o tienes alguna pregunta?"
                )

    expected_field = _next_missing_field(lead)
    extracted = preview_extracted

    correction = _extract_route_correction(message)
    if correction:
        extracted.update(correction)

    if ai_extracted and ai_extracted["campos_detectados"]:
        for field, value in ai_extracted["campos_detectados"].items():
            if field in {"piso_origen", "piso_destino"} and not has_explicit_floor_reference(message):
                continue
            if value not in ("", None) and not extracted.get(field):
                extracted[field] = value
    _restrict_elevator_evidence_to_locations(extracted, extracted_locations)
    if route_with_stops:
        extracted.pop("distrito_origen", None)
        extracted.pop("distrito_destino", None)

    _apply_contextual_answer(extracted, expected_field, message, lead)
    normalized_message = _canonical_place(message)
    if any(term in normalized_message for term in ("piso", "ascensor", "escalera", "puerta a calle")):
        _extract_contextual_levels(extracted, message, lead)
    if "camion" in normalized_message and any(
        term in normalized_message for term in ("puerta", "acerc", "metros", "llega", "entra")
    ):
        _extract_contextual_truck_access(extracted, message, lead)
    validation_reply = _validate_reservation_input(lead, extracted, expected_field, message)
    if validation_reply:
        return validation_reply
    pricing_changed = False
    rephrase_now = None
    for field, value in extracted.items():
        if value not in ("", None):
            if field == "cliente_nombre":
                cliente.nombre = value
                cliente.save(update_fields=["nombre"])
                continue
            if (
                field == "tipo_servicio"
                and lead.tipo_servicio
                and expected_field != "tipo_servicio"
            ):
                continue
            if field == "fecha_servicio":
                lead.fecha_por_confirmar = False
            if field in PRICING_FIELDS and getattr(lead, field) != value:
                pricing_changed = True
            setattr(lead, field, value)

    defaulted_fields = apply_quote_defaults(lead)
    if defaulted_fields:
        pricing_changed = True
    if lead.etapa_conversacion == Lead.ETAPA_COTIZACION and not lead.fecha_servicio:
        lead.fecha_por_confirmar = True

    if pricing_changed:
        _clear_quote(lead)
    if lead.etapa_conversacion != Lead.ETAPA_RESERVA:
        lead.estado = Lead.EN_CONVERSACION
    lead.save()
    if extracted_locations:
        _merge_endpoint_fields_into_locations(extracted_locations, extracted)
        replace_lead_route(lead, extracted_locations)
    else:
        sync_legacy_endpoints(lead, extracted.keys())
    removed_stop = _requested_stop_removal(message)
    if removed_stop:
        remove_stop(lead, removed_stop)
    question_answer = _answer_customer_question(lead, message)

    if route_with_stops:
        lead.estado = Lead.DATOS_INCOMPLETOS
        lead.atencion_humana = True
        lead.save(update_fields=["estado", "atencion_humana"])
        _mark_for_manual_quote(lead, "Ruta con una o más paradas intermedias")
        _log_decision(lead, "human_quote", extracted, False, True, ai_extracted is not None)
        return (
            "Veo que la ruta incluye una parada intermedia. Para no calcularla "
            "como un traslado directo, un asesor revisará la ruta completa y continuará la cotización."
        )

    if expected_field and not _field_complete(lead, expected_field):
        rephrase_now = _rephrase_if_unanswered(
            expected_field, extracted, message, lead
        )
    if rephrase_now:
        return f"{question_answer} {rephrase_now}" if question_answer else rephrase_now

    if lead.etapa_conversacion == Lead.ETAPA_RESERVA:
        if (
            expected_field == "fecha_hora"
            and extracted.get("fecha_servicio")
            and extracted.get("horario_servicio")
            and _mentions_weekday(message)
        ):
            lead.horario_por_confirmar = True
            lead.save(update_fields=["horario_por_confirmar"])
            return f"Confirmamos {_formatted_schedule(lead)}?"
        missing_question = _next_missing_question(lead)
        if missing_question:
            return missing_question
        return _complete_reservation(lead)

    missing_question = _next_missing_question(lead, message=message)
    if missing_question:
        lead.estado = Lead.DATOS_INCOMPLETOS
        lead.save(update_fields=["estado"])
        _log_decision(lead, "collect_quote", extracted, False, False, ai_extracted is not None)
        if question_answer:
            return f"{question_answer} {missing_question}"
        return missing_question

    if _route_requires_manual_review(lead):
        lead.estado = Lead.DATOS_INCOMPLETOS
        lead.atencion_humana = True
        lead.save(update_fields=["estado", "atencion_humana"])
        _mark_for_manual_quote(lead, "Ruta fuera de Lima o Callao")
        return (
            "Como la ruta incluye una ciudad fuera de Lima o Callao, necesito "
            "revisar kilometraje, peajes y tiempo de viaje antes de darte un precio. "
            "Ya tengo los datos del servicio y un asesor continuara la cotizacion."
        )

    if lead.modalidad_servicio == "embalaje full":
        lead.estado = Lead.DATOS_INCOMPLETOS
        lead.atencion_humana = True
        lead.save(update_fields=["estado", "atencion_humana"])
        _mark_for_manual_quote(lead, "Embalaje full requiere revisión humana")
        return (
            "Para cotizar embalaje full necesitamos fotos de todo lo que deseas "
            "embalar. Un asesor revisara el volumen y te indicara el monto."
        )

    cotizacion = cotizar_lead(lead)
    lead.precio_estimado_min = cotizacion.precio_min
    lead.precio_estimado_max = cotizacion.precio_max
    lead.precio_recomendado = cotizacion.precio_recomendado
    lead.precio_cotizado = cotizacion.precio_max
    lead.estado = Lead.COTIZADO
    lead.save(
        update_fields=[
            "precio_estimado_min",
            "precio_estimado_max",
            "precio_recomendado",
            "precio_cotizado",
            "estado",
        ]
    )
    _log_decision(lead, "quote_ready", extracted, True, False, ai_extracted is not None)
    response = _price_offer_message(lead)
    if canonical_context is not None and generation_id is not None:
        from apps.cotizador.commercial import crear_cotizacion_automatica
        from apps.whatsapp.models import ConversacionWhatsApp
        conversation = ConversacionWhatsApp.objects.filter(lead=lead).exclude(
            estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA
        ).order_by("-ultima_actividad").first()
        if conversation:
            crear_cotizacion_automatica(
                conversation,
                cotizacion,
                response,
                source_key=f"bot-generation:{generation_id}",
            )
    return response


def _mark_for_manual_quote(lead, reason):
    from apps.whatsapp.domain import enviar_a_cotizar
    from apps.whatsapp.models import ConversacionWhatsApp
    conversation = ConversacionWhatsApp.objects.filter(lead=lead).exclude(
        estado_atencion=ConversacionWhatsApp.ATENCION_CERRADA
    ).order_by("-ultima_actividad").first()
    if conversation:
        enviar_a_cotizar(conversation.id, None, reason, conversation.datos_faltantes)


def handle_image_inventory(cliente, analysis):
    lead = _get_active_lead(cliente)
    objects = ", ".join(analysis.get("objetos", []))
    heavy_items = ", ".join(analysis.get("objetos_pesados", []))
    if objects:
        lead.lista_objetos = objects
    if heavy_items:
        lead.objetos_pesados = heavy_items
    _clear_quote(lead)
    lead.estado = Lead.DATOS_INCOMPLETOS
    lead.save()

    summary = analysis.get("resumen") or objects
    next_question = _next_missing_question(lead)
    confirmation = f"En la foto veo {summary}. Lo tomo como inventario; avisame si falta algo."
    if next_question:
        return f"{confirmation} {next_question}"
    return confirmation


def next_missing_question_for(cliente):
    lead = _get_active_lead(cliente)
    return _next_missing_question(lead)


def _get_active_lead(cliente):
    lead = (
        cliente.leads.exclude(estado__in=[Lead.CERRADO, Lead.PERDIDO])
        .order_by("-fecha_creacion")
        .first()
    )
    if lead:
        return lead
    return Lead.objects.create(cliente=cliente, estado=Lead.NUEVO)


def _next_missing_question(lead, message=""):
    decision = decide_conversation(
        lead,
        requires_truck_access=bool(lead.lista_objetos and _requires_truck_access(lead)),
    )
    if not decision.missing_relevant_data:
        return None
    fallback = _grouped_question(decision, message=message)
    return _generate_decision_reply(lead, message, decision, fallback) or fallback


def _next_missing_field(lead):
    decision = decide_conversation(
        lead,
        requires_truck_access=bool(lead.lista_objetos and _requires_truck_access(lead)),
    )
    return {
        "collect_service": "tipo_servicio",
        "collect_route": "datos_ruta",
        "collect_load": "lista_objetos" if "lista_objetos" in decision.missing_relevant_data else "dimension_carga",
        "collect_access": (
            "acceso_camion"
            if decision.missing_relevant_data and all(
                field in {"camion_llega_origen", "camion_llega_destino"}
                or field.endswith("_acceso_camion")
                for field in decision.missing_relevant_data
            )
            else "datos_niveles"
        ),
        "collect_booking": _booking_expected_field(decision.missing_relevant_data),
    }.get(decision.goal)


def _booking_expected_field(missing):
    fields = set(missing)
    if "cliente_nombre" in fields:
        return "datos_cliente"
    if fields & {"direccion_origen", "direccion_destino"} or any(field.endswith("_direccion") for field in fields):
        return "datos_direcciones"
    if fields & {"fecha_servicio", "horario_servicio"}:
        return "fecha_hora"
    return None


def _merge_endpoint_fields_into_locations(locations, extracted):
    """Keep reliable flat extraction when creating the canonical route."""
    mappings = (
        (locations[0], "origen"),
        (locations[-1], "destino"),
    )
    field_map = {
        "direccion": "direccion_{}",
        "piso": "piso_{}",
        "ascensor": "ascensor_{}",
        "acceso_camion": "camion_llega_{}",
        "distancia_acarreo": "distancia_carga_{}_m",
        "observaciones_acceso": "acceso_{}",
    }
    for location, suffix in mappings:
        for target, source_template in field_map.items():
            value = extracted.get(source_template.format(suffix))
            if value not in (None, ""):
                location[target] = value


def _restrict_elevator_evidence_to_locations(extracted, locations):
    """Do not spread one endpoint's elevator evidence across a two-point route."""
    if len(locations) != 2:
        return
    elevator_values = [locations[0].get("ascensor"), locations[-1].get("ascensor")]
    if not any(value is not None for value in elevator_values):
        return
    for suffix, value in zip(("origen", "destino"), elevator_values):
        field = f"ascensor_{suffix}"
        if value is None:
            extracted.pop(field, None)
        else:
            extracted[field] = value


def _grouped_question(decision, message=""):
    missing = set(decision.missing_relevant_data)
    if decision.phase == BOOKING:
        if "cliente_nombre" in missing:
            return "¿A nombre de quién coordinamos el servicio?"
        location_addresses = [field for field in missing if field.endswith("_direccion")]
        if location_addresses:
            return "¿Cuáles son las direcciones exactas de recojo, paradas y entrega?"
        if {"direccion_origen", "direccion_destino"} <= missing:
            return "¿Cuáles son las direcciones exactas de recojo y entrega?"
        if "direccion_origen" in missing:
            return "¿Cuál es la dirección exacta de recojo?"
        if "direccion_destino" in missing:
            return "¿Cuál es la dirección exacta de entrega?"
        if {"fecha_servicio", "horario_servicio"} <= missing:
            return "¿Qué fecha y hora prefieres para el traslado?"
        if "fecha_servicio" in missing:
            return "¿Qué fecha prefieres para el traslado?"
        return "¿A qué hora prefieres el traslado?"
    if decision.goal == "collect_service":
        return "Hola, que deseas trasladar?"
    if decision.goal == "collect_route":
        if any(field.endswith("_distrito") for field in missing):
            return "¿En qué distrito queda cada punto de la ruta?"
        if {"distrito_origen", "distrito_destino"} <= missing:
            return "Cual es el distrito de partida y llegada?"
        if "distrito_origen" in missing:
            return "¿De qué distrito sale?"
        return "¿A qué distrito llega?"
    if decision.goal == "collect_load":
        if "lista_objetos" in missing:
            return "Cuéntame brevemente qué cosas vas a trasladar, sobre todo los muebles o artefactos grandes."
        return "¿Tienes un peso aproximado o las medidas de la carga?"
    if decision.goal == "collect_access":
        floors = missing & {"piso_origen", "piso_destino"}
        elevators = missing & {"ascensor_origen", "ascensor_destino"}
        truck = missing & {"camion_llega_origen", "camion_llega_destino"}
        floor_orders = {
            int(field.split("_")[1])
            for field in missing
            if field.startswith("ubicacion_") and field.endswith("_piso")
        }
        elevator_orders = {
            int(field.split("_")[1])
            for field in missing
            if field.startswith("ubicacion_") and field.endswith("_ascensor")
        }
        locations = decision.known_data.get("ubicaciones", [])
        origin_name = locations[0].get("distrito") if locations else "el origen"
        destination_name = locations[-1].get("distrito") if locations else "el destino"
        if len(decision.known_data.get("ubicaciones", [])) > 2 and any(
            field.endswith(("_piso", "_ascensor")) for field in missing
        ):
            return "¿En qué piso está cada punto de la ruta y tienen ascensor?"
        if floors or elevators or any(field.endswith(("_piso", "_ascensor")) for field in missing):
            if floors == {"piso_origen"} or floor_orders == {0}:
                question = "De que piso sale y hay ascensor en el origen?"
            elif floors == {"piso_destino"} or floor_orders == {1}:
                question = "A que piso llega y hay ascensor en el destino?"
            elif not floors and (elevators == {"ascensor_origen"} or elevator_orders == {0}):
                question = f"¿En {origin_name} tienen ascensor?"
            elif not floors and (elevators == {"ascensor_destino"} or elevator_orders == {1}):
                question = f"¿En {destination_name} tienen ascensor?"
            elif not floors and elevators:
                question = "En origen y destino, tienen ascensor?"
            else:
                question = "¿En qué pisos están ambos lugares y tienen ascensor?"
            if truck or any(field.endswith("_acceso_camion") for field in missing):
                question += " " + _truck_access_question(decision, message)
            return question
        if truck or any(field.endswith("_acceso_camion") for field in missing):
            return _truck_access_question(decision, message)
    return "¿Me das un poco más de detalle del servicio?"


def _truck_access_question(decision, message):
    normalized = _canonical_place(message)
    truck_clause = normalized.split("camion", 1)[1] if "camion" in normalized else ""
    ambiguous_distance = (
        any(term in truck_clause for term in ("cuadra", "estacio", "metros"))
        and not any(term in truck_clause for term in ("origen", "destino", "ambos", "los dos"))
    )
    if ambiguous_distance:
        locations = decision.known_data.get("ubicaciones", [])
        districts = [item.get("distrito") for item in locations if item.get("distrito")]
        if len(districts) >= 2:
            return (
                f"Y lo de estacionarse a una cuadra, ¿corresponde a "
                f"{districts[0]}, {districts[-1]} o ambos?"
            )
        return "Y lo de estacionarse a una cuadra, ¿a cuál lugar corresponde?"
    return "¿El camión puede estacionarse cerca para cargar y descargar?"


def _generate_decision_reply(lead, message, decision, fallback):
    if not message:
        return None
    context = (
        f"Mensaje actual: {message}\n"
        f"Fase: {decision.phase}\nObjetivo: {decision.goal}\n"
        f"Hechos confirmados: {decision.known_data}\n"
        f"Datos relevantes faltantes: {list(decision.missing_relevant_data)}\n"
        f"Respuesta fallback autorizada: {fallback}\n"
        "Responde brevemente. Mantén exactamente el objetivo autorizado."
    )
    return generate_reply(
        [{"role": "user", "content": context}],
        system_prompt=CONVERSATIONAL_RESPONSE_SYSTEM_PROMPT,
    )


REPHRASED_QUESTIONS = {
    "incluye_personal_carga": [
        "Disculpa no te entendi bien. Es solo el servicio de transporte o necesitas personal para cargar y descargar?",
        "Disculpa, no me quedo claro. Prefieres solo el movil o requieres ayuda con la carga y descarga?",
        "Perdon, no entendi bien tu respuesta. Quieres que vaya personal a cargar tus cosas o solo necesitas el traslado?",
    ],
    "modalidad_servicio": [
        "Disculpa no entendi. Necesitas que protejamos tus cosas con embalaje o lo llevas tal cual?",
        "Perdon, no me quedo claro. Quieres algun tipo de embalaje o prefieres sin embalaje?",
    ],
    "requiere_desarmado": [
        "Disculpa, no me quedo claro. Hay algun mueble que necesite desarmarse para el traslado?",
        "Perdon, no entendi. Tienes muebles que requieran desarmado y armado?",
    ],
    "lista_objetos": [
        "Disculpa, no capte bien. Que cosas vas a llevar? Puedes describirmelo por favor.",
        "Perdon, no entendi. Podrias decirme que cosas, objetos o muebles llevaras?",
    ],
    "datos_niveles": [
        "Disculpa, no me quedo claro los pisos. Me podrias repetir de que piso a que piso seria?",
        "Perdon, no identifique bien los pisos. Me dices de que piso sales y a cual llegas?",
    ],
    "datos_ruta": [
        "Disculpa, no identifique bien los distritos. Me repites de donde a donde seria el traslado?",
    ],
}


def _questions_for(lead):
    field = _next_missing_field(lead)
    if not field:
        return []
    return [(field, _next_missing_question(lead))]


def _field_complete(lead, field):
    if field == "datos_cliente":
        return bool(lead.cliente.nombre)
    if field == "cliente_nombre":
        return bool(lead.cliente.nombre)
    if field == "datos_ruta":
        return bool(lead.distrito_origen and lead.distrito_destino)
    if field == "datos_niveles":
        return (
            lead.piso_origen is not None
            and (lead.piso_origen <= 1 or lead.ascensor_origen is not None)
            and lead.piso_destino is not None
            and (lead.piso_destino <= 1 or lead.ascensor_destino is not None)
        )
    if field == "acceso_camion":
        return (
            lead.camion_llega_origen is not None
            and lead.camion_llega_destino is not None
        )
    if field == "dimension_carga":
        return lead.peso_carga_kg is not None or lead.volumen_carga_m3 is not None
    if field == "datos_direcciones":
        return bool(
            _is_specific_address(lead.direccion_origen)
            and _is_specific_address(lead.direccion_destino)
        )
    if field == "fecha_hora":
        return bool(
            lead.fecha_servicio
            and _parse_schedule_time(lead.horario_servicio) is not None
        )
    if field == "fecha_servicio":
        if lead.etapa_conversacion == Lead.ETAPA_RESERVA:
            return bool(lead.fecha_servicio)
        return bool(lead.fecha_servicio or lead.fecha_por_confirmar)
    if field == "modalidad_servicio":
        return lead.modalidad_servicio in (
            "sin embalaje",
            "embalaje basico",
            "embalaje de muebles y artefactos",
            "embalaje full",
        )
    value = getattr(lead, field)
    return value is not None if isinstance(value, bool) else bool(value)


def _apply_contextual_answer(extracted, expected_field, message, lead):
    answer = " ".join(message.strip(" .,").split())
    if not answer:
        return

    if expected_field == "tipo_servicio":
        if extracted.get("tipo_servicio"):
            return
        if extracted.get("lista_objetos"):
            extracted["tipo_servicio"] = _infer_service_from_objects(answer)
            return
        if len(answer) > 2 and not _is_greeting(answer):
            extracted["lista_objetos"] = answer
            extracted["tipo_servicio"] = _infer_service_from_objects(answer)
        return

    if expected_field == "datos_ruta":
        _extract_contextual_route(extracted, answer, lead)
        return

    if expected_field == "datos_cliente":
        _extract_reservation_customer(extracted, answer, lead)
        return

    if expected_field == "datos_direcciones":
        _extract_reservation_addresses(extracted, answer, lead)
        return

    if expected_field == "fecha_hora":
        return

    if expected_field == "fecha_servicio":
        # "Manana" answers the date question; it must not also skip the time question.
        if answer.lower() in {"manana", "mañana"}:
            extracted.pop("horario_servicio", None)
        return

    if expected_field == "datos_niveles":
        _extract_contextual_levels(extracted, answer, lead)
        return

    if expected_field == "acceso_camion":
        _extract_contextual_truck_access(extracted, answer, lead)
        return

    if expected_field == "dimension_carga":
        return

    if expected_field == "lista_objetos" and not extracted.get("lista_objetos"):
        if _refers_only_to_photo(answer):
            return
        if any(term in _canonical_place(answer) for term in ("piso", "ascensor", "escalera", "camion", "puerta")):
            return
        extracted["lista_objetos"] = answer
        return

    if expected_field == "incluye_personal_carga" and "incluye_personal_carga" not in extracted:
        if _only_yes_or_no(answer):
            extracted["incluye_personal_carga"] = _answer_is_yes(answer)
        elif _answer_is_transport_only(answer):
            extracted["incluye_personal_carga"] = False
        return

    if expected_field == "modalidad_servicio":
        if extracted.get("modalidad_servicio"):
            return
        lowered = answer.lower()
        if any(term in lowered for term in ["sin embalaje", "no quiero embalaje", "no", "sin"]):
            extracted["modalidad_servicio"] = "sin embalaje"
            return
        if "con embalaje" in lowered or "embalaje" in lowered:
            extracted["modalidad_servicio"] = "embalaje basico"
            return
        wants_packing = any(
            term in lowered
            for term in [
                "si", "sí", "quiero", "necesito",
                "claro", "dale", "ok", "obvio",
            ]
        )
        if wants_packing:
            extracted["modalidad_servicio"] = "embalaje_pendiente"
        return

    if expected_field == "requiere_desarmado" and "requiere_desarmado" not in extracted:
        extracted["requiere_desarmado"] = _answer_is_yes(answer)
        return

    if expected_field in {"direccion_origen", "direccion_destino", "dni_reserva"}:
        extracted[expected_field] = answer
        return

    if expected_field == "cliente_nombre" and not extracted.get("cliente_nombre"):
        extracted["cliente_nombre"] = answer.title()
        return

    if expected_field == "horario_servicio" and not extracted.get("horario_servicio"):
        extracted["horario_servicio"] = answer


LIMA_DISTRICTS_LOWER = {
    "ancon", "ate", "barranco", "bellavista", "brena", "callao",
    "carmen de la legua reynoso", "carabayllo", "cercado de lima",
    "chaclacayo", "chorrillos", "cieneguilla", "comas", "el agustino",
    "independencia", "jesús maría", "la molina", "la perla", "la punta",
    "la victoria", "lince", "los olivos", "lurigancho", "lurin",
    "magdalena del mar", "miraflores", "mi peru", "padre las casas",
    "pueblo libre", "puente piedra", "punta hermosa", "punta negra",
    "rimac", "san bartolo", "san borja", "san isidro",
    "san juan de lurigancho", "san juan de miraflores", "san luis",
    "san martin de porres", "san miguel", "santa anita",
    "santa maria del mar", "santa rosa", "santiago de surco",
    "surco", "surquillo", "ventanilla", "villa el salvador",
    "villa maria del triunfo",
}


def _is_known_district(value):
    return value and value.lower() in LIMA_DISTRICTS_LOWER


def _extract_contextual_route(extracted, answer, lead):
    if extracted.get("distrito_origen") or extracted.get("distrito_destino"):
        return
    cleaned = answer.strip(" .,")
    match = re.match(r"(.+?)\s+(?:y|\ba\b|hasta)\s+(.+)", cleaned, flags=re.IGNORECASE)
    if match:
        origin = normalize_district(match.group(1))
        destination = normalize_district(match.group(2))
        if origin and destination:
            extracted["distrito_origen"] = origin
            extracted["distrito_destino"] = destination
    elif not lead.distrito_origen and len(cleaned) <= 120:
        candidate = normalize_district(cleaned)
        if candidate and _is_known_district(candidate):
            extracted["distrito_origen"] = candidate
    elif not lead.distrito_destino and len(cleaned) <= 120:
        candidate = normalize_district(cleaned)
        if candidate and _is_known_district(candidate):
            extracted["distrito_destino"] = candidate


def _extract_reservation_customer(extracted, answer, lead):
    dni_match = re.search(r"\b(\d{8})\b", answer)
    if dni_match:
        extracted["dni_reserva"] = dni_match.group(1)
    if not lead.cliente.nombre and not extracted.get("cliente_nombre"):
        name = re.sub(r"\b(?:dni\s*)?\d{8}\b", "", answer, flags=re.IGNORECASE)
        name = re.sub(r"\b(?:mi nombre es|me llamo|soy)\b", "", name, flags=re.IGNORECASE)
        name = " ".join(name.strip(" ,.-").split())
        if re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñ ]{2,80}", name):
            extracted["cliente_nombre"] = name.title()


def _extract_reservation_addresses(extracted, answer, lead):
    origin = _labeled_address(answer, ("partida", "origen", "recojo"))
    destination = _labeled_address(answer, ("llegada", "destino", "entrega"))

    if not origin and not destination:
        parts = re.split(
            r"\s*(?:\n|;|\||/|\s+y\s+(?=(?:av(?:\.|enida)?|jr(?:\.|iron)?|"
            r"calle|pasaje|carretera|mz\.?|manzana)\b))\s*",
            answer,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        if len(parts) == 2:
            origin, destination = parts
        elif not lead.direccion_origen:
            origin = answer
        else:
            destination = answer

    if origin:
        extracted["direccion_origen"] = origin.strip(" ,.-")
    if destination:
        extracted["direccion_destino"] = destination.strip(" ,.-")


def _labeled_address(answer, labels):
    labels_pattern = "|".join(labels)
    other_labels = "partida|origen|recojo|llegada|destino|entrega"
    match = re.search(
        rf"\b(?:{labels_pattern})\s*[:,-]?\s*(.+?)(?=\s+\b(?:{other_labels})\b\s*[:,-]?|$)",
        answer,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _validate_reservation_input(lead, extracted, expected_field, answer=""):
    if lead.etapa_conversacion != Lead.ETAPA_RESERVA:
        return None

    if expected_field == "datos_direcciones":
        invalid = []
        for field in ("direccion_origen", "direccion_destino"):
            value = extracted.get(field)
            if value and not _is_specific_address(value):
                invalid.append(field)
                extracted.pop(field, None)
        if invalid:
            places = []
            if "direccion_origen" in invalid:
                places.append("partida")
            if "direccion_destino" in invalid:
                places.append("llegada")
            return (
                f"Necesito una direccion mas precisa de {' y '.join(places)}: "
                "calle o avenida y numero, o manzana y lote."
            )

    if expected_field == "fecha_hora":
        candidate_date = extracted.get("fecha_servicio") or lead.fecha_servicio
        candidate_schedule = extracted.get("horario_servicio") or lead.horario_servicio
        if extracted.get("horario_servicio") and _parse_schedule_time(
            extracted["horario_servicio"]
        ) is None:
            extracted.pop("horario_servicio", None)
            return "Necesito una hora exacta, por ejemplo 9:00 am o 3:30 pm."
        if candidate_date and candidate_date < timezone.localdate():
            extracted.pop("fecha_servicio", None)
            extracted.pop("horario_servicio", None)
            return "Esa fecha ya paso. Me indica una fecha y hora futuras?"
        schedule_time = _parse_schedule_time(candidate_schedule)
        if candidate_date and schedule_time:
            scheduled = timezone.make_aware(
                datetime.combine(candidate_date, schedule_time),
                timezone.get_current_timezone(),
            )
            if scheduled <= timezone.now():
                if _mentions_weekday(answer):
                    extracted["fecha_servicio"] = candidate_date + timedelta(days=7)
                    return None
                extracted.pop("fecha_servicio", None)
                extracted.pop("horario_servicio", None)
                lead.fecha_servicio = None
                lead.horario_servicio = ""
                lead.save(update_fields=["fecha_servicio", "horario_servicio"])
                return "Esa fecha u hora ya paso. Me indica una fecha y hora futuras?"
    return None


def _is_specific_address(value):
    normalized = _canonical_place(value)
    if not normalized or len(normalized) < 8:
        return False
    if normalized in LOCAL_LIMA_CALLAO_AREAS:
        return False
    has_number = bool(re.search(r"\b\d+[a-z]?\b", normalized))
    has_lot = bool(
        re.search(r"\b(?:mz|manzana|lote|lt|km)\s*[a-z0-9-]+\b", normalized)
    )
    return has_number or has_lot


def _parse_schedule_time(value):
    normalized = str(value or "").strip().lower().replace(".", "")
    for pattern in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            return datetime.strptime(normalized, pattern).time()
        except ValueError:
            continue
    return None


def _extract_contextual_levels(extracted, answer, lead):
    lowered = answer.lower()
    pair = _floor_pair_from_text(lowered)
    if pair:
        extracted["piso_origen"], extracted["piso_destino"] = pair
        return

    access_answer = _standalone_access_answer(lowered)
    if access_answer is not None:
        pending = []
        if (
            lead.piso_origen is not None
            and lead.piso_origen > 1
            and lead.ascensor_origen is None
        ):
            pending.append("origen")
        if (
            lead.piso_destino is not None
            and lead.piso_destino > 1
            and lead.ascensor_destino is None
        ):
            pending.append("destino")
        if len(pending) == 1:
            extracted[f"ascensor_{pending[0]}"] = access_answer
            return
        if len(pending) == 2:
            if "ambos" in lowered or "los dos" in lowered:
                extracted["ascensor_origen"] = access_answer
                extracted["ascensor_destino"] = access_answer
                return
            extracted["ascensor_origen"] = access_answer
            return

    origin_window = _location_window(lowered, ["sale", "origen", "partida"])
    destination_window = _location_window(lowered, ["llega", "destino", "entrega"])
    if not origin_window and not destination_window:
        floor = _floor_from_text(lowered)
        if floor is not None:
            extracted.pop("piso_origen", None)
            extracted.pop("piso_destino", None)
            if lead.piso_origen is None:
                extracted["piso_origen"] = floor
            elif lead.piso_destino is None:
                extracted["piso_destino"] = floor
    for suffix, window in [("origen", origin_window), ("destino", destination_window)]:
        if not window:
            continue
        floor = _floor_from_text(window)
        if floor is not None:
            extracted[f"piso_{suffix}"] = floor
        if any(term in window for term in ["escalera", "sin ascensor", "no hay ascensor"]):
            extracted[f"ascensor_{suffix}"] = False
        elif "ascensor" in window:
            extracted[f"ascensor_{suffix}"] = True

    if "ambos" in lowered or "los dos" in lowered:
        if "escalera" in lowered:
            extracted["ascensor_origen"] = False
            extracted["ascensor_destino"] = False
        elif "ascensor" in lowered:
            extracted["ascensor_origen"] = True
            extracted["ascensor_destino"] = True

    if not any(field in extracted for field in ["piso_origen", "piso_destino"]):
        floor = _floor_from_text(lowered)
        if floor is not None:
            if lead.piso_origen is None:
                extracted["piso_origen"] = floor
            elif lead.piso_destino is None:
                extracted["piso_destino"] = floor

def _extract_contextual_truck_access(extracted, answer, lead):
    lowered = answer.lower()
    origin_window = _location_window(lowered, ["origen", "partida", "recojo"])
    destination_window = _location_window(lowered, ["destino", "llegada", "entrega"])
    for suffix, window in [("origen", origin_window), ("destino", destination_window)]:
        if not window:
            continue
        _apply_truck_access(extracted, suffix, window, answer)
    if "ambos" in lowered or "los dos" in lowered:
        reaches = not any(term in lowered for term in ["no llega", "lejos", "retirado"])
        extracted["camion_llega_origen"] = reaches
        extracted["camion_llega_destino"] = reaches
    elif _only_yes_or_no(lowered):
        value = _answer_is_yes(lowered)
        if lead.camion_llega_origen is None:
            extracted["camion_llega_origen"] = value
        if lead.camion_llega_destino is None:
            extracted["camion_llega_destino"] = value


def _apply_truck_access(extracted, suffix, window, answer):
    distance = re.search(r"\b(\d+)\s*(?:m|metros)\b", window)
    if distance:
        extracted[f"distancia_carga_{suffix}_m"] = int(distance.group(1))
        extracted[f"camion_llega_{suffix}"] = int(distance.group(1)) <= 20
    elif any(term in window for term in ["puerta", "cerca", "se estaciona"]):
        extracted[f"camion_llega_{suffix}"] = not any(
            term in window for term in ["no llega", "no entra", "lejos", "retirado"]
        )
    extracted[f"acceso_{suffix}"] = answer


def _location_window(text, labels):
    matches = [
        match
        for label in labels
        for match in re.finditer(rf"\b{re.escape(label)}\b", text)
    ]
    if not matches:
        return ""
    start = min(match.start() for match in matches)
    boundaries = [
        match.start()
        for match in re.finditer(
            r"\b(?:sale|origen|partida|recojo|llega|destino|llegada|entrega)\b",
            text,
        )
        if match.start() > start
    ]
    end = min(boundaries) if boundaries else len(text)
    return text[start:end].strip(" ,.;")


PISO_RE = r"p[ií]s[oó]"

PISO_TYPOS = {
    "psio": "piso",
    "psió": "piso",
    "pioso": "piso",
    "pisoo": "piso",
    "pizo": "piso",
}

def _fix_floor_text(text):
    lowered = text.lower()
    for typo, correct in PISO_TYPOS.items():
        lowered = lowered.replace(typo, correct)
    return lowered


def _floor_from_text(text):
    text = _fix_floor_text(text)
    numeric = re.search(
        rf"(?:\b(\d+)\s*(?:er|do|ro|to|toi|doi)?\s*{PISO_RE}\b|\b{PISO_RE}\s*(\d+)\b)",
        text,
    )
    if numeric:
        return int(numeric.group(1) or numeric.group(2))
    suffix = re.search(r"\b(\d{1,2})\s*(?:ero|er|ro|do|to|toi|doi)\b", text)
    if suffix:
        return int(suffix.group(1))
    bare = re.search(r"\b(\d{1,2})\b", text)
    if bare:
        return int(bare.group(1))
    ordinal_floors = {
        "primer piso": 1, "primero piso": 1,
        "segundo piso": 2, "tercer piso": 3, "tercero piso": 3,
        "cuarto piso": 4, "quinto piso": 5, "sexto piso": 6,
        "primero": 1, "primer": 1, "primer piso": 1,
        "segundo": 2, "tercer": 3, "tercero": 3,
        "cuarto": 4, "quinto": 5, "sexto": 6,
    }
    if "puerta a calle" in text:
        return 1
    lowered = text.lower()
    for label, floor in ordinal_floors.items():
        if label in lowered:
            return floor
    return None


SEPARATORS = r"(?:a|al|hasta|y)"


PISO_SUFFIX = r"(?:\s+[a-z]*piso)?"


def _floor_pair_from_text(text):
    text = _fix_floor_text(text)
    FLOOR_PREFIX = r"\b(\d+)\s*(?:ero|er|ro|do|to|toi|doi)?"
    MID = rf"\s+{SEPARATORS}\s+(?:\w+\s+)*?"
    numeric = re.search(
        rf"{FLOOR_PREFIX}{PISO_SUFFIX}{MID}"
        rf"(\d+)\s*(?:ero|er|ro|do|to|toi|doi)?{PISO_SUFFIX}\b",
        text,
    )
    if numeric:
        return int(numeric.group(1)), int(numeric.group(2))
    words = {
        "primero": 1, "primer": 1, "prime": 1,
        "segundo": 2, "segund": 2,
        "tercero": 3, "tercer": 3, "terce": 3,
        "cuarto": 4, "quinto": 5, "sexto": 6,
    }
    word_list = "|".join(words.keys())
    mixed = re.search(
        rf"{FLOOR_PREFIX}{PISO_SUFFIX}{MID}"
        rf"({word_list}){PISO_SUFFIX}\b",
        text,
    )
    if mixed:
        return int(mixed.group(1)), words[mixed.group(2)]
    WORD_PREFIX = rf"\b({word_list})"
    mixed2 = re.search(
        rf"{WORD_PREFIX}{PISO_SUFFIX}{MID}"
        rf"(\d+)\s*(?:ero|er|ro|do|to|toi|doi)?{PISO_SUFFIX}\b",
        text,
    )
    if mixed2:
        return words[mixed2.group(1)], int(mixed2.group(2))
    verbal = re.search(
        rf"{WORD_PREFIX}{MID}({word_list})\b",
        text,
    )
    if verbal:
        return words[verbal.group(1)], words[verbal.group(2)]
    return None


def _standalone_access_answer(text):
    normalized = _canonical_place(text)
    if any(term in normalized for term in ["escalera", "sin ascensor", "no hay ascensor"]):
        return False
    if any(term in normalized for term in ["ascensor", "elevador"]):
        return True
    return None


def _requires_truck_access(lead):
    objects = _canonical_place(lead.lista_objetos)
    if not objects:
        return False
    if lead.peso_carga_kg and lead.peso_carga_kg >= 300:
        return True
    if lead.volumen_carga_m3 and lead.volumen_carga_m3 >= 3:
        return True
    items = [
        item.strip()
        for item in re.split(r",|;|\n|\s+y\s+", objects)
        if item.strip() and "pendiente confirmar" not in item
    ]
    exceptional_items = ["piano", "caja fuerte", "refrigeradora de 2 puertas"]
    if (
        lead.tipo_servicio == "traslado pequeno"
        and len(items) <= 6
        and not any(item in objects for item in exceptional_items)
    ):
        return False
    effort_indicators = [
        "mudanza completa",
        "departamento completo",
        "casa completa",
        "oficina completa",
        "piano",
        "caja fuerte",
        "ropero",
        "aparador",
        "comoda",
        "sofa",
        "lavadora",
        "cama",
        "colchon",
    ]
    if any(indicator in objects for indicator in effort_indicators):
        return True
    box_count = re.search(r"\b(\d+)\s*cajas?\b", objects)
    if box_count and int(box_count.group(1)) >= 8:
        return True
    return len(items) > 6


def _question_for_missing_parts(lead, field, fallback):
    if field == "datos_cliente":
        if not lead.cliente.nombre and not lead.dni_reserva:
            return fallback
        if not lead.cliente.nombre:
            return "A nombre de quien registramos el servicio?"
        if not lead.dni_reserva:
            return "Me indica su DNI para el registro?"
    if field == "datos_direcciones":
        origin_ok = _is_specific_address(lead.direccion_origen)
        destination_ok = _is_specific_address(lead.direccion_destino)
        if not origin_ok and not destination_ok:
            return fallback
        if not origin_ok:
            return (
                "Me indica la direccion exacta de partida? "
                "Necesito calle o avenida y numero, o manzana y lote."
            )
        if not destination_ok:
            return (
                "Me indica la direccion exacta de llegada? "
                "Necesito calle o avenida y numero, o manzana y lote."
            )
    if field == "fecha_hora":
        if not lead.fecha_servicio and not _parse_schedule_time(lead.horario_servicio):
            return fallback
        if not lead.fecha_servicio:
            return "Me indica la fecha del traslado?"
        if not _parse_schedule_time(lead.horario_servicio):
            return "Me indica la hora exacta del traslado?"
    if field == "datos_ruta":
        if not lead.distrito_origen and not lead.distrito_destino:
            return fallback
        if not lead.distrito_origen:
            return "Cual es el distrito de partida?"
        if not lead.distrito_destino:
            return "Cual es el distrito de llegada?"
    if field == "datos_niveles":
        if lead.piso_origen is None and lead.piso_destino is None:
            return "De que piso sale y a que piso llega?"
        if lead.piso_origen is None:
            return "De que piso sale?"
        if lead.piso_destino is None:
            return "A que piso llega?"
        if (
            lead.piso_origen is not None
            and lead.piso_origen > 1
            and lead.ascensor_origen is None
        ):
            return "En el origen, la mudanza se realiza por ascensor o escaleras?"
        if (
            lead.piso_destino is not None
            and lead.piso_destino > 1
            and lead.ascensor_destino is None
        ):
            if lead.ascensor_origen is not None:
                return "En el destino, tambien es por ascensor o escaleras?"
            return "En el destino, la mudanza se realiza por ascensor o escaleras?"
    if field == "modalidad_servicio":
        if not lead.modalidad_servicio:
            return "Lo necesitas con embalaje o sin embalaje?"
        if lead.modalidad_servicio == "embalaje_pendiente":
            return (
                "Tenemos tres opciones: embalaje basico (solo lo mas fragil), "
                "embalaje de muebles y artefactos, o embalaje full "
                "(muebles, artefactos y empaquetado de cajas). Cual te interesa?"
            )
        return fallback
    if field == "acceso_camion":
        if lead.camion_llega_origen is None and lead.camion_llega_destino is None:
            return fallback
        if lead.camion_llega_origen is None:
            return "En el origen, el camion puede acercarse a la puerta?"
        if lead.camion_llega_destino is None:
            return "En el destino, el camion puede acercarse a la puerta?"
    return fallback


_rephrase_counters = {}


def _rephrase_if_unanswered(expected_field, extracted, message, lead):
    if expected_field not in (
        "incluye_personal_carga",
        "modalidad_servicio",
        "requiere_desarmado",
        "lista_objetos",
        "datos_niveles",
        "datos_ruta",
    ):
        return None
    lowered = message.strip().lower()
    if _is_greeting(lowered) or not lowered or _is_rejection(lowered):
        return None
    if _field_complete(lead, expected_field):
        return None
    if expected_field == "datos_niveles":
        if lead.piso_origen is not None or lead.piso_destino is not None:
            return None
    if expected_field == "datos_ruta":
        if lead.distrito_origen or lead.distrito_destino:
            return None
    if extracted.get(expected_field) not in (None, ""):
        return None
    key = (lead.id, expected_field)
    count = _rephrase_counters.get(key, 0)
    fallbacks = REPHRASED_QUESTIONS.get(expected_field)
    if not fallbacks:
        return None
    if count >= len(fallbacks):
        return None
    _rephrase_counters[key] = count + 1
    return fallbacks[count]


def _only_yes_or_no(answer):
    normalized = re.sub(r"[^a-záéíóúñ ]", "", answer).strip()
    return normalized in {"si", "sí", "no", "claro", "correcto"}


def _answer_is_transport_only(answer):
    lowered = answer.lower()
    phrases = [
        "solo transporte",
        "solo traslado",
        "solo vehiculo",
        "solo el camion",
        "solo camion",
        "solo la movilidad",
        "solo el movil",
        "unicamente el vehiculo",
    ]
    if any(phrase in lowered for phrase in phrases):
        return True
    if re.search(r"\bsolo\s+(?:tr[ea]ns?por?te?|trasnporte|movilidad|camion|vehiculo)\b", lowered):
        return True
    return False


def _refers_only_to_photo(answer):
    lowered = answer.lower()
    references = [
        "es lo que ves",
        "lo que ves",
        "lo de la foto",
        "esta en la foto",
        "está en la foto",
        "solo la foto",
    ]
    return any(reference in lowered for reference in references)


def _answer_is_yes(answer):
    lowered = answer.lower()
    negative_patterns = [
        r"\bno\b",
        r"\bningun[oa]?\b",
        r"\bsin\s+desarmar\b",
    ]
    return not any(re.search(pattern, lowered) for pattern in negative_patterns)


def _is_greeting(message):
    normalized = re.sub(r"[^a-záéíóúñ ]", "", message.lower()).strip()
    return normalized in {
        "hol",
        "hola",
        "ola",
        "buen dia",
        "buen día",
        "buenos dias",
        "buenos días",
        "buenas",
        "buenas tardes",
        "buenas noches",
    }


def _infer_service_from_objects(message):
    lowered = message.lower()
    if any(term in lowered for term in ["oficina", "empresa", "corporativo"]):
        return "oficina"
    if any(
        term in lowered
        for term in [
            "mudanza completa",
            "toda mi casa",
            "todo mi departamento",
            "casa completa",
            "departamento completo",
        ]
    ):
        return "mudanza"
    return "traslado pequeno"


def _is_acceptance(message):
    lowered = message.strip().lower()
    if lowered in {"si", "sí", "ok", "dale", "de acuerdo"}:
        return True
    if (
        re.search(r"\b(?:quiero|qyuiero|quero|kiero)\s+reserv", lowered)
        and "no quiero" not in lowered
    ):
        return True
    terms = [
        "acepto",
        "quiero reservar",
        "confirmo",
        "me parece bien",
        "esta bien",
        "está bien",
        "hagamoslo",
        "hagámoslo",
    ]
    return any(term in lowered for term in terms)


def _is_rejection(message):
    lowered = _canonical_place(message)
    return lowered in {"no", "no es correcto", "incorrecto"} or any(
        term in lowered
        for term in ["quiero cambiar", "otra fecha", "otra hora", "me equivoque"]
    )


def _mentions_weekday(message):
    normalized = _canonical_place(message)
    return any(
        re.search(rf"\b{weekday}\b", normalized)
        for weekday in [
            "lunes",
            "martes",
            "miercoles",
            "jueves",
            "viernes",
            "sabado",
            "domingo",
        ]
    )


def _formatted_schedule(lead):
    weekdays = [
        "lunes",
        "martes",
        "miercoles",
        "jueves",
        "viernes",
        "sabado",
        "domingo",
    ]
    months = [
        "",
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]
    date = lead.fecha_servicio
    return (
        f"el {weekdays[date.weekday()]} {date.day:02d} de {months[date.month]} "
        f"a las {lead.horario_servicio}"
    )


def _complete_reservation(lead):
    missing_question = _next_missing_question(lead)
    if missing_question:
        return missing_question
    from django.core.exceptions import ValidationError
    from apps.servicios.services import crear_servicio_desde_lead

    try:
        servicio, created = crear_servicio_desde_lead(lead, require_accepted_revision=True)
    except ValidationError:
        lead.atencion_humana = True
        lead.requiere_asesor = True
        lead.motivo_derivacion = "Datos completos sin cotizacion comercial enviada y aceptada"
        lead.save(update_fields=["atencion_humana", "requiere_asesor", "motivo_derivacion"])
        return (
            "Ya tenemos los datos necesarios. Un asesor validara la cotizacion "
            "aceptada antes de registrar el servicio."
        )
    lead.atencion_humana = False
    lead.requiere_asesor = False
    lead.motivo_derivacion = ""
    lead.save(update_fields=["atencion_humana", "requiere_asesor", "motivo_derivacion"])
    if created:
        return f"Tu servicio quedo registrado con el codigo {servicio.codigo}."
    return f"Tu servicio ya estaba registrado con el codigo {servicio.codigo}."

    # Legacy fallback retained temporarily below; unreachable by design.
    lead.atencion_humana = True
    lead.requiere_asesor = True
    lead.motivo_derivacion = "Datos de reserva completos; falta crear Servicio operacional"
    lead.save(
        update_fields=[
            "atencion_humana",
            "requiere_asesor",
            "motivo_derivacion",
        ]
    )
    return (
        "Ya tenemos los datos necesarios para coordinar el servicio. "
        "Un asesor confirmará la disponibilidad y completará el registro."
    )


def _ai_detects_new_quote(ai_extracted):
    if not ai_extracted or not ai_extracted.get("campos_detectados"):
        return False
    campos = ai_extracted["campos_detectados"]
    new_quote_fields = [
        "lista_objetos", "tipo_servicio",
        "distrito_origen", "distrito_destino",
        "fecha_servicio",
    ]
    return any(
        field in campos and campos[field] not in (None, "")
        for field in new_quote_fields
    )


def _handle_conversation_closure(lead, message):
    lowered = message.strip().lower()
    closure_phrases = [
        "yo le aviso",
        "cualquier cosa le aviso",
        "cualquier cosa te aviso",
        "cualquier cosa le escribo",
        "cualquier cosa te escribo",
        "gracias igual",
        "gracias por la informacion",
        "gracias por la información",
        "gracias por la info",
        "no estoy interesado",
        "por ahora no gracias",
        "por ahora no",
        "por el momento no",
        "lo voy a evaluar",
        "voy a consultarlo",
        "lo converso y te aviso",
        "lo voy a conversar",
        "lo voy a pensar",
        "hablamos luego",
        "gracias no gracias",
        "no gracias",
    ]
    if any(phrase in lowered for phrase in closure_phrases):
        lead.estado = Lead.PERDIDO
        lead.motivo_perdida = "Cliente no interesado / lo pensara"
        lead.save(update_fields=["estado", "motivo_perdida"])
        return (
            "Perfecto. Quedamos atentos por si mas adelante deseas continuar con "
            "la cotizacion. Que tengas un excelente dia."
        )
    bare = lowered.strip().rstrip(".!")
    if bare == "gracias" and not any(
        acc in lowered for acc in ["quiero reservar", "acepto", "confirmo", "si reserv"]
    ):
        lead.estado = Lead.PERDIDO
        lead.motivo_perdida = "Cliente no interesado / lo pensara"
        lead.save(update_fields=["estado", "motivo_perdida"])
        return (
            "Perfecto. Quedamos atentos por si mas adelante deseas continuar con "
            "la cotizacion. Que tengas un excelente dia."
        )
    return None


def _handle_price_conversation(lead, message):
    current = lead.precio_cotizado or lead.precio_estimado_max
    minimum = lead.precio_estimado_min
    if current is None or minimum is None:
        return None

    lowered = message.strip().lower()

    if lead.esperando_motivo_no_reserva:
        return _handle_reservation_objection(lead, lowered, current, minimum)

    proposed = _extract_price_offer(lowered)
    if proposed is not None:
        return _reply_to_price_offer(lead, proposed, current, minimum)

    if _is_greeting(lowered):
        if current >= lead.precio_estimado_max and current > minimum:
            new_price = max(minimum, current - _negotiation_step(lead))
            lead.precio_cotizado = new_price
            lead.save(update_fields=["precio_cotizado"])
            return (
                f"Hola. Para ayudarte puedo dejarte el servicio en S/ {new_price:.0f}. "
                "Te animas a reservarlo?"
            )
        return "Hola. Hay algun detalle que te impida decidir o que quieras cambiar?"

    if any(
        term in lowered
        for term in [
            "cual es el precio",
            "cuál es el precio",
            "precio real",
            "precio final",
            "cuanto cuesta",
            "cuánto cuesta",
            "cuanto sale",
            "cuánto sale",
        ]
    ):
        return _price_offer_message(lead)

    if _mentions_price_objection(lowered):
        if current <= minimum:
            return (
                f"Entiendo. El mejor precio que puedo ofrecerte actualmente es "
                f"S/ {current:.0f}. Si te sirve, avanzamos con la reserva."
            )
        new_price = max(minimum, current - _negotiation_step(lead))
        lead.precio_cotizado = new_price
        lead.etapa_conversacion = Lead.ETAPA_COTIZACION
        lead.save(update_fields=["precio_cotizado", "etapa_conversacion"])
        return (
            f"Entiendo. Puedo hacerte un descuento y dejarte el servicio en "
            f"S/ {new_price:.0f}. Te serviria ese precio para reservarlo?"
        )

    if _is_postponement(lowered):
        lead.esperando_motivo_no_reserva = True
        lead.save(update_fields=["esperando_motivo_no_reserva"])
        return (
            "Claro. Antes de dejarlo pendiente, que te detiene por ahora: "
            "el precio, la fecha o algun otro detalle?"
        )

    # New enhancement: handle price negotiation with multiple steps and context
    if "me parece caro" in lowered or "muy caro" in lowered:
        if current > minimum:
            new_price = max(minimum, current - _negotiation_step(lead) * 2)
            lead.precio_cotizado = new_price
            lead.save(update_fields=["precio_cotizado"])
            return (
                f"Entiendo que el precio es alto. Puedo ofrecerte un descuento especial "
                f"y dejar el servicio en S/ {new_price:.0f}. ¿Te gustaría reservar ahora?"
            )
        else:
            return (
                f"Entiendo. El mejor precio que puedo ofrecerte actualmente es "
                f"S/ {current:.0f}. Si te sirve, avanzamos con la reserva."
            )

    if "no quiero pagar tanto" in lowered or "es muy caro" in lowered:
        if current > minimum:
            new_price = max(minimum, current - _negotiation_step(lead))
            lead.precio_cotizado = new_price
            lead.save(update_fields=["precio_cotizado"])
            return (
                f"Comprendo tu preocupación por el precio. Puedo ajustar el costo a S/ {new_price:.0f}. "
                "¿Quieres reservar con este precio?"
            )
        else:
            return (
                f"Entiendo. El mejor precio que puedo ofrecerte actualmente es "
                f"S/ {current:.0f}. Si te sirve, avanzamos con la reserva."
            )

    return None


def _handle_reservation_objection(lead, message, current, minimum):
    lead.esperando_motivo_no_reserva = False
    if _mentions_price_objection(message):
        if current <= minimum:
            lead.save(update_fields=["esperando_motivo_no_reserva"])
            return (
                f"Entiendo. El mejor precio que puedo ofrecerte actualmente es "
                f"S/ {current:.0f}. Si te sirve, avanzamos con la reserva."
            )
        new_price = max(minimum, current - _negotiation_step(lead))
        lead.precio_cotizado = new_price
        lead.save(update_fields=["esperando_motivo_no_reserva", "precio_cotizado"])
        return (
            f"Entiendo. Para ayudarte puedo dejarte el servicio en S/ {new_price:.0f}. "
            "Te serviria ese precio?"
        )
    if any(term in message for term in ["fecha", "dia", "día", "aun no se", "aún no sé"]):
        lead.fecha_por_confirmar = True
        lead.save(update_fields=["esperando_motivo_no_reserva", "fecha_por_confirmar"])
        return "Entiendo, no hay problema. Cuando tengas la fecha me escribes y lo coordinamos."
    lead.save(update_fields=["esperando_motivo_no_reserva"])
    return "Entiendo. Cuando tengas decidido ese detalle me escribes y retomamos desde aqui."


def _is_postponement(message):
    return any(
        term in message
        for term in [
            "te aviso",
            "yo te aviso",
            "luego te aviso",
            "despues te aviso",
            "después te aviso",
            "lo voy a pensar",
            "voy a pensarlo",
            "dejame pensarlo",
            "déjame pensarlo",
            "te confirmo luego",
            "mas adelante",
            "más adelante",
        ]
    )


def _mentions_price_objection(message):
    return any(
        term in message
        for term in [
            "precio",
            "caro",
            "costoso",
            "presupuesto",
            "dinero",
            "muy alto",
            "elevado",
            "demasiado",
            "es mucho",
            "no llego",
            "se me escapa",
            "se me hace mucho",
            "no me alcanza",
            "fuera de mi presupuesto",
            "no me parece",
            "no estoy de acuerdo",
            "no me convence",
            "sigue caro",
            "aun esta caro",
            "aún está caro",
            "descuento",
            "rebaja",
            "mejor precio",
            "puedes mejorar",
            "puede mejorar",
            "algo menos",
            "menos precio",
        ]
    )


def _extract_price_offer(message):
    patterns = [
        r"(?:te\s+doy|ofrezco|puedo\s+pagar|lo\s+dejamos\s+en|por)\s+s?/?\.?\s*(\d{2,5})",
        r"s/?\.?\s*(\d{2,5})",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return Decimal(match.group(1))
    return None


def _reply_to_price_offer(lead, proposed, current, minimum):
    if proposed < minimum:
        lead.precio_cotizado = minimum
        lead.save(update_fields=["precio_cotizado"])
        return (
            f"Por ese monto no llegamos, pero lo minimo que puedo dejarte es "
            f"S/ {minimum:.0f}. Si te parece, lo reservamos."
        )
    agreed = min(proposed, current)
    lead.precio_cotizado = agreed
    lead.save(update_fields=["precio_cotizado"])
    return (
        f"Listo, podemos dejar el servicio en S/ {agreed:.0f}. "
        "Si estas de acuerdo, avanzamos con la reserva."
    )


def _negotiation_step(lead):
    spread = lead.precio_estimado_max - lead.precio_estimado_min
    raw_step = max(Decimal("10"), spread / Decimal("3"))
    return (raw_step / Decimal("10")).to_integral_value(
        rounding=ROUND_CEILING
    ) * Decimal("10")


def _price_offer_message(lead):
    price = lead.precio_cotizado or lead.precio_estimado_max
    service = "mudanza" if lead.tipo_servicio == "mudanza" else "traslado"
    return (
        f"El costo de tu {service} es de S/ {price:.0f}. "
        "Si te parece, avanzamos con la reserva."
    )


def _date_is_unknown(message):
    lowered = message.strip().lower()
    terms = [
        "no tengo fecha",
        "sin fecha",
        "aun no se",
        "aún no sé",
        "todavia no",
        "todavía no",
        "solo estoy cotizando",
        "recien estoy cotizando",
        "recién estoy cotizando",
        "no quiero programarlo",
        "no estoy seguro de la fecha",
        "no estoy segura de la fecha",
        "aun no tengo una fecha",
        "aún no tengo una fecha",
        "solo quiero el precio",
        "solo quiero cotizar",
        "quiero saber el precio",
    ]
    if any(term in lowered for term in terms):
        return True
    mentions_uncertainty = any(
        term in lowered
        for term in ["no se", "no sé", "no estoy seguro", "no estoy segura", "por confirmar"]
    )
    mentions_date = any(term in lowered for term in ["fecha", "dia", "día"])
    return mentions_uncertainty and mentions_date


def _asks_about_payment(message):
    lowered = _canonical_place(message)
    return any(
        term in lowered
        for term in [
            "como seria el pago",
            "como es el pago",
            "como pago",
            "como puedo pagar",
            "medio de pago",
            "medios de pago",
            "forma de pago",
            "formas de pago",
            "donde pago",
            "yape",
            "numero de cuenta",
            "nro de cuenta",
            "cuenta bcp",
            "transferencia",
            "deposito",
        ]
    )


def _account_holder_information(message):
    normalized = _canonical_place(message)
    mentions_account = any(
        term in normalized
        for term in ["cuenta", "bcp", "transferencia", "deposito"]
    )
    asks_holder = any(
        term in normalized
        for term in [
            "mismo nombre",
            "misma persona",
            "a nombre de quien",
            "quien es el titular",
            "nombre de quien",
            "tambien sale",
        ]
    )
    if mentions_account and asks_holder:
        return "Si, la cuenta BCP tambien esta a nombre de Walter Escobar."
    return None


def _answer_post_reservation_question(lead, message):
    recent = list(
        lead.cliente.conversaciones.order_by("-fecha").values_list(
            "mensaje_entrada",
            "mensaje_salida",
        )[:6]
    )
    recent.reverse()
    history = "\n".join(
        f"Cliente: {incoming}\nAsesor: {outgoing}"
        for incoming, outgoing in recent
        if incoming or outgoing
    )
    context = (
        "Responde la consulta actual del cliente de TaxiCarga de forma breve, "
        "natural y directa. El servicio ya esta reservado. No vuelvas a pedir "
        "datos de cotizacion o reserva. Usa solo los datos proporcionados. Si la "
        "respuesta no se puede saber con certeza, indica que lo confirmaremos con "
        "el equipo; no inventes.\n\n"
        "Datos verificados del negocio:\n"
        "- Yape: 996797907, titular Walter Escobar.\n"
        "- Cuenta BCP: 19409223621088, titular Walter Escobar.\n"
        "- El conductor se comunica cuando esta llegando a la direccion.\n\n"
        f"Reserva: fecha={lead.fecha_servicio}, hora={lead.horario_servicio}, "
        f"origen={lead.direccion_origen}, destino={lead.direccion_destino}, "
        f"precio=S/ {lead.precio_final or lead.precio_cotizado}.\n\n"
        f"Conversacion reciente:\n{history}\n\n"
        f"Consulta actual: {message}"
    )
    ai_reply = generate_reply(
        [{"role": "user", "content": context}],
        system_prompt=POST_RESERVATION_SYSTEM_PROMPT,
    )
    return ai_reply or (
        "Voy a confirmar ese detalle con el equipo para darte una respuesta correcta."
    )


def _packing_information(message):
    lowered = message.lower()
    asks = any(
        term in lowered
        for term in [
            "que incluye",
            "qué incluye",
            "cual es la diferencia",
            "cuál es la diferencia",
            "como es el embalaje",
            "cómo es el embalaje",
        ]
    )
    if not asks or "embalaje" not in lowered:
        return None
    if "full" in lowered:
        return (
            "El embalaje full incluye proteger muebles y artefactos, y tambien "
            "empacar menaje, ropa y accesorios."
        )
    if "muebles" in lowered or "artefactos" in lowered or "completo" in lowered:
        return (
            "Ese embalaje protege todos los muebles y artefactos. El menaje, "
            "la ropa y los accesorios deben quedar listos en cajas."
        )
    if "basico" in lowered or "básico" in lowered:
        return (
            "El embalaje basico usa stretch film en los muebles y artefactos "
            "mas delicados. No incluye empacar menaje, ropa ni accesorios."
        )
    return (
        "Tenemos embalaje basico para piezas delicadas, embalaje de todos los "
        "muebles y artefactos, y embalaje full que tambien incluye menaje, ropa "
        "y accesorios."
    )


def _handle_packaging_inquiry(lead, message):
    lowered = message.lower()

    if lead.estado == Lead.COTIZADO and "embalaje full" in lowered:
        if any(
            term in lowered
            for term in [
                "incluye", "incluido", "incluye embalaje",
                "precio incluye", "precio incluye embalaje",
                "ese precio", "esta incluido", "está incluido",
            ]
        ):
            current_type = lead.modalidad_servicio or "basico"
            return (
                f"No, ese precio considera embalaje {current_type}. "
                "El embalaje full requiere evaluacion previa con fotos "
                "de todo lo que deseas embalar."
            )

    if "embalaje" in lowered:
        asks_type = any(
            term in lowered
            for term in [
                "que tipo", "qué tipo", "que embalaje", "qué embalaje",
                "es basico", "es básico", "es full",
                "estan dando", "están dando", "me estan dando",
                "quiero saber", "como es el embalaje", "cómo es el embalaje",
            ]
        )
        if asks_type:
            current_type = lead.modalidad_servicio or "aun no se ha definido"
            if current_type == "embalaje_pendiente":
                current_type = "aun por definir"
            return f"La modalidad actual es: {current_type}."

    if "quiero embalaje full" in lowered or "embalaje full quiero" in lowered:
        lead.modalidad_servicio = "embalaje full"
        lead.atencion_humana = True
        lead.save(update_fields=["modalidad_servicio", "atencion_humana"])
        return (
            "Para cotizar embalaje full necesitamos fotos de todo lo que "
            "deseas embalar. Un asesor revisara el volumen y te indicara "
            "el monto."
        )

    return None


def _handle_availability_inquiry(lead, message):
    lowered = message.lower()
    asks_availability = any(
        term in lowered
        for term in [
            "disponibilidad", "disponible",
            "tienen para manana", "tienen para mañana",
            "pueden manana", "pueden mañana",
            "para manana", "para mañana",
            "hacen manana", "hacen mañana",
            "trabajan manana", "trabajan mañana",
            "atencion manana", "atención mañana",
        ]
    )
    if not asks_availability:
        return None

    if lead.estado not in (Lead.COTIZADO, Lead.ASIGNADO, Lead.DATOS_INCOMPLETOS):
        return None

    return (
        "Podemos revisar disponibilidad para manana. "
        "A que hora aproximadamente lo necesitas?"
    )


def _route_requires_manual_review(lead):
    for place, label in [
        (lead.distrito_origen, "distrito_origen"),
        (lead.distrito_destino, "distrito_destino"),
    ]:
        canonical = _canonical_place(place)
        if canonical not in LOCAL_LIMA_CALLAO_AREAS:
            logger.info(
                "ManualReview=True | %s=%s canonical=%s fuera de Lima/Callao",
                label, place, canonical,
            )
            return True
    return False


def _route_with_stops(message):
    normalized = _canonical_place(message)
    explicit_stop = any(
        marker in normalized
        for marker in (
            "paso por", "pasamos por", "parada en", "una parada", "recoger tambien",
            "recogemos tambien", "luego vamos a", "despues vamos a",
        )
    )
    mentioned = {
        area for area in LOCAL_LIMA_CALLAO_AREAS
        if re.search(rf"\b{re.escape(area)}\b", normalized)
    }
    return explicit_stop or len(mentioned) >= 3


def _extract_route_correction(message):
    normalized = _canonical_place(message)
    destination = re.search(
        r"(?:no era|no es)\s+.+?[,;]\s*(?:es|seria)\s+([a-z ]+)$",
        normalized,
    )
    if not destination:
        return {}
    district = normalize_district(destination.group(1))
    if _canonical_place(district) not in LOCAL_LIMA_CALLAO_AREAS:
        return {}
    return {"distrito_destino": district}


def _requested_stop_removal(message):
    normalized = _canonical_place(message)
    match = re.search(
        r"(?:ya no|no)\s+(?:pasaremos|pasamos|pasar|iremos|vamos)\s+por\s+([a-z ]+)",
        normalized,
    )
    if not match:
        return ""
    district = normalize_district(match.group(1))
    return district if district else ""


def _answer_customer_question(lead, message):
    normalized = _canonical_place(message)
    if "?" not in message and not normalized.startswith(("incluye", "el precio incluye", "vienen")):
        return None
    if any(term in normalized for term in ("ayudante", "operario", "personal")):
        if lead.incluye_personal_carga is True:
            return "Sí, estamos considerando personal para carga y descarga."
        if lead.incluye_personal_carga is False:
            return "No, estamos considerando solo el transporte porque ustedes realizarán la carga."
        return "Aún no está definido si el servicio llevará personal de carga."
    return None


def _log_decision(lead, decision_type, extracted, quote_ready, handoff, ai_success):
    logger.info(
        "conversation_decision conversation_lead=%s phase=%s fields_updated=%s "
        "quote_ready=%s handoff=%s ai=%s",
        lead.id,
        decision_type,
        sorted(extracted.keys()),
        quote_ready,
        handoff,
        "success" if ai_success else "fallback",
    )


def _canonical_place(value):
    normalized = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    return " ".join(
        "".join(char for char in normalized if not unicodedata.combining(char)).split()
    )


def _clear_quote(lead):
    lead.precio_estimado_min = None
    lead.precio_estimado_max = None
    lead.precio_recomendado = None
    lead.precio_cotizado = None
    lead.esperando_motivo_no_reserva = False


def _try_ai_reply(lead, message, fallback_question):
    examples = conversation_examples_for(message, fallback_question)
    examples_context = format_examples_for_prompt(examples)
    context = (
        f"Mensaje del cliente: {message}\n"
        f"Datos actuales: tipo={lead.tipo_servicio}, origen={lead.distrito_origen}, "
        f"destino={lead.distrito_destino}, objetos={lead.lista_objetos}\n"
        f"Siguiente dato faltante sugerido: {fallback_question}\n"
        f"{examples_context}"
    )
    return generate_reply([{"role": "user", "content": context}])
