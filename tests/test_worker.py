import unittest
from sparecore.worker import WorkerState, plan


def state(**updates):
    values = dict(tier="off", vm="stopped", node_ready=None, node_cordoned=True,
                  workloads=0, enabled=False, admission_verified=False)
    values.update(updates)
    return WorkerState(**values)


class WorkerPlannerTests(unittest.TestCase):
    def test_no_optin_never_starts_or_admits(self):
        for tier in ("off", "light", "boost"):
            self.assertEqual(plan(state(tier=tier)).step, "none")

    def test_light_never_starts_even_when_opted_in(self):
        self.assertEqual(plan(state(enabled=True, tier="light")).step, "none")

    def test_only_boost_and_explicit_optin_start(self):
        self.assertEqual(plan(state(enabled=True, tier="boost")).step, "start_vm")

    def test_stopped_vm_does_not_excuse_uncordoned_node(self):
        for enabled in (True, False):
            for tier in ("off", "light", "boost"):
                result = plan(state(tier=tier, vm="stopped",
                                    node_cordoned=False, enabled=enabled))
                self.assertEqual(result.step, "cordon")

    def test_unknown_admission_with_stopped_vm_is_not_clear(self):
        p = plan(state(vm="stopped", node_cordoned=None))
        self.assertEqual(p.step, "inspect")

    def test_cordon_precedes_eviction_on_owner_activity(self):
        p = plan(state(enabled=True, tier="off", vm="running", node_cordoned=False,
                       workloads=2))
        self.assertEqual(p.step, "cordon")

    def test_no_stop_if_workloads_exist(self):
        p = plan(state(enabled=True, tier="off", vm="running", node_cordoned=True,
                       workloads=2))
        self.assertEqual(p.step, "drain")

    def test_never_stop_when_pods_unknown(self):
        p = plan(state(enabled=False, vm="running", node_cordoned=True,
                       workloads=None))
        self.assertEqual(p.step, "inspect")

    def test_stop_only_after_cordon_and_empty_workloads(self):
        p = plan(state(enabled=True, tier="light", vm="running", node_cordoned=True,
                       workloads=0))
        self.assertEqual(p.step, "stop_vm")

    def test_unknown_node_safety_does_not_stop(self):
        p = plan(state(enabled=True, tier="off", vm="running",
                       node_cordoned=None, workloads=0))
        self.assertEqual(p.step, "inspect")

    def test_boost_requires_node_readiness_and_admission(self):
        base = state(enabled=True, tier="boost", vm="running", node_ready=True,
                     node_cordoned=True)
        self.assertEqual(plan(base).step, "none")
        self.assertEqual(plan(state(enabled=True, tier="boost", vm="running",
                                    node_ready=False, admission_verified=True)).step, "inspect")
        self.assertEqual(plan(state(enabled=True, tier="boost", vm="running",
                                    node_ready=True, node_cordoned=True,
                                    admission_verified=True)).step, "admit")

    def test_disabled_forces_cordon_even_on_boost(self):
        p = plan(state(tier="boost", vm="running", node_ready=True,
                       node_cordoned=False, workloads=0))
        self.assertEqual(p.step, "cordon")

    def test_invalid_input_rejected(self):
        with self.assertRaises(ValueError):
            state(workloads=-1)
        with self.assertRaises(ValueError):
            state(enabled="yes")
        with self.assertRaises(ValueError):
            state(node_cordoned="false")
        with self.assertRaises(ValueError):
            state(vm="start")

    def test_none_applied(self):
        for s in (state(), state(enabled=True,tier="boost"),
                  state(enabled=True, tier="off",vm="running")):
            self.assertFalse(plan(s).applied)

if __name__ == "__main__":
    unittest.main()
