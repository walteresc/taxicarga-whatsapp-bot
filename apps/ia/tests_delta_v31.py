from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from .conversation_policy import QuestionTarget, _question_targets
from .delta_contract_v31 import ConversationDeltaV31
from .delta_context import DeltaContext
from .delta_extractor_v31 import extract_conversation_delta_v31
from .providers import AIResult
from .delta_snapshot import CanonicalSnapshot
from .delta_validator_v31 import (
    AMBIGUOUS_REF, DERIVED_VALUE_FORBIDDEN, EVIDENCE_CLAIM_COLLISION,
    INFERRED_NOT_ALLOWED, NO_EVIDENCE, NO_OP,
    UNVERIFIED_EXPLICIT_REF,
    UNSUPPORTED_BOOLEAN_EVIDENCE,
    UNSUPPORTED_SERVICE_EVIDENCE,
    UNSUPPORTED_STAFF_EVIDENCE,
    AMBIGUOUS_BOOLEAN_EVIDENCE,
    validate_delta_v31,
)
from .v31_offline_replay import adapt_v3_delta_to_v31
from .v31_blind_holdout import v31_blind_holdout_cases
from .v31_blind_holdout_round2 import v31_blind_holdout_round2_cases
from .v31_blind_holdout_round3 import v31_blind_holdout_round3_cases


