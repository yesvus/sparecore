#!/usr/bin/env python3
"""Read-only zombie Kubernetes drain preflight. Run on a trusted admin host.

Never run this with kubeconfig copied to a personal Mac. This intentionally
does not implement eviction, cordon, drain, VM control or token management.
"""
import json
import subprocess
import sys


NODE = "zombie"
RUNNER_NAMESPACE = "arc-sparecore"


def _get(args):
    result = subprocess.run(
        ["kubectl", "get"] + list(args) + ["-o", "json"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=10,
        check=True,
    )
    return json.loads(result.stdout)


def inspect(node, pods):
    """Pure check: 0 pods only means inventory is clear, not safe to stop."""
    if not isinstance(node, dict) or not isinstance(pods, dict):
        raise ValueError("Invalid API result")
    metadata = node.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("name") != NODE:
        raise ValueError("Wrong Kubernetes node identity")
    spec = node.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("Node spec unavailable")
    if not isinstance(pods.get("items"), list):
        raise ValueError("Pod inventory unavailable")

    cordoned = spec.get("unschedulable") is True
    taints = spec.get("taints", [])
    if not isinstance(taints, list):
        raise ValueError("Unexpected Node taints")
    tainted = any(
        isinstance(t, dict) and t.get("key") == "sparecore"
        and t.get("value") == "true" and t.get("effect") == "NoSchedule"
        for t in taints
    )
    foreign = []
    runner = []
    for p in pods["items"]:
        if not isinstance(p, dict):
            raise ValueError("Invalid Pod entry")
        meta = p.get("metadata", {})
        p_spec = p.get("spec", {})
        if not isinstance(meta, dict) or not isinstance(p_spec, dict):
            raise ValueError("Incomplete Pod entry")
        if not meta.get("name") or not meta.get("namespace"):
            raise ValueError("Pod identity incomplete")
        if p_spec.get("nodeName") != NODE:
            raise ValueError("Pod inventory was not filtered to zombie")
        status = p.get("status")
        if status is not None and not isinstance(status, dict):
            raise ValueError("Invalid Pod status")
        entry = {"namespace": meta["namespace"], "name": meta["name"],
                 "phase": (status or {}).get("phase", "Unknown"),
                 "terminating": bool(meta.get("deletionTimestamp"))}
        if entry["namespace"] == RUNNER_NAMESPACE:
            runner.append(entry)
        else:
            foreign.append(entry)
    if not cordoned or not tainted:
        status = "block_admission_not_closed"
    elif foreign:
        status = "block_foreign_workloads"
    elif runner:
        status = "review_runner_evictions"
    else:
        status = "no_pods_observed"

    return {
        "node": NODE,
        "status": status,
        "node_cordoned": cordoned,
        "taint_present": tainted,
        "foreign_pods": foreign,
        "runner_pods": runner,
        "applied": False,
        "disclaimer": (
            "Read-only inventory snapshot, not authorization to shut down the VM. "
            "No drain/eviction/PDB checks were executed."
        ),
    }


def main():
    try:
        node = _get(["node", NODE])
        pods = _get(["pods", "--all-namespaces", "--field-selector",
                     "spec.nodeName=" + NODE])
        result = inspect(node, pods)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError,
            ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"node": NODE, "status": "unknown_fail_closed",
                          "applied": False,
                          "reason": type(exc).__name__}), flush=True)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "no_pods_observed" else 3


if __name__ == "__main__":
    sys.exit(main())
