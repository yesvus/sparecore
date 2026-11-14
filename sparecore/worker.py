"""Pure, intentionally non-executing lifecycle admission planner.

Never give this module cluster credentials or install it as a daemon.
The plan is *advisory*. All actual Kubernetes drain/RBAC operations remain
separate, explicitly authorized, and PDB-aware.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class WorkerState:
    # This tier is computed by the existing trusted macOS sensor policy.
    tier: str
    # Only the one owned Lima VZ worker is supported.
    vm: str
    # Unknown is expected when the cluster is unreachable.
    node_ready: Optional[bool]
    node_cordoned: Optional[bool]
    # Number of *non-DaemonSet* workload pods on the node (not a PID count).
    workloads: Optional[int]
    # Explicit advance opt-in; never infer it from "Auto" in Hammerspoon.
    enabled: bool = False
    # True only after credential-scoping + workload isolation verification.
    admission_verified: bool = False

    def __post_init__(self):
        if self.tier not in ("off", "light", "boost"):
            raise ValueError("tier must be off, light or boost")
        if self.vm not in ("stopped", "running", "broken", "unknown"):
            raise ValueError("unknown VM state")
        if self.node_ready is not None and type(self.node_ready) is not bool:
            raise ValueError("node_ready must be bool or null")
        if self.node_cordoned is not None and type(self.node_cordoned) is not bool:
            raise ValueError("node_cordoned must be bool or null")
        if self.workloads is not None and (
            type(self.workloads) is not int or self.workloads < 0
        ):
            raise ValueError("workloads must be nonnegative integer or null")
        if type(self.enabled) is not bool or type(self.admission_verified) is not bool:
            raise ValueError("invalid opt-in flags")


@dataclass(frozen=True)
class Plan:
    step: str
    reason: str
    # Informational: do not treat "next_step" as a shell command.
    requires_confirmation: bool = True
    applied: bool = False


def plan(state: WorkerState) -> Plan:
    """At most one next step; never automatically skip cordon or safe drain.

    Only a stable macOS "boost" allows capacity admission. "light" means
    protecting interactive use, not a license to schedule background work.
    """
    if state.vm in ("broken", "unknown"):
        return Plan("inspect", "VM status unknown or broken; never force-start or stop")
    # A stopped VM must not leave a Kubernetes Node mistakenly schedulable.
    if state.vm == "stopped" and state.node_cordoned is False:
        return Plan("cordon", "VM stopped but Kubernetes admission still open")
    if state.vm == "stopped" and state.node_cordoned is None:
        return Plan("inspect", "VM stopped; cannot verify Kubernetes admission")
    if not state.enabled:
        if state.vm == "running" and state.node_cordoned is False:
            return Plan("cordon", "Explicit opt-in is off; block any new scheduling first")
        if state.vm == "running":
            if state.node_cordoned is None:
                return Plan("inspect", "Node admission unknown; cannot verify cordon")
            if state.workloads is None:
                return Plan("inspect", "Active workload count unknown; refusing VM shutdown")
            if state.workloads:
                return Plan("drain", "Opt-in off; evict controlled work through native PDB-aware drain")
            return Plan("stop_vm", "Opt-in off; node cordoned and no active workloads")
        return Plan("none", "Opt-in disabled; VM already stopped", False)
    if state.tier != "boost":
        if state.vm == "stopped":
            return Plan("none", "Owner not idle with stable headroom; do not start VM", False)
        if state.node_cordoned is False:
            return Plan("cordon", "Owner active or unsafe; immediately stop new admission")
        if state.node_cordoned is None:
            return Plan("inspect", "Cluster state unavailable; cannot assume admission is blocked")
        if state.workloads is None:
            return Plan("inspect", "Workload state unavailable; never blindly stop running jobs")
        if state.workloads:
            return Plan("drain", "Existing work must finish or be PDB-evicted before VM stop")
        return Plan("stop_vm", "No active work, node already cordoned; stop bounded VM")
    # boost / enabled
    if state.vm == "stopped":
        return Plan("start_vm", "Boost eligible and explicitly opted in; boot known bounded Lima VM")
    if state.node_ready is not True:
        return Plan("inspect", "Wait for kubelet, Tailscale and API readiness")
    if state.node_cordoned is None:
        return Plan("inspect", "Node scheduling state unknown; fail closed")
    if not state.admission_verified:
        if not state.node_cordoned:
            return Plan("cordon", "Workload isolation not approved; keep node fenced")
        return Plan("none", "Ready but admission/RBAC validation not completed", False)
    if state.node_cordoned:
        return Plan("admit", "Explicitly isolated trusted work may be admitted")
    return Plan("none", "Node already admitted with safety guards in place", False)