class DeltaValidatorV31Tests(SimpleTestCase):
    def setUp(self):
        self.snapshot = CanonicalSnapshot("v31", {
            "service":None, "service_date":None, "load":None,
            "staff":{"required":None},
            "additional_services":{"packing":None,"packing_required":None,
                                   "disassembly_required":None,"assembly_required":None},
            "locations":{"origin":{"district":None,"floor":None,"elevator":None,
                                    "truck_access":None,"carry_distance_m":None,
                                    "access_observation":None},
                         "destination":{"district":None,"floor":None,"elevator":None,
                                         "truck_access":None,"carry_distance_m":None,
                                         "access_observation":None}},
        })

    def delta(self, lead=None, locations=None, corrections=None):
        return ConversationDeltaV31.model_validate({
            "schema_version":"3.1", "intent":"provide_information",
            "changes":{"lead":lead or {},"locations":locations or []},
            "corrections":corrections or [],"ambiguities":[],
        })

    def validate(self, delta, message, targets=()):
        return validate_delta_v31(delta, self.snapshot, customer_message=message,
                                  question_targets=targets)

    def test_target_claim_and_independent_extra_fact_both_survive(self):
        delta = self.delta(lead={"load":{"value":"20 cajas","evidence_quote":"20 cajas",
            "evidence_type":"explicit","context_dependency":"none"}}, locations=[{
            "ref":"origin","ref_evidence_quote":"sí","ref_source":"question_target",
            "set":{"elevator":{"value":True,"evidence_quote":"sí","evidence_type":"explicit",
                                 "context_dependency":"question_target"}}}])
        result = self.validate(delta, "sí, y además son 20 cajas",
                               [QuestionTarget("elevator","origin")])
        self.assertEqual(result.accepted.changes.lead.load.value, "20 cajas")
        self.assertTrue(result.accepted.changes.locations[0].set.elevator.value)

    def test_independent_districts_survive_unrelated_target(self):
        locations=[]
        for ref,name in (("origin","Surco"),("destination","Miraflores")):
            locations.append({"ref":ref,"ref_evidence_quote":name,"ref_source":"explicit_message",
                "set":{"district":{"value":name,"evidence_quote":name,
                "evidence_type":"explicit","context_dependency":"none"}}})
        result=self.validate(self.delta(locations=locations),"Surco a Miraflores",
                             [QuestionTarget("packing_required")])
        self.assertEqual(len(result.accepted.changes.locations),2)

    def test_explicit_correction_bypasses_unrelated_target(self):
        correction={"target":"locations.destination.district","old":"Miraflores",
            "new":"San Isidro","evidence_quote":"no era Miraflores, era San Isidro",
            "evidence_type":"explicit","context_dependency":"none"}
        result=self.validate(self.delta(corrections=[correction]),
            "no era Miraflores, era San Isidro",[QuestionTarget("truck_access","origin")])
        self.assertEqual(result.accepted.corrections[0].new,"San Isidro")

    def test_correction_metadata_does_not_depend_on_question_target(self):
        correction={"target":"staff.required","old":False,"new":True,
            "evidence_quote":"Rectifico, sí necesito personal",
            "evidence_type":"explicit","context_dependency":"question_target"}
        result=self.validate(self.delta(corrections=[correction]),
            "Rectifico, sí necesito personal",[QuestionTarget("staff_required")])
        self.assertEqual(result.accepted.corrections[0].new,True)

    def test_inferred_service_from_staff_is_rejected(self):
        delta=self.delta(lead={"staff_required":{"value":True,"evidence_quote":"con personal",
            "evidence_type":"explicit","context_dependency":"none"},
            "service":{"value":"mudanza","evidence_quote":"con personal",
            "evidence_type":"inferred","context_dependency":"none"}})
        result=self.validate(delta,"con personal")
        self.assertTrue(result.accepted.changes.lead.staff_required.value)
        self.assertIsNone(result.accepted.changes.lead.service)
        self.assertIn(INFERRED_NOT_ALLOWED,[x.reason for x in result.rejected])

    def test_inferred_load_from_staff_is_rejected(self):
        delta=self.delta(lead={"load":{"value":"nosotros cargamos","evidence_quote":"nosotros cargamos",
            "evidence_type":"inferred","context_dependency":"none"}})
        result=self.validate(delta,"nosotros cargamos")
        self.assertIsNone(result.accepted.changes.lead.load)

    def test_endpoint_without_source_becomes_ambiguity(self):
        delta=self.delta(locations=[{"ref":"origin","ref_evidence_quote":"queda lejos",
            "ref_source":"ambiguous","set":{"access_observation":{"value":"queda lejos",
            "evidence_quote":"queda lejos","evidence_type":"explicit","context_dependency":"none"}}}])
        result=self.validate(delta,"queda lejos")
        self.assertIn(AMBIGUOUS_REF,[x.reason for x in result.rejected])
        self.assertEqual(result.accepted.ambiguities[0].field,"access_observation")

    def test_truck_target_resolves_origin(self):
        delta=self.delta(locations=[{"ref":"origin","ref_evidence_quote":"sí",
            "ref_source":"question_target","set":{"truck_access":{"value":True,
            "evidence_quote":"sí","evidence_type":"explicit","context_dependency":"question_target"}}}])
        result=self.validate(delta,"sí",[QuestionTarget("truck_access","origin")])
        self.assertTrue(result.accepted.changes.locations[0].set.truck_access.value)

    def test_direct_distance_is_accepted(self):
        delta=self.delta(locations=[{"ref":"destination","ref_evidence_quote":"en destino",
            "ref_source":"explicit_message","set":{"carry_distance_m":{"value":65,
            "evidence_quote":"en destino son 65 metros","evidence_type":"explicit",
            "context_dependency":"none","value_origin":"direct"}}}])
        result=self.validate(delta,"en destino son 65 metros")
        self.assertEqual(result.accepted.changes.locations[0].set.carry_distance_m.value,65)

    def test_derived_distance_is_rejected(self):
        delta=self.delta(locations=[{"ref":"destination","ref_evidence_quote":"en destino",
            "ref_source":"explicit_message","set":{"carry_distance_m":{"value":100,
            "evidence_quote":"en destino queda lejos","evidence_type":"explicit",
            "context_dependency":"none","value_origin":"derived"}}}])
        result=self.validate(delta,"en destino queda lejos")
        self.assertIn(DERIVED_VALUE_FORBIDDEN,[x.reason for x in result.rejected])

    def test_exact_ordinal_floor_normalization_is_accepted(self):
        delta=self.delta(locations=[{"ref":"destination",
            "ref_evidence_quote":"en destino","ref_source":"explicit_message",
            "set":{"floor":{"value":4,"evidence_quote":"cuarto piso",
            "evidence_type":"explicit","context_dependency":"none",
            "value_origin":"normalized_unit"}}}])
        result=self.validate(delta,"en destino es cuarto piso")
        self.assertEqual(result.accepted.changes.locations[0].set.floor.value,4)

    def test_service_date_is_direct_fact_not_quote_requirement(self):
        delta=self.delta(lead={"service_date":{"value":"2026-09-18",
            "evidence_quote":"18 de septiembre","evidence_type":"explicit",
            "context_dependency":"none"}})
        result=self.validate(delta,"lo necesito el 18 de septiembre")
        self.assertEqual(result.accepted.changes.lead.service_date.value,"2026-09-18")

    def test_paraphrased_evidence_is_rejected(self):
        delta=self.delta(lead={"staff_required":{"value":True,
            "evidence_quote":"cliente necesita personal","evidence_type":"explicit",
            "context_dependency":"none"}})
        result=self.validate(delta,"Necesito personal para cargar")
        self.assertIn(NO_EVIDENCE,[item.reason for item in result.rejected])

    def test_known_location_restatement_is_no_op(self):
        snapshot=CanonicalSnapshot("known",{**self.snapshot.state,"locations":{
            **self.snapshot.state["locations"],"origin":{
                **self.snapshot.state["locations"]["origin"],"district":"Surco"}}})
        delta=self.delta(locations=[{"ref":"origin","ref_evidence_quote":"origen",
            "ref_source":"explicit_message","set":{"district":{"value":"Surco",
            "evidence_quote":"Surco","evidence_type":"explicit",
            "context_dependency":"none"}}}])
        result=validate_delta_v31(delta,snapshot,
            customer_message="origen Surco",question_targets=())
        self.assertIn(NO_OP,[item.reason for item in result.rejected])
        self.assertEqual(result.accepted.changes.locations,[])

    def test_explicit_endpoint_and_fact_are_accepted(self):
        delta=self.delta(locations=[{"ref":"destination",
            "ref_evidence_quote":"en destino","ref_source":"explicit_message",
            "set":{"truck_access":{"value":False,
            "evidence_quote":"en destino no entra el camión","evidence_type":"explicit",
            "context_dependency":"none"}}}])
        result=self.validate(delta,"en destino no entra el camión")
        self.assertFalse(result.accepted.changes.locations[0].set.truck_access.value)

    def test_ambiguity_dominates_conflicting_location_claim(self):
        payload={"schema_version":"3.1","intent":"provide_information",
            "changes":{"lead":{},"locations":[{"ref":"both",
            "ref_evidence_quote":"en uno sí","ref_source":"question_target",
            "set":{"elevator":{"value":True,"evidence_quote":"en uno sí",
            "evidence_type":"explicit","context_dependency":"question_target"}}}]},
            "corrections":[],"ambiguities":[{"field":"elevator","value":"true",
            "possible_refs":["origin","destination"],"evidence_quote":"en uno sí"}]}
        result=self.validate(ConversationDeltaV31.model_validate(payload),"en uno sí",
                             [QuestionTarget("elevator","both")])
        self.assertEqual(result.accepted.changes.locations,[])
        self.assertEqual(result.accepted.ambiguities[0].field,"elevator")

    def test_contextual_quote_cannot_double_as_independent_neighbor_claim(self):
        delta=self.delta(lead={
            "packing_mode":{"value":"embalaje de muebles y artefactos",
                "evidence_quote":"muebles y artefactos","evidence_type":"explicit",
                "context_dependency":"question_target"},
            "load":{"value":"muebles y artefactos",
                "evidence_quote":"muebles y artefactos","evidence_type":"explicit",
                "context_dependency":"none"}})
        result=self.validate(delta,"muebles y artefactos",
                             [QuestionTarget("packing_mode")])
        self.assertIsNotNone(result.accepted.changes.lead.packing_mode)
        self.assertIsNone(result.accepted.changes.lead.load)
        self.assertIn(EVIDENCE_CLAIM_COLLISION,[item.reason for item in result.rejected])

    def test_target_claim_wins_shared_quote_over_neighbor_field(self):
        delta=self.delta(lead={
            "staff_required":{"value":False,"evidence_quote":"solo transporte",
                "evidence_type":"explicit","context_dependency":"none"},
            "service":{"value":"carga","evidence_quote":"solo transporte",
                "evidence_type":"explicit","context_dependency":"none"}})
        result=self.validate(delta,"solo transporte",[QuestionTarget("staff_required")])
        self.assertFalse(result.accepted.changes.lead.staff_required.value)
        self.assertIsNone(result.accepted.changes.lead.service)

    def test_access_claim_without_explicit_endpoint_marker_is_rejected(self):
        delta=self.delta(locations=[{"ref":"origin",
            "ref_evidence_quote":"el carro para a dos cuadras",
            "ref_source":"explicit_message","set":{"access_observation":{
            "value":"a dos cuadras","evidence_quote":"a dos cuadras",
            "evidence_type":"explicit","context_dependency":"none"}}}])
        result=self.validate(delta,"el carro para a dos cuadras")
        self.assertIn(UNVERIFIED_EXPLICIT_REF,[item.reason for item in result.rejected])

    def test_explicit_both_marker_wins_spurious_ambiguity(self):
        payload={"schema_version":"3.1","intent":"provide_information",
            "changes":{"lead":{},"locations":[{"ref":"both",
            "ref_evidence_quote":"en ambos","ref_source":"explicit_message",
            "set":{"access_observation":{"value":"retirado",
            "evidence_quote":"en ambos queda retirado","evidence_type":"explicit",
            "context_dependency":"none"}}}]},"corrections":[],"ambiguities":[{
            "field":"access_observation","value":"retirado",
            "possible_refs":["origin","destination"],
            "evidence_quote":"en ambos queda retirado"}]}
        result=self.validate(ConversationDeltaV31.model_validate(payload),
                             "en ambos queda retirado")
        self.assertEqual(result.accepted.changes.locations[0].ref,"both")

    def test_specific_endpoint_cue_cannot_expand_to_both(self):
        delta=self.delta(locations=[{"ref":"both","ref_evidence_quote":"allá sí",
            "ref_source":"question_target","set":{"elevator":{"value":True,
            "evidence_quote":"allá sí","evidence_type":"explicit",
            "context_dependency":"question_target"}}}])
        result=self.validate(delta,"allá sí",[QuestionTarget("elevator","both")])
        self.assertEqual(result.accepted.changes.locations,[])
        self.assertIn(AMBIGUOUS_REF,[item.reason for item in result.rejected])

    def test_parking_distance_does_not_prove_truck_access(self):
        delta=self.delta(locations=[{"ref":"destination",
            "ref_evidence_quote":"en destino","ref_source":"explicit_message",
            "set":{"truck_access":{"value":True,
            "evidence_quote":"estaciona a 30 metros","evidence_type":"explicit",
            "context_dependency":"none"}}}])
        result=self.validate(delta,"en destino estaciona a 30 metros")
        self.assertIn(UNSUPPORTED_BOOLEAN_EVIDENCE,
                      [item.reason for item in result.rejected])

    def test_object_list_does_not_prove_service(self):
        delta=self.delta(lead={"service":{"value":"traslado pequeno",
            "evidence_quote":"una cama y una lavadora","evidence_type":"explicit",
            "context_dependency":"none"}})
        result=self.validate(delta,"una cama y una lavadora")
        self.assertIn(UNSUPPORTED_SERVICE_EVIDENCE,
                      [item.reason for item in result.rejected])

    def test_uncertain_staff_answer_does_not_set_boolean(self):
        delta=self.delta(lead={"staff_required":{"value":False,
            "evidence_quote":"tal vez necesite gente, no sé",
            "evidence_type":"explicit","context_dependency":"question_target"}})
        result=self.validate(delta,"tal vez necesite gente, no sé",
                             [QuestionTarget("staff_required")])
        self.assertIn(AMBIGUOUS_BOOLEAN_EVIDENCE,
                      [item.reason for item in result.rejected])

    def test_access_missing_fields_generate_truck_targets(self):
        targets=_question_targets(("ubicacion_0_acceso_camion", "ubicacion_1_acceso_camion"))
        self.assertEqual([x.field for x in targets],["truck_access","truck_access"])

    def test_runtime_does_not_import_canonical_evaluator(self):
        root=Path(__file__).parent
        runtime=["conversation_engine.py","delta_extractor.py","delta_extractor_v3.py",
                 "delta_extractor_v31.py","delta_validator_v31.py"]
        self.assertTrue(all("canonical_evaluation" not in (root/name).read_text(encoding="utf-8")
                            for name in runtime))

    def test_packing_only_evidence_cannot_set_staff(self):
        delta=self.delta(lead={"staff_required":{"value":True,
            "evidence_quote":"sí quiero embalaje","evidence_type":"explicit",
            "context_dependency":"none"}})
        result=self.validate(delta,"Finalmente sí quiero embalaje")
        self.assertIsNone(result.accepted.changes.lead.staff_required)
        self.assertIn(UNSUPPORTED_STAFF_EVIDENCE,
                      [item.reason for item in result.rejected])

    def test_literal_ambiguous_ref_becomes_ambiguity(self):
        delta=self.delta(locations=[{"ref":"ambiguous",
            "ref_evidence_quote":"a dos cuadras","ref_source":"explicit_message",
            "set":{"access_observation":{"value":"a dos cuadras",
                "evidence_quote":"a dos cuadras","evidence_type":"explicit",
                "context_dependency":"none"}}}])
        result=self.validate(delta,"el carro para a dos cuadras")
        self.assertEqual(result.accepted.ambiguities[0].field,"access_observation")

    def test_both_complement_can_be_overridden_by_specific_endpoint(self):
        proposal=lambda value:{"value":value,"evidence_quote":"solo en el segundo",
            "evidence_type":"explicit","context_dependency":"question_target"}
        delta=self.delta(locations=[
            {"ref":"both","ref_evidence_quote":"solo en el segundo",
             "ref_source":"question_target","set":{"truck_access":proposal(False)}},
            {"ref":"destination","ref_evidence_quote":"solo en el segundo",
             "ref_source":"question_target","set":{"truck_access":proposal(True)}}])
        target=[QuestionTarget("truck_access","both")]
        result=self.validate(delta,"solo en el segundo",target)
        self.assertEqual(len(result.accepted.changes.locations),2)

    def test_old_contextual_metadata_adapts_without_changing_claim(self):
        old={"schema_version":3,"intent":"provide_information","changes":{"lead":{
            "load":{"value":"20 cajas","evidence":"20 cajas",
                    "evidence_type":"explicit_contextual"}},"locations":[]},
            "corrections":[],"ambiguities":[]}
        adapted=adapt_v3_delta_to_v31(old)
        self.assertEqual(adapted.changes.lead.load.value,"20 cajas")
        self.assertEqual(adapted.changes.lead.load.context_dependency.value,"question_target")

    @patch("apps.ia.delta_extractor_v31.build_provider")
    def test_fake_provider_uses_v31_schema_and_structured_targets(self, build_provider):
        response=self.delta()
        fake=build_provider.return_value
        fake.generate_structured.return_value=AIResult(response.model_dump_json(),"fake","v31",1,2,1)
        target={"field":"elevator","ref":"origin","operation":"set"}
        context=DeltaContext({"state":self.snapshot.state,"last_bot_question":"visible",
            "last_question_targets":[target],"customer_message":"sí","recent_turns":[]},
            "visible",0,(target,))
        parsed,_=extract_conversation_delta_v31(context,provider_name="openai")
        self.assertIs(fake.generate_structured.call_args.kwargs["schema_model"],ConversationDeltaV31)
        self.assertEqual(parsed.schema_version,"3.1")

    def test_blind_holdout_is_frozen_unique_and_contextual(self):
        cases=v31_blind_holdout_cases()
        self.assertEqual(len(cases),100)
        self.assertGreaterEqual(sum(bool(case["question_targets"]) for case in cases),50)
        self.assertGreaterEqual(sum(case["human_review"] for case in cases),10)

    def test_second_holdout_is_disjoint_and_frozen(self):
        first=v31_blind_holdout_cases();second=v31_blind_holdout_round2_cases()
        self.assertEqual(len(second),100)
        self.assertFalse({x["message"] for x in first}&{x["message"] for x in second})

    def test_third_holdout_is_disjoint_and_frozen(self):
        third=v31_blind_holdout_round3_cases()
        self.assertEqual(len(third),100)
        self.assertGreaterEqual(sum(x["human_review"] for x in third),12)
