# Lima full VM worker pilot (macOS)

This is an experimental, **manual only** worker integration.
The existing Hammerspoon status menu is still observe-only.

## Why Lima?

The real K3s 1.36.4 agent failed inside the OrbStack shared-kernel machine:
kubelet cannot open its missing kernel message device (/dev/kmsg).
The subsequent agent certificate retries were secondary.
We are not using fake device symlinks or an alpha kubelet feature flag.

Lima 2.3.0, using native Apple Virtualization.framework (VZ), booted
Ubuntu 24.04.5 LTS with an independent kernel and these verified properties:

- 2 vCPU, roughly 2 GiB visible RAM, 20 GiB configured disk
- /dev/kmsg exists as a character device and cgroup v2 is enabled
- Plain mode: no shared Mac directories, guest agent, bundled containerd,
  or dynamic port forwarding; no forwarded host SSH agent
- Host-loopback access explicitly disabled to protect host-local services
- Full VM stopped after each safety smoke check

Documentation: https://lima-vm.io/docs/config/vmtype/vz/

## Existing Zombie setup

The VM is called sparecore-zombie, but the future Kubernetes node will be
called zombie. The Ubuntu guest is configured and stopped. Official Tailscale
was installed from its signed Ubuntu repository and the user enrolled
the guest as a distinct tailnet device. The tested K3s agent is installed,
but is DISABLED at boot and STOPPED when the VM is off. The Kubernetes
Node object named zombie remains cordoned and tainted.

For other Macs, use these commands only after reviewing resource headroom:

~~~sh
brew install lima
limactl create --name=sparecore-zombie --vm-type=vz \
  --cpus=2 --memory=2 --disk=20 --plain --mount-none \
  --containerd=none --set '.networkOpts.hostLoopback=false'   --tty=false template:ubuntu-24.04
~~~

No automatic boot. This instance already exists on Zombie; do not recreate it.

## Enroll guest (one time, explicit owner approval)

From the SpareCore checkout on the Mac, run interactively:

~~~sh
bash scripts/enroll-lima-tailscale.sh
~~~

The script verifies AC power, memory safety, user-priority mode and VM limits.
After typed consent, the official Tailscale CLI prints a private browser login
URL for this *new* Linux guest. Do not paste that URL into public repos or logs.
The script verifies registration and stops the VM on completion or failure.
This step has already been performed on Zombie and should not be repeated
unless repairing or re-enrolling the VM.

Do NOT copy the Mac's Tailscale identity or reuse the still-stopped OrbStack
guest's credentials. After the Lima replacement works, review retirement of
the old pilot and its stale tailnet device.

## Live pilot acceptance evidence (2026-11-14)

The full Linux VM has passed **actual** Kubernetes registration and network
testing. The real cluster is K3s v1.36.4+k3s1. Results:

| Check | Observed |
| --- | --- |
| macOS eligibility | AC, nominal thermals, normal memory pressure |
| Lima guest | Ubuntu 24.04.5 LTS ARM64, full native VZ Linux kernel |
| Network | Tailnet peer and API reachable in both directions |
| Flannel ingress | UDP 8472 request/response succeeds |
| Node identity | zombie, flannel-iface tailscale0 |
| Node isolation | sparecore=true:NoSchedule, additionally cordoned |
| Kubelet status on startup | Ready |
| CPU | 2 core capacity, 1700m allocatable |
| RAM | about 1.91 GiB capacity, about 1.28 GiB allocatable |
| Pod count | max-pods=4 |
| Rejoin after stopping | Ready again with existing kubelet certificates |
| DNS | kubernetes.default.svc.cluster.local resolves in a Pod |
| Pod-to-Pod | busybox client on zombie can reach a server Pod on gurbet |
| Pod-to-Service | client reaches server via Kubernetes Service DNS |
| End of test | client Succeeded, server/test namespace deleted |
| Credentials | temporary K3s bootstrap token revoked, zero active tokens |
| Current condition | guest stopped; agent disabled; zombie cordoned |

A resource-limited BusyBox client Pod ran on Zombie and reached a
resource-limited server Pod on Gurbet via both direct Pod IP and Kubernetes
Service DNS. Both tests returned the expected fixed string. This is a
**functional smoke test**, not a sustained-load, latency, thermal, or
untrusted-code safety certification.

### Next engineering gate

1. Implement the smallest owner-priority host actuator: fail-closed admission
   control (cordon), bounded drain that respects jobs and PDBs, then guest
   stop. An AC-loss event must never silently continue scheduling jobs.
2. Use strict, node-scoped RBAC: no full cluster-admin kubeconfig on the
   personal Mac. Use native Kubernetes node conditions/leases, not custom
   heartbeat/lease infrastructure.
3. Validate 48-72h normal-use interactive latency, power and memory pressure
   before assigning jobs. The current Hammerspoon menu still **only
   observes**, so it does NOT shut down a VM automatically on battery yet.
4. Pilot a single **trusted** ARC ephemeral runner via existing cluster ARC,
   with minRunners=0, explicit node selector and taint tolerations.
5. Review and retire the old stopped OrbStack pilot and its stale tailnet
   device after verifying there are no user-owned assets inside.
6. Keep untrusted fork workflows, databases and irreplaceable state off this
   opportunistic laptop.

Do not confuse a K3s Node showing Ready with permission to schedule work.
The node is intentionally cordoned even when it temporarily transitions
through Ready while the VM shuts down.
