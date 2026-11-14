# Design: reuse operationally proven components

Kubernetes node lifecycle and taint-based eviction already handle unreachable
and unhealthy nodes. When voluntarily taking a node offline, use the existing
cordon / drain / uncordon API, not a custom lease or heartbeat protocol.
Drain honors PodDisruptionBudgets and graceful termination. An unexpected VM
power loss may kill a job; only reschedulable workloads are appropriate.

Official GitHub Actions Runner Controller (ARC) manages the lifecycle of
ephemeral runner Pods and their registration with GitHub. Do not rebuild
ARC's runner queue, retry protocol, heartbeat or runner state.

SpareCore's only job is host safety policy and an optional, guarded actuator.
An admission downgrade needs to prevent new work immediately; it does not
limit an already running build. Separate fixed VM CPU/RAM/IO/disk limits are
mandatory, and power source changes must never blindly kill a running job.

The future Android/Termux adapter is a separate rootless executor backend.
PRoot does not magically provide cgroups or a privileged kubelet.
Archived Cindral is a reference for boundaries, not a dependency.

Milestones: telemetry -> tested sensor policy -> isolated VM -> manual
drain/cordon -> guarded automation -> ARC integration -> Android prototype.
