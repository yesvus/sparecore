"""The optional admission fence MUST remain manual and node-specific."""
import importlib.util
import json
import pathlib
import subprocess
import unittest
from unittest.mock import Mock, patch

MODULE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "fence-zombie.py"
spec = importlib.util.spec_from_file_location("fence_zombie", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def node(cordoned=False, tainted=True):
    return {
        "metadata": {"name": "zombie", "uid": "node-uid", "resourceVersion": "42"},
        "spec": {
            "unschedulable": cordoned,
            "taints": [dict(module.TAINT)] if tainted else [],
        },
    }


class FenceTests(unittest.TestCase):
    def test_requires_correct_node_identity_and_taint(self):
        for change in (
            {"metadata": {"name": "gurbet", "uid": "node-uid", "resourceVersion": "42"}},
            {"metadata": {"name": "zombie", "uid": "node-uid"}},
            {"spec": {"unschedulable": False, "taints": []}},
            {"spec": {"unschedulable": "true", "taints": [module.TAINT]}},
        ):
            bad = node()
            bad.update(change)
            with self.assertRaises(ValueError):
                module.inspect(bad)

    @patch.object(module, "_node")
    @patch.object(module, "patch_cordon")
    def test_default_is_read_only(self, patch_cordon, get_node):
        get_node.return_value = node()
        result, code = module.execute()
        self.assertEqual((result["status"], code), ("would_cordon", 0))
        self.assertFalse(result["applied"])
        patch_cordon.assert_not_called()

    @patch.object(module, "_node")
    @patch.object(module, "patch_cordon")
    def test_apply_requires_context_and_exact_confirmation(self, patch_cordon, get_node):
        for ctx, confirmed in ((None, "zombie"), ("prod", "gurbet"), ("", "zombie"),
                               ("prod", None)):
            status, code = module.execute(ctx, True, confirmed)
            self.assertEqual((status["status"], code), ("blocked_confirmation", 3))
        get_node.assert_not_called()
        patch_cordon.assert_not_called()

    @patch.object(module, "_node")
    @patch.object(module, "patch_cordon")
    def test_already_cordoned_is_idempotent(self, patch_cordon, get_node):
        get_node.return_value = node(cordoned=True)
        result, code = module.execute("prod", True, "zombie")
        self.assertEqual((result["status"], code), ("already_cordoned", 0))
        patch_cordon.assert_not_called()

    @patch.object(module, "scoped_authority", return_value=False)
    @patch.object(module, "_node", return_value=node())
    @patch.object(module, "patch_cordon")
    def test_broad_rbac_blocks(self, patch_cordon, get_node, authority):
        result, code = module.execute("prod", True, "zombie")
        self.assertEqual((result["status"], code), ("blocked_rbac_scope", 3))
        patch_cordon.assert_not_called()

    @patch.object(module, "_can_i")
    def test_rbac_must_approve_specific_node_and_deny_broad_patch(self, can_i):
        can_i.side_effect = [True, True, False, False]
        self.assertTrue(module.scoped_authority("prod"))
        self.assertEqual(can_i.call_args_list[1].args,
                         ("prod", "patch", "nodes/zombie"))
        for responses in ([False], [True, False], [True, True, True],
                          [True, True, False, True]):
            can_i.side_effect = responses
            self.assertFalse(module.scoped_authority("prod"))

    @patch.object(module, "_run")
    def test_json_patch_has_identity_and_version_preconditions(self, run):
        module.patch_cordon("prod", module.inspect(node()))
        ctx, args = run.call_args.args
        self.assertEqual(ctx, "prod")
        self.assertEqual(args[:3], ["patch", "node", "zombie"])
        operations = json.loads(args[args.index("-p") + 1])
        self.assertEqual(operations[0]["value"], "node-uid")
        self.assertEqual(operations[1]["value"], "42")
        self.assertEqual(operations[2],
                         {"op": "add", "path": "/spec/unschedulable", "value": True})

    @patch.object(module, "_node")
    @patch.object(module, "scoped_authority", return_value=True)
    @patch.object(module, "patch_cordon")
    def test_confirmed_success_requires_second_read(self, patch_cordon, authority,
                                                     get_node):
        get_node.side_effect = [node(), node(cordoned=True)]
        result, code = module.execute("prod", True, "zombie")
        self.assertEqual((result["status"], code), ("cordoned_verified", 0))
        self.assertTrue(result["applied"])
        self.assertEqual(get_node.call_count, 2)
        patch_cordon.assert_called_once()

    @patch.object(module, "_node")
    @patch.object(module, "scoped_authority", return_value=True)
    @patch.object(module, "patch_cordon")
    def test_post_patch_unknown_is_not_false_success(self, patch_cordon,
                                                      authority, get_node):
        get_node.side_effect = [node(), RuntimeError("api gone")]
        result, code = module.execute("prod", True, "zombie")
        self.assertEqual((result["status"], code), ("verification_unknown", 2))
        self.assertEqual(result["applied"], "unknown")

    @patch.object(module, "_node")
    @patch.object(module, "scoped_authority", return_value=True)
    @patch.object(module, "patch_cordon")
    def test_post_patch_uncordoned_or_replaced_blocks(self, patch_cordon,
                                                      authority, get_node):
        for second in (node(), dict(node(cordoned=True),
                                   metadata={"name": "zombie", "uid": "new-uid",
                                             "resourceVersion": "43"})):
            get_node.side_effect = [node(), second]
            result, code = module.execute("prod", True, "zombie")
            self.assertEqual((result["status"], code), ("verification_failed", 2))

    @patch.object(module.subprocess, "run")
    def test_kubectl_never_uses_shell_or_interactive_stdin(self, run):
        run.return_value = Mock(stdout=json.dumps(node()), returncode=0)
        module._node("prod")
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:3], ["kubectl", "--context", "prod"])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertFalse(run.call_args.kwargs["check"])

    @patch.object(module, "_node", side_effect=TimeoutError)
    def test_unreachable_cluster_fails_closed(self, get_node):
        # TimeoutExpired is a SubprocessError; TimeoutError is an OSError.
        self.assertEqual(module.main([]), 2)


if __name__ == "__main__":
    unittest.main()
