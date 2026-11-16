"""One-shot Lima actuation tests: no Kubernetes credentials or VM writes by default."""
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from sparecore import lima_control as control

VM = "edge-worker"
NODE = "edge-node"
NS = "trusted-runners"
ALIAS = "sparecore-audit"

SAFE = {"tier": "boost", "on_ac": True, "memory_pressure": "1",
        "status_age_seconds": 3}
STOPPED = {"name": VM, "vm": "stopped", "isolation_verified": True}
RUNNING = {"name": VM, "vm": "running", "isolation_verified": True}


def invoke(action, apply=False):
    return control.execute(action, VM, NODE, NS, ALIAS, apply, VM, NODE)


class LimaOneShotTests(unittest.TestCase):
    def test_target_names_are_checked_before_any_io(self):
        for kind, bad in (("vm", "--x"), ("node", "a..b"),
                          ("namespace", "UPPER"), ("ssh_alias", "-Proxy")):
            with self.assertRaises(ValueError):
                control._validate(bad, kind)

    def test_non_mac_does_not_inspect_or_run_any_command(self):
        with patch.object(control.platform, "system", return_value="Linux"), \
                patch.object(control, "_guest_summary") as guest:
            result, code = invoke("start", True)
        self.assertEqual((result["status"], code), ("blocked_non_macos", 3))
        guest.assert_not_called()

    @patch.object(control.platform, "system", return_value="Darwin")
    @patch.object(control, "_guest_summary", return_value=STOPPED)
    def test_no_apply_never_starts_vm(self, guest, platform):
        with patch.object(control, "_host_summary", return_value=SAFE), \
                patch.object(control, "_probe_node", return_value={}), \
                patch.object(control, "_command") as cmd:
            result, code = invoke("start")
        self.assertEqual((result["status"], result["applied"], code),
                         ("would_start", False, 0))
        cmd.assert_not_called()

    @patch.object(control.platform, "system", return_value="Darwin")
    @patch.object(control, "_guest_summary", return_value=STOPPED)
    def test_confirmation_is_exact_and_blocks_before_probes(self, guest, platform):
        with patch.object(control, "_probe_node") as probe:
            result, code = control.execute("start", VM, NODE, NS, ALIAS,
                                           apply=True, confirm_vm=VM,
                                           confirm_node="different-node")
        self.assertEqual((result["status"], code), ("blocked_confirmation", 3))
        result, code = control.execute("start", VM, NODE, NS, ALIAS,
                                       apply=True, confirm_vm="different-vm",
                                       confirm_node=NODE)
        self.assertEqual((result["status"], code), ("blocked_confirmation", 3))
        probe.assert_not_called()

    @patch.object(control.platform, "system", return_value="Darwin")
    @patch.object(control, "_guest_summary", return_value=STOPPED)
    def test_battery_active_unknown_or_stale_never_starts(self, guest, platform):
        variations = [
            dict(SAFE, tier="off"), dict(SAFE, tier="light"),
            dict(SAFE, on_ac=False), dict(SAFE, memory_pressure="2"),
            dict(SAFE, status_age_seconds=61),
            dict(SAFE, status_age_seconds=None),
        ]
        with patch.object(control, "_probe_node") as probe, \
                patch.object(control, "_command") as command:
            for h in variations:
                with patch.object(control, "_host_summary", return_value=h):
                    result, code = invoke("start", True)
                    self.assertEqual((result["status"], code),
                                     ("blocked_host_safety", 3))
            probe.assert_not_called()
            command.assert_not_called()

    @patch.object(control.platform, "system", return_value="Darwin")
    def test_unknown_or_unsafe_guest_fails_before_probe(self, platform):
        with patch.object(control, "_guest_summary", return_value={
            "vm": "unknown", "isolation_verified": False
        }), patch.object(control, "_probe_node") as probe:
            self.assertEqual(invoke("start", True)[0]["status"],
                             "blocked_unverified_vm")
            probe.assert_not_called()

    @patch.object(control.platform, "system", return_value="Darwin")
    @patch.object(control, "_guest_summary", return_value=STOPPED)
    def test_cluster_unreachable_blocks_start(self, guest, platform):
        with patch.object(control, "_host_summary", return_value=SAFE), \
                patch.object(control, "_probe_node", side_effect=RuntimeError("no ssh")), \
                patch.object(control, "_command") as cmd:
            result, code = invoke("start", True)
        self.assertEqual((result["status"], code), ("blocked_cluster_unknown", 3))
        cmd.assert_not_called()

    def test_ssh_command_uses_no_shell_or_interactive_stdin(self):
        report = {"status": "no_pods_observed", "node": NODE,
                  "bound_vm": VM, "node_uid": "node-uid-1",
                  "vm_binding_verified": True,
                  "node_cordoned": True, "taint_present": True,
                  "foreign_pods": [], "runner_pods": [], "applied": False}
        with patch.object(control.subprocess, "run",
                          return_value=Mock(returncode=0,
                                            stdout=json.dumps(report))) as run:
            out = control._probe_node(ALIAS, VM, NODE, NS)
        self.assertEqual(out["status"], "no_pods_observed")
        args = run.call_args.args[0]
        self.assertEqual(args[0], "ssh")
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertIn("BatchMode=yes", args)
        self.assertIn("sparecore-readonly-node-check", args)
        self.assertEqual(args[-2:], ["--vm", VM])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_cluster_probe_rejects_foreign_workload_or_wrong_node(self):
        good = {"status": "no_pods_observed", "node": NODE,
                "bound_vm": VM, "node_uid": "node-uid-1",
                "vm_binding_verified": True,
                "node_cordoned": True, "taint_present": True,
                "foreign_pods": [], "runner_pods": [], "applied": False}
        for bad in (dict(good, node="other"),
                    dict(good, bound_vm="different-vm"),
                    dict(good, node_uid=""),
                    dict(good, vm_binding_verified=False),
                    dict(good, status="review_runner_evictions"),
                    dict(good, node_cordoned=False),
                    dict(good, runner_pods=[{"name": "busy"}]),
                    dict(good, foreign_pods=[{"name": "foreign"}]),
                    dict(good, taint_present=False),
                    dict(good, applied=True)):
            with patch.object(control, "_command",
                              return_value=Mock(returncode=0,
                                                stdout=json.dumps(bad))):
                with self.assertRaises(RuntimeError):
                    control._probe_node(ALIAS, VM, NODE, NS)

    @patch.object(control.platform, "system", return_value="Darwin")
    def test_start_checks_twice_and_verifies_running(self, platform):
        with patch.object(control, "_guest_summary",
                          side_effect=[STOPPED, STOPPED, RUNNING]) as guest, \
                patch.object(control, "_host_summary",
                             side_effect=[SAFE, SAFE]) as host, \
                patch.object(control, "_probe_node", return_value={}) as probe, \
                patch.object(control, "_command",
                             return_value=Mock(returncode=0)) as cmd:
            result, code = invoke("start", True)
        self.assertEqual((result["status"], result["applied"], code),
                         ("start_verified", True, 0))
        self.assertEqual(guest.call_count, 3)
        self.assertEqual(host.call_count, 2)
        self.assertEqual(probe.call_count, 2)
        probe.assert_called_with(ALIAS, VM, NODE, NS)
        self.assertEqual(cmd.call_args.args[0][:4],
                         ["limactl", "start", "--tty=false", "--timeout=70s"])

    @patch.object(control.platform, "system", return_value="Darwin")
    def test_new_host_activity_before_start_blocks(self, platform):
        with patch.object(control, "_guest_summary", return_value=STOPPED), \
                patch.object(control, "_host_summary",
                             side_effect=[SAFE, dict(SAFE, tier="light")]), \
                patch.object(control, "_probe_node", return_value={}), \
                patch.object(control, "_command") as cmd:
            result, code = invoke("start", True)
        self.assertEqual((result["status"], code),
                         ("blocked_host_safety_changed", 3))
        cmd.assert_not_called()

    @patch.object(control.platform, "system", return_value="Darwin")
    def test_stop_only_when_node_is_confirmed_empty(self, platform):
        with patch.object(control, "_guest_summary",
                          side_effect=[RUNNING, RUNNING, STOPPED]), \
                patch.object(control, "_host_summary") as host, \
                patch.object(control, "_probe_node", return_value={}), \
                patch.object(control, "_command",
                             return_value=Mock(returncode=0)) as cmd:
            result, code = invoke("stop", True)
        self.assertEqual((result["status"], result["applied"], code),
                         ("stop_verified", True, 0))
        cmd.assert_called_once_with(["limactl", "stop", VM], timeout=60)
        host.assert_not_called()

    @patch.object(control.platform, "system", return_value="Darwin")
    def test_mutation_timeout_never_claims_no_change(self, platform):
        with patch.object(control, "_guest_summary", return_value=RUNNING), \
                patch.object(control, "_probe_node", return_value={}), \
                patch.object(control, "_command",
                             side_effect=subprocess.TimeoutExpired(["limactl"], 60)):
            result, code = invoke("stop", True)
        self.assertEqual((result["status"], result["applied"], code),
                         ("vm_mutation_unknown", "unknown", 2))

    @patch.object(control.platform, "system", return_value="Darwin")
    def test_no_action_on_already_correct_vm_state(self, platform):
        with patch.object(control, "_guest_summary", return_value=STOPPED), \
                patch.object(control, "_probe_node") as probe:
            result, code = invoke("stop", True)
        self.assertEqual((result["status"], code), ("already_stopped", 0))
        probe.assert_called_once_with(ALIAS, VM, NODE, NS)

    @patch.object(control.platform, "system", return_value="Darwin")
    def test_guest_isolation_changed_before_mutation(self, platform):
        changed = dict(STOPPED, isolation_verified=False)
        with patch.object(control, "_guest_summary", side_effect=[STOPPED, changed]), \
                patch.object(control, "_host_summary", return_value=SAFE), \
                patch.object(control, "_probe_node", return_value={}) as probe, \
                patch.object(control, "_command") as command:
            result, code = invoke("start", True)
        self.assertEqual((result["status"], code), ("blocked_vm_state_changed", 3))
        probe.assert_called_once()
        command.assert_not_called()

    @patch.object(control.platform, "system", return_value="Darwin")
    def test_second_cluster_probe_failure_prevents_stop(self, platform):
        with patch.object(control, "_guest_summary", return_value=RUNNING), \
                patch.object(control, "_probe_node", side_effect=[{}, RuntimeError("offline")]) as probe, \
                patch.object(control, "_command") as command:
            result, code = invoke("stop", True)
        self.assertEqual((result["status"], code), ("blocked_cluster_changed", 3))
        self.assertEqual(probe.call_count, 2)
        command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
