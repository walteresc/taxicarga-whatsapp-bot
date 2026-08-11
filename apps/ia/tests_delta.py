import json

from django.test import TestCase, override_settings

from apps.clientes.models import Cliente
from apps.leads.models import Lead, LeadUbicacion
from apps.whatsapp.models import (
    ConversacionWhatsApp,
    MensajeWhatsApp,
    WhatsAppChannel,
)

from .delta_context import build_delta_context
from .delta_contract import ConversationDelta
from .delta_extractor import (
    process_delta_shadow_event,
    queue_delta_shadow,
    run_delta_shadow,
)
from .delta_snapshot import build_canonical_snapshot
from .delta_validator import snapshot_matches, validate_delta
from .models import AIDeltaAudit
from .providers import AIResult, OpenAIProvider


class FakeStructuredProvider:
    name = "openai"
    model = "gpt-4.1-mini"

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def generate_structured(self, messages, *, schema_model):
        if self.error:
            raise self.error
        parsed = schema_model.model_validate(self.payload)
        return AIResult(
            text=parsed.model_dump_json(),
            provider=self.name,
            model=self.model,
            latency_ms=12.5,
            input_tokens=120,
            output_tokens=45,
        )


class DeltaArchitectureTests(TestCase):
    def setUp(self):
        self.client_record = Cliente.objects.create(telefono="51900000991")
        self.channel = WhatsAppChannel.objects.create(
            nombre="Delta shadow TEST", phone_number_id="delta-shadow-test", activo=True
        )
        self.lead = Lead.objects.create(
            cliente=self.client_record,
            whatsapp_channel=self.channel,
            tipo_servicio="mudanza",
            distrito_origen="Surco",
            distrito_destino="Miraflores",
            piso_origen=3,
            piso_destino=2,
            ascensor_destino=False,
            lista_objetos="cama, refrigeradora y aprox. 15 cajas",
            incluye_personal_carga=True,
            modalidad_servicio="sin embalaje",
            requiere_desarmado=False,
            requiere_armado=False,
        )
        LeadUbicacion.objects.create(
            lead=self.lead, orden=0, tipo="origen", distrito="Surco", piso=3
        )
        LeadUbicacion.objects.create(
            lead=self.lead,
            orden=1,
            tipo="destino",
            distrito="Miraflores",
            piso=2,
            ascensor=False,
        )
        self.conversation = ConversacionWhatsApp.objects.create(
            cliente=self.client_record,
            lead=self.lead,
            channel=self.channel,
        )
        self.bot_message = MensajeWhatsApp.objects.create(
            conversacion=self.conversation,
            direccion=MensajeWhatsApp.SALIENTE,
            origen=MensajeWhatsApp.ORIGEN_BOT,
            contenido=(
                "¿En Surco tienen ascensor? Y lo de estacionarse a una cuadra, "
                "¿corresponde a Surco, Miraflores o ambos?"
            ),
        )
        self.customer_text = (
            "si, asensor en el origen y enel destino el carro se estaciona un "
            "poquitolejos de la entrada de la casa"
        )
        self.customer_message = MensajeWhatsApp.objects.create(
            conversacion=self.conversation,
            direccion=MensajeWhatsApp.ENTRANTE,
            origen=MensajeWhatsApp.ORIGEN_CLIENTE,
            contenido=self.customer_text,
        )

    def test_snapshot_preserves_unknowns_and_uses_locations(self):
        snapshot = build_canonical_snapshot(self.lead)

        self.assertIsNone(snapshot.state["locations"]["origin"]["elevator"])
        self.assertIsNone(snapshot.state["locations"]["origin"]["truck_access"])
        self.assertFalse(snapshot.state["locations"]["destination"]["elevator"])
        self.assertTrue(snapshot_matches(self.lead, snapshot.state_version))

    @override_settings(
        AI_DELTA_EXTRACTION_ENABLED=False,
        AI_DELTA_SHADOW_MODE=True,
    )
    def test_shadow_mode_is_independent_from_future_operative_flag(self):
        from .conversation_engine import delta_shadow_enabled

        self.assertTrue(delta_shadow_enabled())

    @override_settings(
        AI_DELTA_EXTRACTION_ENABLED=True,
        AI_DELTA_SHADOW_MODE=False,
    )
    def test_operative_flag_does_not_force_shadow_mode(self):
        from .conversation_engine import delta_shadow_enabled

        self.assertFalse(delta_shadow_enabled())

    def test_context_has_explicit_last_question_without_customer_duplicate(self):
        snapshot = build_canonical_snapshot(self.lead)
        context = build_delta_context(
            self.conversation.id,
            trigger_message_id=self.customer_message.id,
            customer_message=self.customer_text,
            snapshot=snapshot,
        )

        self.assertEqual(context.last_bot_question, self.bot_message.contenido)
        self.assertEqual(context.payload["customer_message"], self.customer_text)
        recent_texts = [turn["text"] for turn in context.payload["recent_turns"]]
        self.assertNotIn(self.customer_text, recent_texts)
        self.assertNotIn(self.bot_message.contenido, recent_texts)
        self.assertLessEqual(context.recent_turn_count, 4)

    def test_queue_is_idempotent_and_does_not_call_provider(self):
        from unittest.mock import patch

        with patch("apps.ia.delta_extractor.build_provider") as provider:
            first, first_created = queue_delta_shadow(
                trigger_message_id=self.customer_message.id,
                legacy_extraction={"cliente_nombre": "secreto", "piso_origen": 3},
            )
            second, second_created = queue_delta_shadow(
                trigger_message_id=self.customer_message.id,
            )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.safe_payload["legacy_extraction"]["cliente_nombre"], "[redacted]")
        provider.assert_not_called()
        self.assertFalse(AIDeltaAudit.objects.exists())

    def test_internal_worker_processes_only_queued_shadow_event(self):
        payload = {
            "schema_version": 2,
            "intent": "provide_information",
            "changes": {
                "lead": {},
                "locations": [{
                    "ref": "origin",
                    "ref_evidence": "en el origen",
                    "ref_evidence_type": "explicit",
                    "set": {"elevator": {
                        "value": True,
                        "evidence": "si, asensor en el origen",
                        "evidence_type": "explicit",
                    }},
                }],
            },
            "corrections": [],
            "ambiguities": [],
        }
        event, _ = queue_delta_shadow(trigger_message_id=self.customer_message.id)
        from unittest.mock import patch

        with patch(
            "apps.ia.delta_extractor.build_provider",
            return_value=FakeStructuredProvider(payload),
        ):
            result = process_delta_shadow_event(event.id, worker_id="test-worker")

        event.refresh_from_db()
        self.assertEqual(result, "sent")
        self.assertEqual(event.status, "sent")
        self.assertEqual(event.attempts, 1)
        self.assertTrue(AIDeltaAudit.objects.filter(message_id=self.customer_message.id).exists())

    def test_real_sequence_produces_shadow_delta_without_mutating_lead(self):
        payload = {
            "schema_version": 2,
            "intent": "provide_information",
            "changes": {
                "lead": {},
                "locations": [
                    {
                        "ref": "origin",
                        "ref_evidence": "en el origen",
                        "ref_evidence_type": "explicit",
                        "set": {"elevator": {
                            "value": True,
                            "evidence": "si, asensor en el origen",
                            "evidence_type": "explicit",
                        }},
                    },
                    {
                        "ref": "destination",
                        "ref_evidence": "enel destino",
                        "ref_evidence_type": "explicit",
                        "set": {
                            "access_observation": {
                                "value": "El vehículo se estaciona un poco lejos de la entrada",
                                "evidence": "enel destino el carro se estaciona un poquitolejos de la entrada de la casa",
                                "evidence_type": "explicit",
                            }
                        },
                    },
                ],
            },
            "corrections": [],
            "ambiguities": [],
        }
        provider = FakeStructuredProvider(payload)

        from unittest.mock import patch

        with patch("apps.ia.delta_extractor.build_provider", return_value=provider):
            audit = run_delta_shadow(
                lead=self.lead,
                conversation_id=self.conversation.id,
                trigger_message_id=self.customer_message.id,
                customer_message=self.customer_text,
            )

        self.lead.refresh_from_db()
        locations = list(self.lead.ubicaciones.order_by("orden"))
        self.assertEqual(audit.status, AIDeltaAudit.STATUS_ACCEPTED)
        self.assertTrue(
            audit.accepted_delta["changes"]["locations"][0]["set"]["elevator"]["value"]
        )
        self.assertIsNone(locations[0].ascensor)
        self.assertFalse(locations[1].ascensor)
        self.assertEqual(locations[1].observaciones_acceso, "")

    def test_same_message_is_idempotent(self):
        payload = {
            "schema_version": 2,
            "intent": "provide_information",
            "changes": {"lead": {}, "locations": []},
            "corrections": [],
            "ambiguities": [],
        }
        provider = FakeStructuredProvider(payload)
        from unittest.mock import patch

        with patch("apps.ia.delta_extractor.build_provider", return_value=provider):
            first = run_delta_shadow(
                lead=self.lead,
                conversation_id=self.conversation.id,
                trigger_message_id=self.customer_message.id,
                customer_message=self.customer_text,
            )
            second = run_delta_shadow(
                lead=self.lead,
                conversation_id=self.conversation.id,
                trigger_message_id=self.customer_message.id,
                customer_message=self.customer_text,
            )

        self.assertEqual(first.id, second.id)
        self.assertEqual(AIDeltaAudit.objects.count(), 1)

    def test_provider_failure_records_conservative_empty_fallback(self):
        provider = FakeStructuredProvider(error=TimeoutError("timeout"))
        from unittest.mock import patch

        with patch("apps.ia.delta_extractor.build_provider", return_value=provider):
            audit = run_delta_shadow(
                lead=self.lead,
                conversation_id=self.conversation.id,
                trigger_message_id=self.customer_message.id,
                customer_message=self.customer_text,
            )

        self.assertEqual(audit.status, AIDeltaAudit.STATUS_FALLBACK)
        self.assertTrue(audit.fallback_used)
        self.assertEqual(audit.error_type, "TimeoutError")
        self.assertEqual(audit.accepted_delta["changes"]["locations"], [])

    def test_15_boxes_delta_does_not_contain_floor(self):
        delta = ConversationDelta.model_validate(
            {
                "schema_version": 1,
                "intent": "provide_information",
                "changes": {"lead": {"load": "15 cajas"}, "locations": []},
                "corrections": [],
                "ambiguities": [],
            }
        )

        self.assertEqual(delta.changes.lead.load, "15 cajas")
        self.assertFalse(delta.changes.locations)

    def test_destination_correction_is_valid_delta(self):
        delta = ConversationDelta.model_validate(
            {
                "schema_version": 1,
                "intent": "correct_information",
                "changes": {
                    "lead": {},
                    "locations": [
                        {"ref": "destination", "set": {"district": "San Isidro"}}
                    ],
                },
                "corrections": [{"target": "destination.district"}],
                "ambiguities": [],
            }
        )

        result = validate_delta(delta, build_canonical_snapshot(self.lead))
        self.assertFalse(result.rejected_fields)
        self.assertEqual(
            result.accepted.changes.locations[0].set.district, "San Isidro"
        )

    def test_both_reference_is_limited_to_current_attribute_delta(self):
        delta = ConversationDelta.model_validate_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "intent": "provide_information",
                    "changes": {
                        "lead": {},
                        "locations": [
                            {"ref": "both", "set": {"truck_access": True}}
                        ],
                    },
                    "corrections": [],
                    "ambiguities": [],
                }
            )
        )

        result = validate_delta(delta, build_canonical_snapshot(self.lead))
        self.assertFalse(result.rejected_fields)
        values = result.accepted.changes.locations[0].set.model_dump(exclude_none=True)
        self.assertEqual(values, {"truck_access": True})

    def test_unknown_location_reference_is_rejected(self):
        delta = ConversationDelta.model_validate(
            {
                "schema_version": 1,
                "intent": "provide_information",
                "changes": {
                    "lead": {},
                    "locations": [{"ref": "order:99", "set": {"elevator": True}}],
                },
                "corrections": [],
                "ambiguities": [],
            }
        )

        result = validate_delta(delta, build_canonical_snapshot(self.lead))
        self.assertEqual(result.rejected_fields, ("changes.locations[0].ref",))
        self.assertFalse(result.accepted.changes.locations)

    def test_business_authority_fields_are_forbidden_by_schema(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            ConversationDelta.model_validate(
                {
                    "schema_version": 1,
                    "intent": "provide_information",
                    "changes": {
                        "lead": {"price": 120, "owner_state": "BOT_ACTIVO"},
                        "locations": [],
                    },
                    "corrections": [],
                    "ambiguities": [],
                }
            )

    def test_state_version_detects_stale_snapshot(self):
        snapshot = build_canonical_snapshot(self.lead)
        destination = self.lead.ubicaciones.get(tipo="destino")
        destination.distrito = "San Isidro"
        destination.save(update_fields=["distrito"])

        self.assertFalse(snapshot_matches(self.lead, snapshot.state_version))

    def test_short_yes_uses_previous_question_context(self):
        self.customer_message.contenido = "si"
        self.customer_message.save(update_fields=["contenido"])
        context = build_delta_context(
            self.conversation.id,
            trigger_message_id=self.customer_message.id,
            customer_message="si",
            snapshot=build_canonical_snapshot(self.lead),
        )

        self.assertIn("Surco", context.last_bot_question)
        self.assertEqual(context.payload["customer_message"], "si")
        self.assertNotIn(
            "si", [turn["text"] for turn in context.payload["recent_turns"]]
        )

    def test_structured_provider_uses_sdk_parse_contract(self):
        parsed = ConversationDelta.model_validate(
            {
                "schema_version": 1,
                "intent": "provide_information",
                "changes": {"lead": {}, "locations": []},
                "corrections": [],
                "ambiguities": [],
            }
        )

        class Usage:
            input_tokens = 10
            output_tokens = 5

        class Response:
            output_parsed = parsed
            usage = Usage()

        class Responses:
            def __init__(self):
                self.kwargs = None

            def parse(self, **kwargs):
                self.kwargs = kwargs
                return Response()

        responses = Responses()

        class Client:
            pass

        client = Client()
        client.responses = responses
        provider = OpenAIProvider(
            api_key="test-key",
            model="gpt-4.1-mini",
            client_factory=lambda **kwargs: client,
        )

        result = provider.generate_structured(
            [{"role": "user", "content": "test"}],
            schema_model=ConversationDelta,
        )

        self.assertIs(responses.kwargs["text_format"], ConversationDelta)
        self.assertEqual(
            ConversationDelta.model_validate_json(result.text).schema_version, 1
        )
