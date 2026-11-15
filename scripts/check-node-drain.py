#!/usr/bin/env python3
"""Read-only Kubernetes drain preflight. Run on a trusted admin host.

Never run this with kubeconfig copied to a personal Mac. This intentionally
does not implement eviction, cordon, drain, VM control or token management.
"""
import argparse
import json
import re
import subprocess
import sys


def validate_name(value, kind="node"):
    if not isinstance(value, str) or not 1 <= len(value) <= 253:
        raise ValueError("Invalid " + kind)
    parts = value.split(".")
    if (kind == "namespace" and len(parts) != 1) or any(
            len(part) > 63 or not re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", part) for part in parts):
        raise ValueError("Invalid " + kind)
    return value


def _get(args, context=None):
    command = ["kubectl"]
    if context:
        command += ["--context", context]
    result = subprocess.run(
        command + ["get"] + list(args) + ["-o", "json"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=10,
        check=True,
    )
    return json.loads(result.stdout)


def inspect(node, pods, node_name, runner_namespace,
            taint_key="sparecore", taint_value="true"):
    validate_name(node_name)
    validate_name(runner_namespace, "namespace")
    """Pure check: 0 pods only means inventory is clear, not safe to stop."""
    if not isinstance(node, dict) or not isinstance(pods, dict):
        raise ValueError("Invalid API result")
    metadata = node.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("name") != node_name:
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
        isinstance(t, dict) and t.get("key") == taint_key
        and t.get("value") == taint_value and t.get("effect") == "NoSchedule"
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
        if p_spec.get("nodeName") != node_name:
            raise ValueError("Pod inventory was not filtered to selected Node")
        status = p.get("status")
        if status is not None and not isinstance(status, dict):
            raise ValueError("Invalid Pod status")
        entry = {"namespace": meta["namespace"], "name": meta["name"],
                 "phase": (status or {}).get("phase", "Unknown"),
                 "terminating": bool(meta.get("deletionTimestamp"))}
        if entry["namespace"] == runner_namespace:
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
        "node": node_name,
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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Kubernetes drain preflight")
    parser.add_argument("--node", required=True, help="Exact Kubernetes node")
    parser.add_argument("--runner-namespace", required=True,
                        help="Only trusted runner namespace")
    parser.add_argument("--context", help="Read-only kubectl context")
    parser.add_argument("--taint-key", default="sparecore")
    parser.add_argument("--taint-value", default="true")
    args = parser.parse_args(argv)
    try:
        node_name = validate_name(args.node)
        namespace = validate_name(args.runner_namespace, "namespace")
        node = _get(["node", node_name], args.context)
        pods = _get(["pods", "--all-namespaces", "--field-selector",
                     "spec.nodeName=" + node_name], args.context)
        result = inspect(node, pods, node_name, namespace,
                         args.taint_key, args.taint_value)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError,
            ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"node": args.node, "status": "unknown_fail_closed",
                          "applied": False, "reason": type(exc).__name__}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "no_pods_observed" else 3


if __name__ == "__main__":
    sys.exit(main())
