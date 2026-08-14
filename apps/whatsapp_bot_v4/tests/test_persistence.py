from django.test import TestCase

from ..domain.merge import merge_state
from ..domain.requirements import ready_to_quote, required_missing
from ..domain.state import Access, BotState
from ..models import BotConversationState
from ..repositories.state import DjangoBotStateRepository


class PersistenceTests(TestCase):
    def setUp(self):
        self.repository = DjangoBotStateRepository()
        self.key = "test:persistence"

    def test_new_conversation_creates_state(self):
        self.assertEqual(self.repository.load(self.key), BotState())
        self.assertTrue(BotConversationState.objects.filter(conversation_key=self.key).exists())

    def test_state_persists(self):
        self.repository.save(self.key, BotState(origin_district="Surco"))
        self.assertEqual(self.repository.load(self.key).origin_district, "Surco")

    def test_reload_with_new_repository_preserves_state(self):
        self.repository.save(self.key, BotState(origin_district="Surco"))
        self.assertEqual(DjangoBotStateRepository().load(self.key).origin_district, "Surco")

    def test_partial_update_preserves_previous_fields(self):
        state = self.repository.save(self.key, BotState(origin_district="Surco"))
        state = merge_state(state, {"destination_district": "Miraflores"}, {})
        self.repository.save(self.key, state)
        loaded = self.repository.load(self.key)
        self.assertEqual((loaded.origin_district, loaded.destination_district), ("Surco", "Miraflores"))

    def test_null_does_not_overwrite(self):
        state = merge_state(BotState(origin_district="Surco"), {"origin_district": None}, {})
        self.repository.save(self.key, state)
        self.assertEqual(self.repository.load(self.key).origin_district, "Surco")

    def test_explicit_correction_overwrites(self):
        state = merge_state(BotState(origin_district="Surco"), {}, {"origin_district": "San Borja"})
        self.repository.save(self.key, state)
        self.assertEqual(self.repository.load(self.key).origin_district, "San Borja")

    def test_floor_one_persists_not_applicable(self):
        state = merge_state(BotState(), {"origin_floor": 1}, {})
        self.repository.save(self.key, state)
        self.assertEqual(self.repository.load(self.key).origin_access, Access.NOT_APPLICABLE)

    def test_upper_floor_requires_access_after_reload(self):
        self.repository.save(self.key, BotState(origin_floor=3))
        self.assertIn("origin_access", required_missing(self.repository.load(self.key)))

    def test_items_persist(self):
        self.repository.save(self.key, BotState(items=["1 cama", "10 cajas"]))
        self.assertEqual(self.repository.load(self.key).items, ["1 cama", "10 cajas"])

    def test_ready_to_quote_survives_reload(self):
        state = BotState("Surco", "Miraflores", 1, 2, Access.NOT_APPLICABLE, Access.STAIRS, ["cama"])
        self.repository.save(self.key, state)
        self.assertTrue(ready_to_quote(self.repository.load(self.key)))
        self.assertEqual(BotConversationState.objects.get(conversation_key=self.key).status, "ready_to_quote")
