#!/usr/bin/env python3
"""One-shot, owner-confirmed native ARC Pod eviction on a trusted cluster host.

This does NOT drive a VM, automate a scheduler or provide shutdown permission.
Uses two distinct pre-existing kubectl contexts: inventory read and namespaced
pods/eviction authority. Never install either kubeconfig on a personal Mac.
"""
import argparse
import json
import platform
import re
import subprocess
import sys

TAINT_KEY = "sparecore"
TAINT_VALUE = "true"
OWNER_KIND = "EphemeralRunner"


def valid_name(name, namespace=False):
    if not isinstance(name, str) or not name or len(name) > (63 if namespace else 253):
        raise ValueError("Invalid Kubernetes identity")
    bits = name.split(".")
    if namespace and len(bits) != 1:
        raise ValueError("Namespace must be a DNS label")
    if any(len(bit) > 63 or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", bit) for bit in bits):
        raise ValueError("Invalid Kubernetes identity")
    return name


def _run(context, args, payload=None):
    if not isinstance(context, str) or not context.strip() or context.startswith("-"):
        raise ValueError("Explicit Kubernetes context required")
    cmd = ["kubectl", "--context", context] + list(args)
    kwargs = {"capture_output": True, "text": True, "timeout": 10,
              "check": False}
    if payload is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = payload
    p = subprocess.run(cmd, **kwargs)
    if p.returncode != 0:
        raise RuntimeError("Kubernetes command failed or was rejected")
    return p.stdout


def _get(context, args):
    return json.loads(_run(context, ["get"] + list(args) + ["-o", "json"]))


def inspect(node, pods, node_name, namespace, allow_running=False):
    """Pure fail-closed preflight. Zero Pods is NOT a shutdown authorization."""
    valid_name(node_name)
    valid_name(namespace, namespace=True)
    if not isinstance(node, dict) or not isinstance(pods, dict):
        raise ValueError("Untrusted inventory")
    meta, spec = node.get("metadata"), node.get("spec")
    if not isinstance(meta, dict) or meta.get("name") != node_name:
        raise ValueError("Incorrect Node identity")
    if not isinstance(meta.get("uid"), str) or not meta["uid"]:
        raise ValueError("Node UID unavailable")
    if not isinstance(spec, dict) or spec.get("unschedulable") is not True:
        return {"status": "blocked_node_not_cordoned", "candidate": None}
    taints = spec.get("taints")
    if not isinstance(taints, list) or not any(
            isinstance(t, dict) and t.get("key") == TAINT_KEY
            and t.get("value") == TAINT_VALUE and t.get("effect") == "NoSchedule"
            for t in taints):
        return {"status": "blocked_quarantine_taint", "candidate": None}

    items = pods.get("items")
    if not isinstance(items, list):
        raise ValueError("Pod inventory unavailable")
    candidates = []
    for p in items:
        if not isinstance(p, dict) or not isinstance(p.get("metadata"), dict) or not isinstance(p.get("spec"), dict):
            raise ValueError("Invalid Pod inventory entry")
        pm, ps = p["metadata"], p["spec"]
        if ps.get("nodeName") != node_name or not pm.get("name") or not pm.get("namespace"):
            raise ValueError("Mismatched Pod inventory")
        if pm["namespace"] != namespace:
            return {"status": "blocked_foreign_workload", "candidate": None}
        if pm.get("deletionTimestamp"):
            return {"status": "blocked_terminating", "candidate": None}
        owners = pm.get("ownerReferences")
        if not isinstance(owners, list) or not any(
                isinstance(o, dict) and o.get("kind") == OWNER_KIND
                and o.get("controller") is True for o in owners):
            return {"status": "blocked_untrusted_owner", "candidate": None}
        if not isinstance(pm.get("uid"), str) or not pm["uid"]:
            raise ValueError("Pod UID missing")
        phase = (p.get("status") or {}).get("phase")
        if phase not in ("Pending", "Running", "Succeeded", "Failed"):
            return {"status": "blocked_unknown_pod_phase", "candidate": None}
        if phase == "Running" and not allow_running:
            return {"status": "blocked_active_job", "candidate": None}
        candidates.append({"name": pm["name"], "namespace": namespace,
                           "uid": pm["uid"], "phase": phase})
    if len(candidates) > 1:
        return {"status": "blocked_multiple_pods", "candidate": None}
    if not candidates:
        return {"status": "no_pods_observed", "candidate": None}
    return {"status": "eviction_candidate", "candidate": candidates[0]}


def _inventory(context, node_name):
    return (
        _get(context, ["node", node_name]),
        _get(context, ["pods", "--all-namespaces", "--field-selector",
                       "spec.nodeName=" + node_name]),
    )


def _verify_namespaced_context(context, namespace):
    # This is an additional guard, NOT a full proof of RBAC scope.
    if _run(context, ["auth", "can-i", "create", "pods",
                      "--subresource=eviction", "-n", namespace]).strip() != "yes":
        return False
    for foreign in ("default", "kube-system"):
        if _run(context, ["auth", "can-i", "create", "pods",
                          "--subresource=eviction", "-n", foreign]).strip() != "no":
            return False
    return True


def execute(node_name, namespace, audit_context, eviction_context,
            apply=False, confirm_node=None, allow_running=False):
    valid_name(node_name)
    valid_name(namespace, namespace=True)
    if platform.system() != "Linux":
        return {"status": "blocked_trusted_host_only", "applied": False}, 3
    if not audit_context or not eviction_context or audit_context == eviction_context:
        return {"status": "blocked_distinct_contexts_required", "applied": False}, 3
    if apply and confirm_node != node_name:
        return {"status": "blocked_exact_confirmation", "applied": False}, 3

    n, p = _inventory(audit_context, node_name)
    before = inspect(n, p, node_name, namespace, allow_running)
    state = before["status"]
    if state == "no_pods_observed":
        return {"status": state, "applied": False, "shutdown_authorized": False}, 0
    if state != "eviction_candidate":
        return {"status": state, "applied": False}, 3
    if not apply:
        return {"status": "would_request_eviction", "applied": False,
                "candidate": before["candidate"]}, 0
    if not _verify_namespaced_context(eviction_context, namespace):
        return {"status": "blocked_eviction_rbac", "applied": False}, 3

    # Re-read immediately before the one permitted write. Any change blocks.
    fresh_n, fresh_p = _inventory(audit_context, node_name)
    fresh = inspect(fresh_n, fresh_p, node_name, namespace, allow_running)
    if fresh != before or fresh_n.get("metadata", {}).get("uid") != n.get("metadata", {}).get("uid"):
        return {"status": "blocked_inventory_changed", "applied": False}, 3
    candidate = fresh["candidate"]
    scoped = _get(eviction_context,
                  ["pod", candidate["name"], "-n", namespace])
    if (scoped.get("metadata", {}).get("uid") != candidate["uid"]
            or scoped.get("spec", {}).get("nodeName") != node_name):
        return {"status": "blocked_pod_identity_changed", "applied": False}, 3
    # Native Eviction API observes PDB and graceful termination; never delete.
    request = {
        "apiVersion": "policy/v1", "kind": "Eviction",
        "metadata": {"name": candidate["name"], "namespace": namespace},
        "deleteOptions": {"preconditions": {"uid": candidate["uid"]}},
    }
    path = "/api/v1/namespaces/{}/pods/{}/eviction".format(
        namespace, candidate["name"])
    try:
        _run(eviction_context, ["create", "--raw", path, "-f", "-"],
             json.dumps(request))
    except (OSError, RuntimeError, subprocess.SubprocessError):
        # PDB HTTP 429, API timeout and transport disconnect all fail closed.
        # Even on timeout the API could have accepted the request.
        return {"status": "eviction_blocked_or_unknown", "applied": "unknown",
                "shutdown_authorized": False}, 2
    return {"status": "eviction_requested_not_completed", "applied": True,
            "shutdown_authorized": False, "candidate": candidate}, 3


def main(argv=None):
    ap = argparse.ArgumentParser(description="One-shot PDB-aware native runner eviction; trusted cluster host only")
    ap.add_argument("--node", required=True)
    ap.add_argument("--runner-namespace", required=True)
    ap.add_argument("--audit-context", required=True)
    ap.add_argument("--eviction-context", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-node")
    ap.add_argument("--allow-running", action="store_true",
                    help="Explicitly allow interrupting a running ephemeral CI job")
    args = ap.parse_args(argv)
    try:
        result, code = execute(args.node, args.runner_namespace,
                               args.audit_context, args.eviction_context,
                               args.apply, args.confirm_node, args.allow_running)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError,
            subprocess.SubprocessError, json.JSONDecodeError) as exc:
        result, code = ({"status": "unknown_fail_closed",
                         "reason": type(exc).__name__,
                         "applied": False, "shutdown_authorized": False}, 2)
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
