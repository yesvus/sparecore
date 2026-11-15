#!/usr/bin/env python3
"""Manually gated, node-specific Kubernetes admission fence.

Runs on a trusted cluster-side host, never on a personal-device agent.
The *only* mutation is setting spec.unschedulable=true on an explicitly
selected Kubernetes Node. It cannot uncordon, evict, drain, or stop a VM.
"""
import argparse
import json
import re
import subprocess
import sys

DEFAULT_TAINT_KEY = "sparecore"
DEFAULT_TAINT_VALUE = "true"


def validate_node_name(name):
    # Kubernetes node names are DNS subdomains. Never accept kubectl flags.
    if not isinstance(name, str) or not 1 <= len(name) <= 253:
        raise ValueError("Invalid Kubernetes node name")
    labels = name.split(".")
    if any(len(label) > 63 or not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) for label in labels):
        raise ValueError("Invalid Kubernetes node name")
    return name


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


def _can_i(context, verb, resource):
    result = subprocess.run(
        _command(context, ["auth", "can-i", verb, resource]),
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=10, check=False,
    )
    answer = result.stdout.strip()
    if (answer, result.returncode) not in (("yes", 0), ("no", 1), ("no", 0)):
        raise RuntimeError("Cannot verify effective Kubernetes permissions")
    return answer == "yes"


def _node(context, name):
    return json.loads(_run(context, ["get", "node", name, "-o", "json"]))


def inspect(node, name, taint_key=DEFAULT_TAINT_KEY,
            taint_value=DEFAULT_TAINT_VALUE):
    """Validate exact Node identity and the explicit quarantine taint."""
    validate_node_name(name)
    if not isinstance(node, dict):
        raise ValueError("Incomplete Node")
    metadata, spec = node.get("metadata"), node.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise ValueError("Missing Node metadata/spec")
    if metadata.get("name") != name:
        raise ValueError("Unexpected Node identity")
    uid, version = metadata.get("uid"), metadata.get("resourceVersion")
    if not isinstance(uid, str) or not uid or not isinstance(version, str) or not version:
        raise ValueError("Missing Node UID/resourceVersion")
    taints = spec.get("taints")
    if not isinstance(taints, list) or not any(
        isinstance(t, dict) and t.get("key") == taint_key
        and t.get("value") == taint_value and t.get("effect") == "NoSchedule"
        for t in taints
    ):
        raise ValueError("Required NoSchedule quarantine taint missing")
    cordoned = spec.get("unschedulable", False)
    if type(cordoned) is not bool:
        raise ValueError("Invalid Node scheduling state")
    return {"uid": uid, "version": version, "cordoned": cordoned}


def scoped_authority(context, name):
    """Reject obvious broad patch permissions (not a full RBAC proof)."""
    if not _can_i(context, "get", "nodes/" + name):
        return False
    if not _can_i(context, "patch", "nodes/" + name):
        return False
    if _can_i(context, "patch", "nodes"):
        return False
    return True


def patch_cordon(context, name, facts):
    """Atomic UID/version preconditions prevent patching a replaced Node."""
    operations = [
        {"op": "test", "path": "/metadata/uid", "value": facts["uid"]},
        {"op": "test", "path": "/metadata/resourceVersion", "value": facts["version"]},
        {"op": "add", "path": "/spec/unschedulable", "value": True},
    ]
    _run(context, [
        "patch", "node", name, "--type=json",
        "-p", json.dumps(operations, separators=(",", ":")), "-o", "json",
    ])


def execute(name, context=None, apply=False, confirmation=None,
            taint_key=DEFAULT_TAINT_KEY, taint_value=DEFAULT_TAINT_VALUE):
    """Require explicit node, context, opt-in and narrowly scoped authority."""
    validate_node_name(name)
    if apply and (not context or confirmation != name):
        return {"node": name, "status": "blocked_confirmation",
                "applied": False}, 3
    before = inspect(_node(context, name), name, taint_key, taint_value)
    if before["cordoned"]:
        return {"node": name, "status": "already_cordoned",
                "applied": False}, 0
    if not apply:
        return {"node": name, "status": "would_cordon",
                "applied": False}, 0
    if not scoped_authority(context, name):
        return {"node": name, "status": "blocked_rbac_scope",
                "applied": False}, 3

    patch_cordon(context, name, before)
    # GET failure after patch means success is unknown, not 'applied=false'.
    try:
        after = inspect(_node(context, name), name, taint_key, taint_value)
    except (ValueError, RuntimeError, subprocess.SubprocessError,
            OSError, json.JSONDecodeError):
        return {"node": name, "status": "verification_unknown",
                "applied": "unknown"}, 2
    if after["uid"] != before["uid"] or not after["cordoned"]:
        return {"node": name, "status": "verification_failed",
                "applied": "unknown"}, 2
    return {"node": name, "status": "cordoned_verified",
            "applied": True}, 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Opt-in, cordon-only Kubernetes fence (trusted host only)")
    parser.add_argument("--node", required=True, help="Exact Kubernetes node name")
    parser.add_argument("--context", help="Explicit kubectl context; required to apply")
    parser.add_argument("--taint-key", default=DEFAULT_TAINT_KEY,
                        help="Required quarantine NoSchedule taint key")
    parser.add_argument("--taint-value", default=DEFAULT_TAINT_VALUE,
                        help="Required quarantine NoSchedule taint value")
    parser.add_argument("--apply", action="store_true",
                        help="Only set spec.unschedulable=true on --node")
    parser.add_argument("--confirm-node", help="Must exactly match --node")
    args = parser.parse_args(argv)
    try:
        result, code = execute(
            args.node, context=args.context, apply=args.apply,
            confirmation=args.confirm_node, taint_key=args.taint_key,
            taint_value=args.taint_value)
    except (ValueError, RuntimeError, subprocess.SubprocessError,
            OSError, json.JSONDecodeError) as exc:
        result, code = ({"node": args.node, "status": "unknown_fail_closed",
                         "reason": type(exc).__name__, "applied": False}, 2)
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
