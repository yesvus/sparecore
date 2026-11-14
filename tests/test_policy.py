import unittest
from sparecore import Signals, decide

def sample(**kw):
    d = dict(on_ac=True,idle_seconds=0,displays_asleep=False,cpu_busy_percent=10,memory_safe=True,mode="auto")
    d.update(kw)
    return Signals(**d)

class PolicyTest(unittest.TestCase):
    def test_interactive(self):
        self.assertEqual(decide(sample()).tier,"light")
    def test_idle(self):
        self.assertEqual(decide(sample(idle_seconds=360)).tier,"boost")
    def test_screen_sleep(self):
        self.assertEqual(decide(sample(displays_asleep=True)).tier,"boost")
    def test_battery_even_manual_on(self):
        self.assertEqual(decide(sample(on_ac=False,mode="on")).tier,"off")
    def test_manual_off(self):
        self.assertEqual(decide(sample(mode="off")).tier,"off")
    def test_pressure(self):
        self.assertEqual(decide(sample(memory_safe=False)).tier,"off")
        self.assertEqual(decide(sample(cpu_busy_percent=85)).tier,"off")
    def test_unknown(self):
        self.assertEqual(decide(sample(cpu_busy_percent=None)).tier,"off")
        self.assertEqual(decide(sample(memory_safe=None,idle_seconds=600)).tier,"light")
    def test_active_blocks_boost(self):
        self.assertEqual(decide(sample(cpu_busy_percent=50,idle_seconds=600)).tier,"light")
    def test_rejects_bad_signals(self):
        with self.assertRaises(ValueError):
            sample(cpu_busy_percent=float("nan"))
        with self.assertRaises(ValueError):
            sample(on_ac="yes")
        with self.assertRaises(ValueError):
            sample(mode="force")
