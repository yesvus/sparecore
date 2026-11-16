# Manual guarded Lima VM control (macOS only)

**Status: optional one-shot CLI; not installed, not wired to Hammerspoon.**
This tool is a building block for [#11](https://github.com/yesvus/sparecore/issues/11),
not an automatic ARC/k3s worker and not a complete crash-safe lifecycle.

`python3 -m sparecore.lima_control` can start or stop **only one explicitly
selected existing and isolated Lima VZ VM**, with independent, fresh,
cluster-side read-only verification. It never creates VMs, changes Node
scheduling, manages the guest kubelet, evicts Pods, or installs kubeconfigs.

## Trust boundary

- Use macOS with the original Hammerspoon policy already running.
  A **start** requires AC power, normal memory pressure, fresh (at most
  60 seconds) `boost` eligibility, and the Hammerspoon two-minute stability
  gate. The CLI double-checks host safety immediately before `limactl start`.
  The Hammerspoon `Auto / On / Off` menu is **still observe-only**.
- `--vm` selects an existing Lima VZ ARM64 guest. Read-only inspection
  enforces existing 2 vCPU / 2 GiB RAM / 20 GiB disk and isolation limits.
  Missing, broken or unexpectedly configured guests are never actuated.
- `--ssh-alias` names an explicitly configured, pinned-host-key SSH
  destination for a **trusted cluster-side read-only** helper. The helper
  command is `sparecore-readonly-node-check --node NAME
  --runner-namespace NS`; it must execute the existing
  `scripts/check-node-drain.py` from the trusted administration host
  and return its JSON without any extra banners. An account with a forced
  command/restricted SSH key is strongly preferred. No Kubernetes kubeconfig
  or long-lived cluster credential is placed on the personal Mac.
- Every invocation requires a fresh SSH result of
  `status=no_pods_observed`, `node_cordoned=true`,
  `taint_present=true`, `runner_pods=[]` and `foreign_pods=[]`.
  SSH errors, unsafe inventory, unknown Node, stale host status, failure
  to verify the Lima VM, or any parsing failure are blocking conditions.
- `--apply` requires **both** `--confirm-vm` and `--confirm-node`
  to match exactly. Without `--apply`, the CLI may inspect host/guest/
  cluster state but cannot start or stop a VM.
- `stop` only proceeds after the current cluster check reports a cordoned,
  quarantined, empty Node. This is a snapshot and **not** race-free permission
  for unattended shutdown. If any Pod exists, stop is blocked. On a failed or
  timed-out Lima mutation, status is `applied="unknown"`; do not auto-retry.

## Example (identities are placeholders)

On the trusted Linux host, operator configures a read-only command
`sparecore-readonly-node-check` that invokes the checked-in
`scripts/check-node-drain.py` for the specific authorized Node and runner
namespace, using an existing cluster-side audit context. A forced-command
SSH identity must not allow shell or port forwarding. Never create such a
key, copy kubeconfig, or change SSH policy without separate owner approval.

On the Mac, after verifying the SSH alias has a pinned known host key:

~~~sh
# Read-only:
python3 -m sparecore.lima_control start \
  --vm example-worker --node edge-worker-01 \
  --runner-namespace trusted-runners --ssh-alias sparecore-audit

# One explicitly confirmed VM-only action (requires separate owner approval):
python3 -m sparecore.lima_control start \
  --vm example-worker --node edge-worker-01 \
  --runner-namespace trusted-runners --ssh-alias sparecore-audit \
  --apply --confirm-vm example-worker --confirm-node edge-worker-01
~~~

A stop uses the identical parameters with action `stop`. Do not infer that
successful VM start means Node Ready, that kubelet automatically started, or
that new jobs are authorized. The pilot's k3s agent was left **disabled at
boot**. Admission/uncordon remains a separate owner-approved cluster-side
action, and PDB-aware evacuation from
[the manual gate](EVICTION_GATE.md) must be verified before stop.

## What remains before unattended Auto / On / Off

1. A strictly scoped, operator-reviewed cluster control path for
   native cordon, safe uncordon, eviction/drain and final Pod inventory;
   no broad laptop credential or privileged custom scheduling service.
2. Real macOS Hammerspoon mode/event integration, wake/sleep/AC loss
   behavior, restart-rate limiting and safe unknown-state handling.
3. The dedicated trusted ARC namespace/scale-set credentials and
   manually approved Argo sync from ops #842, and actual ephemeral CI
   job cancellation/retry/PDB validation.
4. A minimum 48–72 hour real-device study of interactive latency, swap,
   thermals, CPU load and battery impact. Node exporter/Prometheus
   integration should reuse the existing observability stack.

**This CLI has only been validated by unit tests and Linux-host code review;
there has been no real Mac VM start/stop, no Node mutation or live Pod eviction.**
