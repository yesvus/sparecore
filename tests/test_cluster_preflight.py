"""Mocked tests for trusted-host read-only drain inspection."""
import importlib.util
import json
import pathlib
import subprocess
import unittest
from unittest.mock import Mock, patch

MODULE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check-zombie-drain.py"
spec = importlib.util.spec_from_file_location("check_zombie_drain", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def node(cordoned=True, tainted=True):
    return {"metadata": {"name": "zombie"}, "spec": {
        "unschedulable": cordoned,
        "taints": [{"key": "sparecore", "value": "true",
                    "effect": "NoSchedule"}] if tainted else [],
    }}


def pod(name="runner", ns="arc-sparecore", node_name="zombie"):
    return {"metadata": {"name": name, "namespace": ns},
            "spec": {"nodeName": node_name}, "status": {"phase": "Running"}}


class DrainSafetyChecks(unittest.TestCase):
    def test_no_pods_requires_cordon_and_taint(self):
        self.assertEqual(module.inspect(node(), {"items": []})["status"],
                         "no_pods_observed")

    def test_uncordoned_blocks(self):
        self.assertEqual(module.inspect(node(cordoned=False), {"items": []})["status"],
                         "block_admission_not_closed")

    def test_missing_taint_blocks(self):
        self.assertEqual(module.inspect(node(tainted=False), {"items": []})["status"],
                         "block_admission_not_closed")

    def test_foreign_namespace_blocks_even_daemonsets(self):
        result = module.inspect(node(), {"items": [
            pod(name="cni", ns="kube-system"), pod()]})
        self.assertEqual(result["status"], "block_foreign_workloads")
        self.assertEqual(result["foreign_pods"][0]["name"], "cni")

    def test_runner_pod_requires_review_not_shutdown(self):
        self.assertEqual(module.inspect(node(), {"items": [pod()]})["status"],
                         "review_runner_evictions")

    def test_wrong_node_aborts(self):
        with self.assertRaises(ValueError):
            module.inspect(node(), {"items": [pod(node_name="gurbet")]})

    def test_bad_inventory_aborts(self):
        with self.assertRaises(ValueError):
            module.inspect(node(), {"items": None})

    def test_null_pod_status_rejected(self):
        broken = pod()
        broken["status"] = "unexpected"
        with self.assertRaises(ValueError):
            module.inspect(node(), {"items": [broken]})

    def test_missing_node_metadata_rejected(self):
        with self.assertRaises(ValueError):
            module.inspect({"metadata": None, "spec": node()["spec"]}, {"items": []})

    def test_none_of_this_ever_claims_application(self):
        for pods in ([], [pod()], [pod(ns="default")]):
            self.assertFalse(module.inspect(node(), {"items": pods})["applied"])

    @patch.object(module.subprocess, "run")
    def test_get_invokes_only_read_only_kubectl(self, run):
        run.return_value = Mock(stdout=json.dumps({"items": []}))
        module._get(["pods", "--all-namespaces", "--field-selector",
                     "spec.nodeName=zombie"])
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["kubectl", "get"])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    @patch.object(module, "_get", side_effect=TimeoutError())
    def test_no_api_fails_closed(self, _):
        self.assertEqual(module.main(), 2)

    @patch.object(module, "_get")
    def test_main_no_pods(self, get):
        get.side_effect = [node(), {"items": []}]
        self.assertEqual(module.main(), 0)

    @patch.object(module, "_get")
    def test_main_pods_block(self, get):
        get.side_effect = [node(), {"items": [pod()]}]
        self.assertEqual(module.main(), 3)


if __name__ == "__main__":
    unittest.main()
