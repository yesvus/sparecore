"""Fail-closed tests for a manual, node-specific ARC Eviction API gate."""
import importlib.util
import json
import pathlib
import subprocess
import unittest
from unittest.mock import Mock, patch

PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "evict-node-runners.py"
SPEC = importlib.util.spec_from_file_location("evict_node_runners", PATH)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

NODE = "edge-worker-01"
NS = "arc-edge"


def node(name=NODE, cordoned=True, quarantine=True):
    return {
        "metadata": {"name": name, "uid": "uid-node-01", "resourceVersion": "9"},
        "spec": {
            "unschedulable": cordoned,
            "taints": [{"key": "sparecore", "value": "true", "effect": "NoSchedule"}]
                      if quarantine else [],
        },
    }


def pod(name="arc-runner-1", namespace=NS, where=NODE, phase="Pending",
        owner="EphemeralRunner", uid="pod-uid-01"):
    return {
        "metadata": {
            "name": name, "namespace": namespace, "uid": uid,
            "ownerReferences": [{"kind": owner, "controller": True,
                                 "name": "run", "uid": "owner-uid"}],
        },
        "spec": {"nodeName": where},
        "status": {"phase": phase},
    }


class EvictionGateTests(unittest.TestCase):
    def test_fails_closed_on_unschedulable_or_quarantine_gaps(self):
        for bad in (node(cordoned=False), node(quarantine=False)):
            result = gate.inspect(bad, {"items": [pod()]}, NODE, NS)
            self.assertTrue(result["status"].startswith("blocked_"))
            self.assertIsNone(result["candidate"])

    def test_exact_name_and_pod_inventory_is_required(self):
        with self.assertRaises(ValueError):
            gate.inspect(node(), {"items": [pod(where="other")]}, NODE, NS)
        with self.assertRaises(ValueError):
            gate.inspect(node(name="other"), {"items": []}, NODE, NS)
        with self.assertRaises(ValueError):
            gate.inspect(node(), {"items": None}, NODE, NS)
        for invalid in ("--flag", "UPPER", "", "has_underscore"):
            with self.assertRaises(ValueError):
                gate.valid_name(invalid)

    def test_other_namespace_and_untrusted_owners_block(self):
        for p, reason in (
            (pod(namespace="default"), "blocked_foreign_workload"),
            (pod(owner="Deployment"), "blocked_untrusted_owner"),
        ):
            result = gate.inspect(node(), {"items": [p]}, NODE, NS)
            self.assertEqual(result["status"], reason)

    def test_running_jobs_require_explicit_interruption_choice(self):
        active = {"items": [pod(phase="Running")]}
        self.assertEqual(gate.inspect(node(), active, NODE, NS)["status"],
                         "blocked_active_job")
        self.assertEqual(gate.inspect(node(), active, NODE, NS, True)["status"],
                         "eviction_candidate")

    def test_unfinished_or_multiple_pods_never_silently_evicted(self):
        self.assertEqual(gate.inspect(node(), {"items": [
            pod(uid="u1"), pod(name="second", uid="u2")]}, NODE, NS)["status"],
            "blocked_multiple_pods")
        unfinished = pod()
        unfinished["metadata"]["deletionTimestamp"] = "2026-11-15T00:00:00Z"
        self.assertEqual(gate.inspect(node(), {"items": [unfinished]}, NODE, NS)["status"],
                         "blocked_terminating")

    def test_malformed_phase_fails_closed(self):
        malformed = pod()
        malformed["status"] = "unexpected"
        with self.assertRaises(ValueError):
            gate.inspect(node(), {"items": [malformed]}, NODE, NS)
        malformed["status"] = None
        with self.assertRaises(ValueError):
            gate.inspect(node(), {"items": [malformed]}, NODE, NS)

    def test_no_pods_does_not_grant_vm_shutdown(self):
        with patch.object(gate.platform, "system", return_value="Linux"), \
                patch.object(gate, "_inventory", return_value=(node(), {"items": []})), \
                patch.object(gate, "_run") as run:
            result, code = gate.execute(NODE, NS, "audit", "evict")
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "no_pods_observed")
        self.assertIs(result["shutdown_authorized"], False)
        run.assert_not_called()

    def test_read_only_default_does_not_request_eviction(self):
        with patch.object(gate.platform, "system", return_value="Linux"), \
                patch.object(gate, "_inventory", return_value=(node(), {"items": [pod()]})), \
                patch.object(gate, "_run") as run:
            result, code = gate.execute(NODE, NS, "audit", "evict")
        self.assertEqual((result["status"], result["applied"], code),
                         ("would_request_eviction", False, 0))
        run.assert_not_called()

    def test_requires_two_distinct_contexts_and_confirmation(self):
        with patch.object(gate.platform, "system", return_value="Linux"), \
                patch.object(gate, "_inventory") as inventory:
            for audit, evict in ((None, "evict"), ("audit", None), ("same", "same")):
                self.assertEqual(gate.execute(NODE, NS, audit, evict)[1], 3)
            self.assertEqual(gate.execute(NODE, NS, "audit", "evict", True, "other")[1], 3)
            inventory.assert_not_called()

    def test_non_linux_trusted_host_only(self):
        with patch.object(gate.platform, "system", return_value="Darwin"), \
                patch.object(gate, "_inventory") as inventory:
            self.assertEqual(gate.execute(NODE, NS, "a", "b")[1], 3)
            inventory.assert_not_called()

    def test_scoped_auth_uses_namespaced_allow_and_denies(self):
        with patch.object(gate.subprocess, "run") as process:
            process.side_effect = [
                Mock(returncode=0, stdout="yes\n"),
                Mock(returncode=1, stdout="no\n"),
                Mock(returncode=0, stdout="no\n"),
            ]
            self.assertTrue(gate._verify_namespaced_context("scoped", NS))
            for call in process.call_args_list:
                self.assertIn("--subresource=eviction", call.args[0])
                self.assertEqual(call.kwargs["stdin"], subprocess.DEVNULL)
                self.assertFalse(call.kwargs.get("shell", False))
        with patch.object(gate.subprocess, "run", return_value=Mock(returncode=0, stdout="yes\n")):
            self.assertFalse(gate._verify_namespaced_context("broad", NS))
        with patch.object(gate.subprocess, "run", return_value=Mock(returncode=3, stdout="???\n")):
            with self.assertRaises(RuntimeError):
                gate._verify_namespaced_context("broken", NS)

    def _apply(self, candidate=None, run_side_effect=None):
        target = candidate or pod()
        ctx = {"node": node(), "pods": {"items": [target]}}
        with patch.object(gate.platform, "system", return_value="Linux"), \
                patch.object(gate, "_inventory", side_effect=[
                    (ctx["node"], ctx["pods"]), (ctx["node"], ctx["pods"])]), \
                patch.object(gate, "_verify_namespaced_context", return_value=True), \
                patch.object(gate, "_get", return_value=target), \
                patch.object(gate, "_run", side_effect=run_side_effect) as run:
            result, code = gate.execute(NODE, NS, "audit", "evict",
                                        apply=True, confirm_node=NODE)
            return result, code, run

    def test_native_eviction_uses_uid_precondition_never_delete(self):
        result, code, run = self._apply()
        self.assertEqual((result["status"], result["applied"], code),
                         ("eviction_requested_not_completed", True, 3))
        self.assertIs(result["shutdown_authorized"], False)
        self.assertEqual(run.call_count, 1)
        context, cmd, body = run.call_args.args
        self.assertEqual(context, "evict")
        self.assertEqual(cmd[:2], ["create", "--raw"])
        self.assertEqual(cmd[2], "/api/v1/namespaces/arc-edge/pods/arc-runner-1/eviction")
        self.assertEqual(cmd[-2:], ["-f", "-"])
        evict = json.loads(body)
        self.assertEqual(evict["kind"], "Eviction")
        self.assertEqual(evict["apiVersion"], "policy/v1")
        self.assertEqual(evict["deleteOptions"]["preconditions"]["uid"], "pod-uid-01")

    def test_pdb_429_and_api_timeout_do_not_grant_shutdown(self):
        for failure in (RuntimeError("TooManyRequests (429)"),
                        subprocess.TimeoutExpired(["kubectl"], 10)):
            result, code, _ = self._apply(run_side_effect=failure)
            self.assertEqual((result["status"], result["applied"], code),
                             ("eviction_blocked_or_unknown", "unknown", 2))
            self.assertFalse(result["shutdown_authorized"])

    def test_stale_node_or_changed_pod_blocks_before_mutation(self):
        first_node = node()
        second_node = node()
        second_node["metadata"]["uid"] = "replacement"
        with patch.object(gate.platform, "system", return_value="Linux"), \
                patch.object(gate, "_inventory", side_effect=[
                    (first_node, {"items": [pod()]}),
                    (second_node, {"items": [pod()]})]), \
                patch.object(gate, "_verify_namespaced_context", return_value=True), \
                patch.object(gate, "_run") as run:
            result, code = gate.execute(NODE, NS, "audit", "evict", True, NODE)
            self.assertEqual((result["status"], code),
                             ("blocked_inventory_changed", 3))
            run.assert_not_called()

    def test_changed_scoped_pod_identity_blocks_before_mutation(self):
        bad = pod(owner="Deployment")
        with patch.object(gate.platform, "system", return_value="Linux"), \
                patch.object(gate, "_inventory", return_value=(node(), {"items": [pod()]})), \
                patch.object(gate, "_verify_namespaced_context", return_value=True), \
                patch.object(gate, "_get", return_value=bad), \
                patch.object(gate, "_run") as run:
            result, code = gate.execute(NODE, NS, "audit", "evict", True, NODE)
            self.assertEqual((result["status"], code),
                             ("blocked_pod_identity_changed", 3))
            run.assert_not_called()

    def test_different_node_and_namespace_names_are_not_hard_coded(self):
        custom = "laptop-02.example"
        target_ns = "trusted-ci"
        output = gate.inspect(node(name=custom), {"items": [
            pod(where=custom, namespace=target_ns)]}, custom, target_ns)
        self.assertEqual(output["status"], "eviction_candidate")
        self.assertEqual(output["candidate"]["namespace"], target_ns)


if __name__ == "__main__":
    unittest.main()
