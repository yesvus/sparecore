"""Read-only Mac worker inspection. No kubeconfig, no subprocess shells."""
import json
import platform
import subprocess
from typing import Optional

from .worker import WorkerState, plan


def _run(args, timeout=5):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _guest_summary():
    output = _run(["limactl", "list", "--json"])
    if output is None:
        return {"vm": "unknown", "isolation_verified": False,
                "reason": "Lima CLI not found or failed"}
    try:
        # Lima emits JSON-lines; never infer success from a missing instance.
        machines = [json.loads(line) for line in output.splitlines() if line.strip()]
        matches = [x for x in machines if x.get("name") == "sparecore-zombie"]
        if len(matches) != 1:
            raise ValueError("Missing or duplicate owned VM")
        m = matches[0]
        c = m.get("config", {})
        limits_valid = (
            m.get("vmType") == "vz" and m.get("arch") == "aarch64"
            and type(m.get("cpus")) is int and 0 < m["cpus"] <= 2
            and type(m.get("memory")) is int and 0 < m["memory"] <= 2 * 1024**3
            and type(m.get("disk")) is int and 0 < m["disk"] <= 20 * 1024**3
            and c.get("plain") is True
            and c.get("networkOpts", {}).get("hostLoopback") is False
            and not c.get("mounts")
            and not c.get("ssh", {}).get("forwardAgent", False)
        )
        vm = {"Running": "running", "Stopped": "stopped"}.get(m.get("status"), "broken")
        return {
            "vm": vm, "isolation_verified": bool(limits_valid),
            "cpus": m.get("cpus"), "memory_bytes": m.get("memory"),
            "status": m.get("status"),
        }
    except (ValueError, TypeError, AttributeError, KeyError):
        return {"vm": "unknown", "isolation_verified": False,
                "reason": "Unexpected Lima inventory format"}


def _host_summary():
    p = _run(["pmset", "-g", "batt"], timeout=3)
    ac = bool(p is not None and "Now drawing from 'AC Power'" in p)
    pressure = _run(["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                    timeout=2)
    result = _run(["/opt/homebrew/bin/hs", "-c",
                   "local tier, reason = sparecore.status(); return tier, reason, sparecore.statusAge()"], timeout=4)
    tier = "off"
    reason = "Hammerspoon state unavailable or stale"
    age = None
    if result:
        parts = result.split("\t")
        if len(parts) >= 3:
            try:
                age = float(parts[-1])
                if 0 <= age <= 60 and parts[0] in ("off", "light", "boost"):
                    tier, reason = parts[0], parts[1]
            except ValueError:
                pass
    # macOS snapshots independently veto even if the Hammerspoon state is stale.
    if not ac or pressure != "1":
        tier = "off"
        reason = "AC unavailable or system memory pressure not normal"
    return {"tier": tier, "reason": reason, "on_ac": ac,
            "memory_pressure": pressure, "status_age_seconds": age}


def snapshot():
    """Return a safe, non-authoritative overview; does not query Kubernetes."""
    if platform.system() != "Darwin":
        return {"applied": False, "host": {"tier": "off", "reason": "macOS only"},
                "guest": {"vm": "unknown", "isolation_verified": False},
                "plan": {"step": "none", "reason": "Unsupported host"},
                "cluster": "not queried: no kubeconfig is used"}
    host = _host_summary()
    guest = _guest_summary()
    tier = host["tier"] if guest["isolation_verified"] else "off"
    state = WorkerState(tier=tier, vm=guest["vm"], node_ready=None,
                        node_cordoned=None, workloads=None, enabled=False)
    step = plan(state)
    return {"applied": False, "host": host, "guest": guest,
            "plan": {"step": step.step, "reason": step.reason,
                     "requires_confirmation": step.requires_confirmation},
            "cluster": "not queried: no kubeconfig is used"}
