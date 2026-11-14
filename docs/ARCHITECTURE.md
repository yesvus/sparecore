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

## macOS K3s backend decision (2026-11-14)

OrbStack's shared-kernel machine could not launch kubelet because the
kernel message device was absent. We will not depend on synthetic kernel
devices or experimental kubelet feature flags for the default runtime.

Use a full ARM64 Linux guest via Lima and the native macOS VZ backend.
A Lima 2.3.0 Ubuntu 24.04.5 LTS guest passed preflight with a real kernel
message device, cgroup v2, two guest CPUs and about 2 GiB guest RAM.
Use plain mode without macOS shared mounts or bundled containerd,
with host-loopback access disabled.
The macOS owner-first Hammerspoon policy is unchanged.
OrbStack remains an optional developer tool, not an approved K3s backend.


## Verified network and scheduler pilot

On 2026-11-14, an ARM64 Ubuntu 24.04 LTS Lima VM successfully joined
K3s as zombie with an initial NoSchedule taint. Actual DNS, cross-node
Pod-to-Pod connectivity and Kubernetes Service traffic passed. Kubelet
capacity/allocatable agrees with the VM size and configured reservations.
The node remains cordoned with the agent disabled between manual runs.

This is a one-time functional pilot, not an unattended resource-sharing
controller. The owner-priority host actuator, scoped RBAC credentials,
admission/drain lifecycle, and ARC workloads are still unimplemented.
