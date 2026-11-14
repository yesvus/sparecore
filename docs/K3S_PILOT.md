# OrbStack -> k3s disposable worker pilot

Status: preflight only. No dedicated OrbStack VM has been created, no k3s
agent was joined, and no CI was routed to the laptop.

## Gates

Before the first VM boot:

- Confirm AC power, normal thermals, a stable SpareCore-eligible state, and
  >=48-72h of CPU, RAM, compression and swap history during normal Mac use.
- Confirm real interactive responsiveness and sufficient RAM headroom.
- Do not start a pilot if the Mac is swapping or SpareCore reports off.
- Require a rollback plan. VM startup and shutdown should be timeboxed.

## Reuse existing components

OrbStack for a bounded ARM64 machine, Tailscale for private transport, k3s
for node lifecycle and scheduling, official ARC for ephemeral runners, and
Prometheus for metrics. No Cindral broker, custom leases, queue or heartbeat.

OrbStack isolated machines remove default host-file integration, but they
share the OrbStack Linux kernel. This is NOT a dedicated trust boundary
against malicious CI. Use trusted-only work; no shared Mac home, forwarded
SSH agent, host Docker socket, public fork workflows or permanent storage.

OrbStack architecture: https://docs.orbstack.dev/architecture

## Manual pilot sequence

1. If host safety gates pass, create a separate isolated Ubuntu ARM64 machine
   with a provisional limit of 2 vCPU, 2 GiB RAM and 30 GiB disk.
2. Confirm systemd, cgroups v2, overlayfs, containerd, nftables/iptables,
   and required network capabilities inside the actual OrbStack guest.
3. Verify guest-to-control-plane and reverse direction, including VPN/NAT
   behavior and Flannel Pod-to-Pod networking. A Ready node is not enough.
4. Join only with initial NoSchedule taint and project-specific labels.
   Never admit production, storage or untrusted workloads by default.
5. Run one harmless resource-limited smoke job. Test manual cordon,
   PDB-respecting drain, restart and unexpected guest disappearance.
6. Add a minimal policy actuator only after safety and networking tests.
   Immediate stop of new admission is distinct from terminating running
   work. Never force-shutdown a running job without reviewing its semantics.
7. Later, official ARC with minRunners=0 for trusted ephemeral CI, using
   the existing ops scale-set deployment rather than a second runner system.

References:
https://docs.k3s.io/cli/agent
https://docs.k3s.io/networking/basic-network-options
https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/

## Live safety snapshot: Nov 14, 2026

Zombie (Apple M2, 16 GiB) was on AC power but did not pass the policy
preflight. Recent 30-minute Prometheus peaks: CPU busy ~63.5% and
swap-out throughput ~5.1 MiB/s. Peaks are not sustained load or validated
headroom. The first OrbStack VM boot is deferred pending safer measurements.
