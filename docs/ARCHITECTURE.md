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

## macOS measurements

The Hammerspoon menu uses asynchronous CPU sampling so the GUI is never blocked
by the default synchronous 100ms CPU snapshot. The VM swap counters are sampled
30s apart and converted from pages into MiB/s; an unknown first sample does
not qualify for boost.

The bounded macOS-specific sysctl probe reads
kern.memorystatus_vm_pressure_level (normal=1, warning=2, critical=4),
whose userspace values must NOT be confused with the XNU internal pressure
enum. This is a non-public API and any failure leaves memory safety unknown.

Hammerspoon uses hs.host.thermalState(): nominal permits boost, fair limits
to light, serious/critical stop eligibility. Two additional minutes of
sustained boost readiness are required before showing boost. Immediate unsafe
state downgrades are not delayed.

Validate policy decisions against real interactive latency before worker
actuation; pressure signals alone do not guarantee that a Mac will stay
responsive. Never expose personal device paths in shared repo state.
