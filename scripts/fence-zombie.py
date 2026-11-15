#!/usr/bin/env python3
"""Explicitly gated, node-specific admission fence for a trusted cluster host.

This is NOT an automatic Mac actuator. Do not copy a cluster kubeconfig to
the laptop. The only supported mutation is a JSON Patch setting
spec.unschedulable=true on the named zombie Node.
"""
import argparse
import json
import subprocess
import sys

NODE = "zombie"
TAINT = {"key": "sparecore", "value": "true", "effect": "NoSchedule"}


def _command(context, args):
    cmd = ["kubectl"]
    if context:
        cmd.extend(["--context", context])
    return cmd + list(args)


def _run(context, args):
    result = subprocess.run(
        _command(context, args), stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode:
        raise RuntimeError("Kubernetes command failed; outcome must be inspected")
    return result.stdout.strip()


def _can_i(context, *args):
    result = subprocess.run(
        _command(context, ["auth", "can-i"] + list(args)),
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=10, check=False,
    )
    answer = result.stdout.strip()
    if (answer, result.returncode) not in (("yes", 0), ("no", 1), ("no", 0)):
        raise RuntimeError("Cannot verify effective Kubernetes permissions")
    return answer == "yes"


def _node(context):
    return json.loads(_run(context, ["get", "node", NODE, "-o", "json"]))


def inspect(node):
    """Require correct identity, version and the existing quarantine taint."""
    if not isinstance(node, dict):
        raise ValueError("Incomplete Node")
    metadata = node.get("metadata")
    spec = node.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise ValueError("Missing Node metadata/spec")
    if metadata.get("name") != NODE:
        raise ValueError("Unexpected Node identity")
    uid = metadata.get("uid")
    version = metadata.get("resourceVersion")
    if not isinstance(uid, str) or not uid or not isinstance(version, str) or not version:
        raise ValueError("Missing Node identity version")
    taints = spec.get("taints")
    if not isinstance(taints, list) or TAINT not in taints:
        raise ValueError("Missing SpareCore admission taint")
    # Refuse malformed flags rather than treating unknown as already fenced.
    cordoned = spec.get("unschedulable", False)
    if type(cordoned) is not bool:
        raise ValueError("Invalid Node scheduling state")
    return {"uid": uid, "version": version, "cordoned": cordoned}


def scoped_authority(context):
    """Block broad admin credentials; this is defense in depth, not RBAC."""
    if not _can_i(context, "get", "nodes/" + NODE):
        return False
    if not _can_i(context, "patch", "nodes/" + NODE):
        return False
    if _can_i(context, "patch", "nodes"):
        return False
    if _can_i(context, "patch", "nodes/gurbet"):
        return False
    return True


def patch_cordon(context, facts):
    """Race-aware mutation: reject if Node UID or resourceVersion changed."""
    operations = [
        {"op": "test", "path": "/metadata/uid", "value": facts["uid"]},
        {"op": "test", "path": "/metadata/resourceVersion", "value": facts["version"]},
        {"op": "add", "path": "/spec/unschedulable", "value": True},
    ]
    _run(context, [
        "patch", "node", NODE, "--type=json",
        "-p", json.dumps(operations, separators=(",", ":")), "-o", "json",
    ])


def execute(context=None, apply=False, confirmation=None):
    """Never write on a default read-only invocation or without three gates."""
    if apply and (not context or confirmation != NODE):
        return {"node": NODE, "status": "blocked_confirmation",
                "applied": False}, 3

    # Read the specific node even for dry runs; fail closed on stale/unknown.
    before = inspect(_node(context))
    if before["cordoned"]:
        return {"node": NODE, "status": "already_cordoned",
                "applied": False}, 0
    if not apply:
        return {"node": NODE, "status": "would_cordon",
                "applied": False}, 0
    if not scoped_authority(context):
        return {"node": NODE, "status": "blocked_rbac_scope",
                "applied": False}, 3

    patch_cordon(context, before)
    # The patch may have succeeded even if this subsequent GET fails.
    # Never report an unverified outcome as clean success.
    try:
        after = inspect(_node(context))
    except (ValueError, RuntimeError, subprocess.SubprocessError,
            OSError, json.JSONDecodeError):
        return {"node": NODE, "status": "verification_unknown",
                "applied": "unknown"}, 2
    if after["uid"] != before["uid"] or not after["cordoned"]:
        return {"node": NODE, "status": "verification_failed",
                "applied": "unknown"}, 2
    return {"node": NODE, "status": "cordoned_verified",
            "applied": True}, 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Manual, fail-closed zombie admission fence (trusted host only)")
    parser.add_argument("--context", help="Explicit kubectl context; required to apply")
    parser.add_argument("--apply", action="store_true",
                        help="Mutate only spec.unschedulable on zombie")
    parser.add_argument("--confirm-node", help="Must equal zombie for --apply")
    args = parser.parse_args(argv)
    try:
        result, code = execute(
            context=args.context, apply=args.apply,
            confirmation=args.confirm_node)
    except (ValueError, RuntimeError, subprocess.SubprocessError,
            OSError, json.JSONDecodeError) as exc:
        result, code = ({"node": NODE, "status": "unknown_fail_closed",
                         "reason": type(exc).__name__, "applied": False}, 2)
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
