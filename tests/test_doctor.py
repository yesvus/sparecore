import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from sparecore.doctor import inspect_environment


class DoctorTests(TestCase):
    def test_mac_missing_optional_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            checks = inspect_environment(
                system="Darwin", home=tmp,
                find_executable=lambda cmd: "/usr/bin/python3" if cmd == "python3" else None)
            by_name = {c.name: c for c in checks}
            self.assertEqual(by_name["macOS"].status, "ok")
            self.assertEqual(by_name["Python"].status, "ok")
            self.assertEqual(by_name["Tailscale (optional)"].status, "optional")
            self.assertEqual(by_name["Lima (optional worker)"].status, "optional")
            self.assertEqual(by_name["OrbStack (optional)"].status, "optional")
            self.assertEqual(by_name["Menu configuration"].status, "missing")
            self.assertFalse((Path(tmp) / ".hammerspoon").exists())

    def test_existing_menu_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".hammerspoon"
            path.mkdir()
            (path / "init.lua").write_text("example")
            checks = inspect_environment("Darwin", tmp, lambda _: "/somewhere")
            self.assertEqual(
                next(c for c in checks if c.name == "Menu configuration").status, "ok")

    def test_non_macos_reports_unsupported(self):
        checks = inspect_environment("Linux", "/tmp", lambda _: None)
        self.assertEqual(checks[0].status, "unsupported")

    def test_json_cli(self):
        result = subprocess.run([sys.executable, "-m", "sparecore", "doctor", "--json"],
                                capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["mode"], "observe-only")
        self.assertIn("checks", data)
        self.assertEqual(len(data["checks"]), 7)

    def test_decide_needs_input(self):
        result = subprocess.run([sys.executable, "-m", "sparecore", "decide"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
