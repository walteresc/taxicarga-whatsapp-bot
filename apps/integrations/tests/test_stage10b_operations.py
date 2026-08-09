import logging
import os
import tempfile
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.test import override_settings
from django.contrib.auth import get_user_model

from config.logging_filters import SanitizePIIFilter
from config.settings import env_value
from apps.integrations.models import WorkerHeartbeat


class Stage10BHealthTests(TestCase):
    def test_health_and_real_404(self):
        self.assertEqual(self.client.get("/health/live").status_code, 200)
        self.assertEqual(self.client.get("/health/ready").status_code, 200)
        self.assertEqual(self.client.get("/does-not-exist").status_code, 404)


class Stage10BOperationsTests(TestCase):
    @override_settings(STRICT_ADMIN_OPERATIONS=True)
    def test_production_gate_blocks_non_admin_channel_mutation(self):
        user = get_user_model().objects.create_user(username="operator", password="test")
        self.client.force_login(user)
        response = self.client.post("/api/whatsapp-channels/", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_worker_once_updates_heartbeat_without_external_calls(self):
        with patch("apps.integrations.management.commands.run_integration_worker.process_meta_outbox_event") as meta:
            call_command("run_integration_worker", once=True, interval=0.1, batch_size=1)
        self.assertTrue(WorkerHeartbeat.objects.filter(name="integration").exists())
        meta.assert_not_called()

    def test_status_is_sanitized(self):
        output = StringIO()
        call_command("integration_status", stdout=output)
        self.assertIn("enabled_channels=0", output.getvalue())

    def test_var_file(self):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as handle:
            handle.write("file-secret\n")
            path = handle.name
        try:
            with patch.dict(os.environ, {"STAGE10B_SECRET_FILE": path}, clear=False):
                self.assertEqual(env_value("STAGE10B_SECRET"), "file-secret")
        finally:
            os.unlink(path)

    def test_log_filter_masks_phone_and_secret(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "phone=+51987654321 access_token=abc", (), None)
        SanitizePIIFilter().filter(record)
        self.assertNotIn("987654321", record.getMessage())
        self.assertNotIn("abc", record.getMessage())
