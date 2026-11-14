# OrbStack -> k3s disposable worker pilot

Status: isolated smoke VM was created and booted briefly; no k3s
agent was joined, and no CI was routed to the laptop. It is stopped by
default.

## Gates

Before the next VM start:

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

## Verified experimental guest (2026-11-14)

An isolated Ubuntu 24.04 ARM64 guest named sparecore-pilot was created with
2 CPU, 2 GiB memory and 20 GiB maximum disk. Inspection using OrbStack
reported the caps, isolated mode and SSH agent forwarding disabled.
Inside the guest, cgroup v2 reported cpu.max 200000 100000 and
memory.max 2147483648; systemd, overlay filesystem and /dev/net/tun are
present. The guest reached the Gurbet API TCP port through OrbStack NAT.

The Linux /proc/meminfo and nproc views show host kernel capacity, not the
effective cgroup limits; check cgroup quota files for actual enforcement.
The smoke guest was stopped after testing, with no kubelet installation.

Run scripts/smoke-orbstack.sh on Zombie for a gated, read-only retest.
The next major unverified item is inbound network reachability and Flannel
Pod routing. This requires an explicit Tailscale guest-network design,
not just a reachable control-plane port.

## Additional guest networking checks (2026-11-14)

- A temporary Linux VXLAN interface using UDP 8472 was created successfully
  and removed immediately. This verifies kernel/netlink support, **not**
  working cross-node Flannel traffic.
- Official Tailscale 1.104.7 was installed inside the isolated guest from
  Tailscale's signed Ubuntu Noble apt repository. The systemd daemon was active
  during testing, but the guest has **not enrolled in the tailnet**.
- VM was stopped after the tests. Mac remained on AC and used swap was 0 MB.

### Remaining network admission gate

Existing k3s nodes use Flannel VXLAN with Tailscale peer addresses. The
new guest requires its own tailnet identity and inbound reachability; OrbStack
outbound NAT alone is insufficient.

1. Register the guest as a distinct tailnet device via official Tailscale
   interactive authentication or a narrowly scoped expiring auth key.
   Do not copy the Mac host identity or commit credentials.
2. Review tailnet grants/ACLs for at least Kubernetes API TCP 6443, the
   necessary kubelet TCP 10250, and Flannel VXLAN UDP 8472 between nodes.
   Never publish these ports on the open Internet.
3. Verify a real tailscale0 guest interface, bidirectional node access and
   kernel overlay routing. Confirm Pod-to-Pod and Pod-to-Service networks,
   rather than treating Node Ready as sufficient.
4. Only then test joining a tainted, dedicated ARM64 k3s agent and running
   an explicitly selected, resource-limited smoke Pod.

VM is stopped between tests. No node secrets, tailnet auth links or
host-private addressing are committed to this project.
