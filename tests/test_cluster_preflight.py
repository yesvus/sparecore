"""Mocked tests for trusted-host read-only drain inspection."""
import importlib.util
import json
import pathlib
import subprocess
import unittest
from unittest.mock import Mock, patch

MODULE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check-node-drain.py"
spec = importlib.util.spec_from_file_location("check_node_drain", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def node(cordoned=True, tainted=True):
    return {"metadata": {"name": "edge-worker-01", "uid": "node-uid-1",
                         "annotations": {"sparecore.dev/lima-vm": "example-vm"}}, "spec": {
        "unschedulable": cordoned,
        "taints": [{"key": "sparecore", "value": "true",
                    "effect": "NoSchedule"}] if tainted else [],
    }}


def pod(name="runner", ns="arc-edge", node_name="edge-worker-01"):
    return {"metadata": {"name": name, "namespace": ns},
            "spec": {"nodeName": node_name}, "status": {"phase": "Running"}}


class DrainSafetyChecks(unittest.TestCase):
    def inspect(self, node_data, pod_data, name="edge-worker-01",
                namespace="arc-edge"):
        return module.inspect(node_data, pod_data, name, namespace)

    def test_no_pods_requires_cordon_and_taint(self):
        self.assertEqual(self.inspect(node(), {"items": []})["status"],
                         "no_pods_observed")

    def test_opt_in_vm_binding_must_match_native_node_annotation(self):
        result = module.inspect(node(), {"items": []}, "edge-worker-01",
                                "arc-edge", vm_name="example-vm")
        self.assertEqual(result["bound_vm"], "example-vm")
        self.assertEqual(result["node_uid"], "node-uid-1")
        self.assertTrue(result["vm_binding_verified"])
        for bad_vm in ("wrong-vm", "Upper_wrong?"):
            with self.assertRaises(ValueError):
                module.inspect(node(), {"items": []}, "edge-worker-01",
                               "arc-edge", vm_name=bad_vm)
        no_annotation = node()
        no_annotation["metadata"]["annotations"] = {}
        with self.assertRaises(ValueError):
            module.inspect(no_annotation, {"items": []}, "edge-worker-01",
                           "arc-edge", vm_name="example-vm")
        no_uid = node()
        del no_uid["metadata"]["uid"]
        with self.assertRaises(ValueError):
            module.inspect(no_uid, {"items": []}, "edge-worker-01",
                           "arc-edge", vm_name="example-vm")

    def test_uncordoned_blocks(self):
        self.assertEqual(self.inspect(node(cordoned=False), {"items": []})["status"],
                         "block_admission_not_closed")

    def test_missing_taint_blocks(self):
        self.assertEqual(self.inspect(node(tainted=False), {"items": []})["status"],
                         "block_admission_not_closed")

    def test_foreign_namespace_blocks_even_daemonsets(self):
        result = self.inspect(node(), {"items": [
            pod(name="cni", ns="kube-system"), pod()]})
        self.assertEqual(result["status"], "block_foreign_workloads")
        self.assertEqual(result["foreign_pods"][0]["name"], "cni")

    def test_runner_pod_requires_review_not_shutdown(self):
        self.assertEqual(self.inspect(node(), {"items": [pod()]})["status"],
                         "review_runner_evictions")

    def test_wrong_node_aborts(self):
        with self.assertRaises(ValueError):
            self.inspect(node(), {"items": [pod(node_name="worker-02")]})

    def test_bad_inventory_aborts(self):
        with self.assertRaises(ValueError):
            self.inspect(node(), {"items": None})

    def test_null_pod_status_rejected(self):
        broken = pod()
        broken["status"] = "unexpected"
        with self.assertRaises(ValueError):
            self.inspect(node(), {"items": [broken]})

    def test_missing_node_metadata_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect({"metadata": None, "spec": node()["spec"]}, {"items": []})

    def test_none_of_this_ever_claims_application(self):
        for pods in ([], [pod()], [pod(ns="default")]):
            self.assertFalse(self.inspect(node(), {"items": pods})["applied"])

    def test_alternate_node_and_namespace(self):
        target = "worker-02"
        alt_node = node()
        alt_node["metadata"]["name"] = target
        result = self.inspect(alt_node, {"items": [pod(ns="trusted-runner",
                                                      node_name=target)]},
                              target, "trusted-runner")
        self.assertEqual(result["status"], "review_runner_evictions")
        self.assertEqual(result["node"], target)

    def test_invalid_names_fail_closed(self):
        for bad in ("--context", "UPPER", ""):
            with self.assertRaises(ValueError):
                module.validate_name(bad)
            with self.assertRaises(ValueError):
                module.validate_name(bad, "namespace")

    @patch.object(module.subprocess, "run")
    def test_get_invokes_only_read_only_kubectl(self, run):
        run.return_value = Mock(stdout=json.dumps({"items": []}))
        module._get(["pods", "--all-namespaces", "--field-selector",
                     "spec.nodeName=zombie"])
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["kubectl", "get"])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    @patch.object(module.subprocess, "run")
    def test_empty_context_rejected_before_kubectl(self, run):
        self.assertEqual(module.main(["--node", "edge-worker-01",
                                      "--runner-namespace", "arc-edge",
                                      "--context", ""]), 2)
        run.assert_not_called()

    def test_inspector_keeps_docstring(self):
        self.assertIn("Pure check", module.inspect.__doc__)

    @patch.object(module, "_get", side_effect=TimeoutError())
    def test_no_api_fails_closed(self, _):
        self.assertEqual(module.main(["--node", "edge-worker-01", "--runner-namespace", "arc-edge"]), 2)

    @patch.object(module, "_get")
    def test_main_no_pods(self, get):
        get.side_effect = [node(), {"items": []}]
        self.assertEqual(module.main(["--node", "edge-worker-01", "--runner-namespace", "arc-edge"]), 0)

    @patch.object(module, "_get")
    def test_main_with_vm_requires_binding(self, get):
        get.side_effect = [node(), {"items": []}]
        self.assertEqual(module.main(["--node", "edge-worker-01",
                                      "--runner-namespace", "arc-edge",
                                      "--vm", "example-vm"]), 0)
        get.side_effect = [node(), {"items": []}]
        self.assertEqual(module.main(["--node", "edge-worker-01",
                                      "--runner-namespace", "arc-edge",
                                      "--vm", "wrong-vm"]), 2)

    @patch.object(module, "_get")
    def test_main_pods_block(self, get):
        get.side_effect = [node(), {"items": [pod()]}]
        self.assertEqual(module.main(["--node", "edge-worker-01", "--runner-namespace", "arc-edge"]), 3)


if __name__ == "__main__":
    unittest.main()
