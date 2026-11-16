# One-shot runner eviction gate (trusted host only)

**Status: manual opt-in; uninstalled; never a VM shutdown authorization.**
This is an incremental primitive for [#11](https://github.com/yesvus/sparecore/issues/11).
The pre-existing read-only inspector `check-node-drain.py` remains unchanged.

`scripts/evict-node-runners.py` uses Kubernetes' **policy/v1 Eviction API**,
not Pod deletion, force drain, a custom queue, or a new controller. It is
only suitable for the narrow, disposable trusted ARC `EphemeralRunner` workload.

## Trust boundary and prerequisites

- Execute on an existing **trusted Linux cluster administration host**. Never
  copy a cluster-admin kubeconfig or eviction credential onto a personal Mac.
- Use **two distinct contexts**: an audit identity capable of listing Pods
  scheduled to the selected Node (cluster-side only) and an eviction identity
  authorized for `pods/eviction` only within the selected runner namespace.
  The tool checks a few effective permissions; independently inspect RBAC
  rules. Arbitrary Kubernetes contexts are *not* inherently restricted.
- The explicitly named Node must **already be cordoned** and retain the
  `sparecore=true:NoSchedule` quarantine taint. The gate never uncordons.
- All Pod inventory on that Node must be visible; foreign namespaces, other
  Pod owners, multiple Pods, unknown phases and racey observations block.
  The only accepted workload owner is official ARC `EphemeralRunner`.
- No evictions of a running runner job by default. An explicit
  `--allow-running` is required *in addition to* manual `--apply` and
  exact `--confirm-node`; this can interrupt a trusted CI job.
  The runner's GitHub retry/cancellation semantics require separate proof.
- API 429 from PodDisruptionBudget, network failures, timeouts and uncertain
  patch/write outcomes always block progression. No `--force`,
  `--disable-eviction`, Pod DELETE or mass eviction.

The public examples below are placeholders **not** credentials or a live
installation. First perform read-only inspection:

~~~sh
python3 scripts/check-node-drain.py \
  --node edge-worker-01 --runner-namespace arc-edge \
  --context AUDIT_CONTEXT

python3 scripts/evict-node-runners.py \
  --node edge-worker-01 --runner-namespace arc-edge \
  --audit-context AUDIT_CONTEXT --eviction-context EVICTION_CONTEXT
~~~

A deliberately authorized *single* native Eviction API request requires:

~~~sh
python3 scripts/evict-node-runners.py \
  --node edge-worker-01 --runner-namespace arc-edge \
  --audit-context AUDIT_CONTEXT --eviction-context EVICTION_CONTEXT \
  --apply --confirm-node edge-worker-01
~~~

For a running job, add `--allow-running` only after the owner explicitly
accepts job interruption. **The tool does not wait for Pod disappearance**.
Even a successful API response reports
`eviction_requested_not_completed` and `shutdown_authorized=false`.
If no Pods are observed, it also reports `shutdown_authorized=false`.
An eventual lifecycle must use a *new*, properly authorized cluster
inventory after any drain and prove an empty, cordoned Node before stopping
the owned Lima guest. It must not treat this one snapshot as a lease.

## Integration status

The existing ops GitOps sources from PR #583/#584 include a target-node
admission identity and a namespace-limited eviction identity. They are
**manually registered and synced** through the ops Argo runbook after
explicit approval, not deployed by merging this PR. The planned runner
namespace is `arc-sparecore`; the `EphemeralRunner` Pod may require
ARC-generated owner references and runtime policy verification. Keep this
public script deployment-agnostic and use the existing official ARC scale
set controller, GitOps and monitoring stack.

Unit tests verify context/identity guards, explicit confirmation,
PDB/timeout uncertainty, changed Node or Pod state, interruption blocking,
native Eviction request shape, and no shutdown permission. No real Pod has
been evicted by this feature. Do not claim unattended owner-priority
lifecycle readiness without a real Mac AC/idle, sleep/wake, thermal,
network-loss and 48–72 hour responsiveness pilot.
