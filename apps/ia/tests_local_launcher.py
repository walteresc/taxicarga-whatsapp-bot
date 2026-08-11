import os
import subprocess
from pathlib import Path

from django.test import SimpleTestCase


class LocalLauncherTests(SimpleTestCase):
    def test_stale_parent_openai_key_is_removed_before_django(self):
        root = Path(__file__).resolve().parents[2]
        stale = "STALE_TEST_VALUE_NOT_A_SECRET"
        environment = os.environ.copy()
        environment["OPENAI_API_KEY"] = stale
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(root / "run_local.ps1"), "check_local_env_source",
             "--reject-value", stale],
            cwd=root, env=environment, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LOCAL_OPENAI_KEY_SOURCE=PROJECT_ENV OK", result.stdout)

    def test_launcher_pins_project_virtualenv(self):
        script = (Path(__file__).resolve().parents[2] / "run_local.ps1").read_text(
            encoding="utf-8")
        self.assertIn('.venv\\Scripts\\python.exe', script)
        self.assertNotIn('SetEnvironmentVariable("OPENAI_API_KEY"', script)
