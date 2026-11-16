"""Manual opt-in, single-step Lima VM actuator (macOS only).

Does not cordon, uncordon, drain, start kubelet, or operate on Kubernetes.
Its cluster gate is a fresh, read-only SSH check executed on a trusted
cluster-side host. It does not load or copy a kubeconfig onto macOS.
"""
import argparse
import json
import platform
import re
import subprocess
import sys

from .worker_status import _guest_summary, _host_summary


def _validate(value, kind):
    if not isinstance(value, str) or not value or len(value) > 253:
        raise ValueError("Invalid " + kind)
    if kind == "ssh_alias":
        pattern = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
    elif kind == "vm":
        pattern = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
    elif kind == "namespace":
        pattern = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    else:
        pattern = r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?"
    if not re.fullmatch(pattern, value):
        raise ValueError("Invalid " + kind)
    if kind == "node" and any(
            len(label) > 63 or not re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
            for label in value.split(".")):
        raise ValueError("Invalid Kubernetes Node label")
    return value


def _command(argv, timeout):
    # Fixed argv, no shell, no caller stdin or interactive credential prompt.
    return subprocess.run(argv, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=timeout, check=False)


def _probe_node(ssh_alias, vm, node, namespace):
    """Run an independent, on-demand cluster-side READ-ONLY check."""
    cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "NumberOfPasswordPrompts=0",
        "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=4",
        "-o", "ConnectionAttempts=1", ssh_alias,
        "sparecore-readonly-node-check",
        "--node", node, "--runner-namespace", namespace, "--vm", vm,
    ]
    result = _command(cmd, timeout=12)
    if result.returncode:
        raise RuntimeError("Cannot verify cluster state")
    try:
        report = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RuntimeError("Malformed cluster preflight") from None
    if not isinstance(report, dict) or report.get("node") != node:
        raise RuntimeError("Wrong cluster Node")
    # A human confirmation of two independent strings is not proof that
    # this Lima guest corresponds to the target Kubernetes Node. The
    # cluster-side helper verifies the operator-managed native Node annotation
    # and includes the stable Kubernetes Node UID in its evidence.
    if (report.get("bound_vm") != vm
            or report.get("vm_binding_verified") is not True
            or not isinstance(report.get("node_uid"), str)
            or not report.get("node_uid")):
        raise RuntimeError("VM/Node binding not verified by trusted cluster")
    if (report.get("status") != "no_pods_observed"
            or report.get("node_cordoned") is not True
            or report.get("taint_present") is not True
            or report.get("foreign_pods") != []
            or report.get("runner_pods") != []
            or report.get("applied") is not False):
        raise RuntimeError("Node is not confirmed cordoned, quarantined and empty")
    return report


def execute(action, vm, node, namespace, ssh_alias, apply=False,
            confirm_vm=None, confirm_node=None):
    """At most one requested VM action; failure always prevents unverified stop."""
    for kind, value in (("vm", vm), ("node", node),
                        ("namespace", namespace), ("ssh_alias", ssh_alias)):
        _validate(value, kind)
    if platform.system() != "Darwin":
        return {"status": "blocked_non_macos", "applied": False}, 3
    if action not in ("start", "stop"):
        raise ValueError("Unsupported action")
    if apply and (confirm_vm != vm or confirm_node != node):
        return {"status": "blocked_confirmation", "applied": False}, 3

    guest = _guest_summary(vm)
    if guest.get("isolation_verified") is not True:
        return {"status": "blocked_unverified_vm", "applied": False}, 3
    before = guest.get("vm")
    if before not in ("running", "stopped"):
        return {"status": "blocked_vm_unknown", "applied": False}, 3
    already = (action == "start" and before == "running") or (
        action == "stop" and before == "stopped")

    if action == "start" and not already:
        host = _host_summary()
        age = host.get("status_age_seconds")
        # The 2-minute stability gate is already enforced by Hammerspoon;
        # never infer eligibility from AC status alone or a stale snapshot.
        if (host.get("tier") != "boost" or host.get("on_ac") is not True
                or host.get("memory_pressure") != "1"
                or not isinstance(age, (int, float)) or not 0 <= age <= 60):
            return {"status": "blocked_host_safety", "applied": False}, 3

    # A fresh SSH probe is required even in read-only mode. No cached proof.
    try:
        _probe_node(ssh_alias, vm, node, namespace)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        return {"status": "blocked_cluster_unknown", "applied": False}, 3
    if already:
        return {"status": "already_" + before, "applied": False}, 0
    if not apply:
        return {"status": "would_" + action, "applied": False}, 0

    # One last AC/idle/pressure check just before a mutating START.
    if action == "start":
        h = _host_summary()
        age = h.get("status_age_seconds")
        if (h.get("tier") != "boost" or h.get("on_ac") is not True
                or h.get("memory_pressure") != "1"
                or not isinstance(age, (int, float)) or not 0 <= age <= 60):
            return {"status": "blocked_host_safety_changed", "applied": False}, 3
    # Re-check both the guest configuration AND the server-side Node
    # binding immediately before mutation. An earlier snapshot never gives
    # durable authority to operate on this Mac or the cluster.
    fresh_guest = _guest_summary(vm)
    if (fresh_guest != guest or
            fresh_guest.get("isolation_verified") is not True):
        return {"status": "blocked_vm_state_changed", "applied": False}, 3
    try:
        _probe_node(ssh_alias, vm, node, namespace)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        return {"status": "blocked_cluster_changed", "applied": False}, 3
    command = ["limactl", action, vm]
    if action == "start":
        command = ["limactl", "start", "--tty=false", "--timeout=70s", vm]
    try:
        response = _command(command, timeout=90 if action == "start" else 60)
        if response.returncode != 0:
            raise RuntimeError("Lima CLI failed")
    except (OSError, RuntimeError, subprocess.SubprocessError):
        # A timeout could occur after Lima already completed the action.
        return {"status": "vm_mutation_unknown", "applied": "unknown"}, 2
    observed = _guest_summary(vm)
    wanted = "running" if action == "start" else "stopped"
    if (observed.get("vm") != wanted
            or observed.get("isolation_verified") is not True):
        return {"status": "vm_verification_unknown", "applied": "unknown"}, 2
    return {"status": action + "_verified", "applied": True,
            "note": "VM only; does not grant Kubernetes admission"}, 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Manual opt-in Lima VM start/stop with cluster preflight")
    parser.add_argument("action", choices=("start", "stop"))
    parser.add_argument("--vm", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--runner-namespace", required=True)
    parser.add_argument("--ssh-alias", required=True,
                        help="Trusted SSH alias with forced read-only preflight command")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-vm")
    parser.add_argument("--confirm-node")
    args = parser.parse_args(argv)
    try:
        result, code = execute(args.action, args.vm, args.node,
                               args.runner_namespace, args.ssh_alias,
                               args.apply, args.confirm_vm, args.confirm_node)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        result, code = ({"status": "unknown_fail_closed",
                         "reason": type(exc).__name__, "applied": False}, 2)
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
