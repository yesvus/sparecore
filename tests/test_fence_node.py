"""Generic cordon fence: no device-specific names or implicit mutations."""
import importlib.util
import json
import pathlib
import subprocess
import unittest
from unittest.mock import Mock, patch

MODULE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "fence-node.py"
spec = importlib.util.spec_from_file_location("fence_node", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NODE = "edge-worker-01"
OTHER_NODE = "laptop-worker-02"


def node(name=NODE, cordoned=False, tainted=True):
    return {
        "metadata": {"name": name, "uid": "node-uid", "resourceVersion": "42"},
        "spec": {
            "unschedulable": cordoned,
            "taints": [{"key": "sparecore", "value": "true",
                        "effect": "NoSchedule"}] if tainted else [],
        },
    }


class FenceTests(unittest.TestCase):
    def test_node_names_are_generic_validated_dns_subdomains(self):
        for name in (NODE, OTHER_NODE, "worker.us-east.example"):
            self.assertEqual(module.validate_node_name(name), name)
        for name in ("", "-bad", "bad_", "UPPER", "--context", "x" * 64):
            with self.assertRaises(ValueError):
                module.validate_node_name(name)

    def test_requires_exact_identity_and_taint(self):
        for bad in (node(OTHER_NODE), node(tainted=False),
                    {"metadata": {"name": NODE, "uid": "node-uid"},
                     "spec": node()["spec"]},
                    dict(node(), spec={"unschedulable": "true",
                                       "taints": node()["spec"]["taints"]})):
            with self.assertRaises(ValueError):
                module.inspect(bad, NODE)

    @patch.object(module, "_node")
    @patch.object(module, "patch_cordon")
    def test_default_is_read_only_for_multiple_nodes(self, patch_cordon, get_node):
        for name in (NODE, OTHER_NODE):
            get_node.return_value = node(name)
            result, code = module.execute(name)
            self.assertEqual((result["status"], code), ("would_cordon", 0))
            self.assertFalse(result["applied"])
            get_node.assert_called_with(None, name)
        patch_cordon.assert_not_called()

    @patch.object(module, "_node")
    @patch.object(module, "patch_cordon")
    def test_apply_needs_context_and_exact_confirmation(self, patch_cordon, get_node):
        for ctx, confirmed in ((None, NODE), ("prod", OTHER_NODE),
                               ("", NODE), ("prod", None)):
            result, code = module.execute(NODE, ctx, True, confirmed)
            self.assertEqual((result["status"], code), ("blocked_confirmation", 3))
        get_node.assert_not_called()
        patch_cordon.assert_not_called()

    @patch.object(module, "_node")
    @patch.object(module, "patch_cordon")
    def test_cordoned_is_idempotent(self, patch_cordon, get_node):
        get_node.return_value = node(cordoned=True)
        result, code = module.execute(NODE, "scoped", True, NODE)
        self.assertEqual((result["status"], code), ("already_cordoned", 0))
        patch_cordon.assert_not_called()

    @patch.object(module, "scoped_authority", return_value=False)
    @patch.object(module, "_node", return_value=node())
    @patch.object(module, "patch_cordon")
    def test_broad_permissions_block(self, patch_cordon, get_node, authority):
        result, code = module.execute(NODE, "scoped", True, NODE)
        self.assertEqual((result["status"], code), ("blocked_rbac_scope", 3))
        patch_cordon.assert_not_called()

    @patch.object(module, "_can_i")
    def test_effective_permissions_are_node_specific(self, can_i):
        can_i.side_effect = [True, True, False]
        self.assertTrue(module.scoped_authority("ctx", OTHER_NODE))
        self.assertEqual(can_i.call_args_list[1].args,
                         ("ctx", "patch", "nodes/" + OTHER_NODE))
        for decisions in ([False], [True, False], [True, True, True]):
            can_i.side_effect = decisions
            self.assertFalse(module.scoped_authority("ctx", NODE))

    @patch.object(module, "_run")
    def test_json_patch_preconditions_and_exact_target(self, run):
        module.patch_cordon("ctx", OTHER_NODE, module.inspect(
            node(OTHER_NODE), OTHER_NODE))
        ctx, args = run.call_args.args
        self.assertEqual(ctx, "ctx")
        self.assertEqual(args[:3], ["patch", "node", OTHER_NODE])
        operations = json.loads(args[args.index("-p") + 1])
        self.assertEqual(operations[0]["value"], "node-uid")
        self.assertEqual(operations[1]["value"], "42")
        self.assertEqual(operations[2],
                         {"op": "add", "path": "/spec/unschedulable", "value": True})

    @patch.object(module, "_node")
    @patch.object(module, "scoped_authority", return_value=True)
    @patch.object(module, "patch_cordon")
    def test_success_requires_verification(self, patch_cordon, authority, get_node):
        for name in (NODE, OTHER_NODE):
            get_node.side_effect = [node(name), node(name, cordoned=True)]
            result, code = module.execute(name, "ctx", True, name)
            self.assertEqual((result["status"], code), ("cordoned_verified", 0))
            self.assertTrue(result["applied"])
            patch_cordon.assert_called_with("ctx", name, module.inspect(
                node(name), name))

    @patch.object(module, "_node")
    @patch.object(module, "scoped_authority", return_value=True)
    @patch.object(module, "patch_cordon")
    def test_unknown_post_patch_never_claims_success(self, patch_cordon, auth, get_node):
        get_node.side_effect = [node(), RuntimeError("api down")]
        result, code = module.execute(NODE, "ctx", True, NODE)
        self.assertEqual((result["status"], code), ("verification_unknown", 2))
        self.assertEqual(result["applied"], "unknown")

    @patch.object(module, "_node")
    @patch.object(module, "scoped_authority", return_value=True)
    @patch.object(module, "patch_cordon")
    def test_replaced_or_uncordoned_node_blocks(self, patch_cordon, auth, get_node):
        for new in (node(), dict(node(cordoned=True),
                                 metadata={"name": NODE, "uid": "different",
                                           "resourceVersion": "43"})):
            get_node.side_effect = [node(), new]
            result, code = module.execute(NODE, "ctx", True, NODE)
            self.assertEqual((result["status"], code), ("verification_failed", 2))

    @patch.object(module.subprocess, "run")
    def test_no_shell_or_interactive_stdin(self, run):
        run.return_value = Mock(stdout=json.dumps(node()), returncode=0)
        module._node("ctx", OTHER_NODE)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:3], ["kubectl", "--context", "ctx"])
        self.assertEqual(cmd[3:6], ["get", "node", OTHER_NODE])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    @patch.object(module, "_node", side_effect=TimeoutError)
    def test_api_failure_fails_closed(self, get_node):
        self.assertEqual(module.main(["--node", NODE]), 2)


if __name__ == "__main__":
    unittest.main()
