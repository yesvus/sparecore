import subprocess
from unittest import TestCase
from unittest.mock import patch
from sparecore.macos import pressure_level, memory_safe


class MemoryProbeTests(TestCase):
    def test_normal_and_idle_swap_safe(self):
        self.assertTrue(memory_safe(1, 0))
        self.assertTrue(memory_safe(1, 1))

    def test_swap_churn_blocks_boost(self):
        self.assertFalse(memory_safe(1, 2))

    def test_warning_and_critical_unsafe(self):
        self.assertFalse(memory_safe(2, 0))
        self.assertFalse(memory_safe(4, None))

    def test_missing_probe_fails_closed(self):
        self.assertIsNone(memory_safe(None, 0))
        self.assertIsNone(memory_safe(1, None))
        self.assertIsNone(memory_safe(1, float("nan")))

    @patch("sparecore.macos.subprocess.run")
    def test_sysctl_success(self, run):
        run.return_value.stdout = "1\n"
        self.assertEqual(pressure_level(), 1)
        run.assert_called_once()

    @patch("sparecore.macos.subprocess.run")
    def test_sysctl_missing_or_unknown(self, run):
        run.return_value.stdout = "3\n"
        self.assertIsNone(pressure_level())
        run.side_effect = subprocess.TimeoutExpired("sysctl", 1)
        self.assertIsNone(pressure_level())
