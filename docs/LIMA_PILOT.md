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
was installed from its signed Ubuntu repository, but the guest is NOT yet
enrolled in the tailnet. No k3s agent is installed in this new guest.

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

Do NOT copy the Mac's Tailscale identity or reuse the still-stopped OrbStack
guest's credentials. After the Lima replacement works, review retirement of
the old pilot and its stale tailnet device.

## Next acceptance gates

1. Bidirectional Tailscale TCP, UDP 8472 and Kubernetes API TCP 6443.
2. Pin compatible ARM64 k3s; create a **short-lived bootstrap token** for join,
   not a long-lived control-plane/server token. Never expose it in logs.
3. Configure node-name zombie, explicit guest tailnet node IP, flannel-iface
   tailscale0, and sparecore=true:NoSchedule initial taint.
4. Verify Ready, accurate Allocatable memory and CPU, cgroup isolation,
   Flannel Pod-to-Pod/Service traffic and a single tiny trusted smoke Pod.
5. Stop and disable agent after pilot, stop VM and check other nodes remain
   Ready. Never schedule databases, long-running stateful work or untrusted CI.
6. Build a guarded local actuator only after host latency and 48-72h
   baseline comparisons. Kubernetes/ARC own lifecycle and runner leases.

This pilot is not a production installation or evidence of safe unattended
operation on a laptop.
