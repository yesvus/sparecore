# Worker lifecycle: owner-first, native Kubernetes

**Status: planner only, no resource changes.** The K3s registration and Pod
networking smoke passed, but VM lifecycle, Node admission, native PDB-aware
drain and ARC dispatch are not automatically enabled.

## Current design

The Mac remains the owner. SpareCore runs a pure decision policy in
Hammerspoon (AC power, CPU, memory/swap, thermals and idle), with a stable
two-minute Boost gate. The Linux worker is a bounded Lima VZ VM.

The new stateless advisory planner can be used without Kubernetes,
admin tokens, or service installation:

~~~sh
python3 -m sparecore worker --vm edge-worker-01
python3 -m sparecore worker --input '{"tier":"boost","vm":"stopped","node_ready":null,"node_cordoned":true,"workloads":0,"enabled":true,"admission_verified":false}'
~~~

The first command reads macOS Hammerspoon and only an explicitly selected
Lima guest (replace the example with the name of your existing VM).
Without --vm, guest status is unknown rather than auto-selected.
The command explicitly reports that cluster state was not queried. The second plans a theoretical
transition from supplied facts. Both always return applied=false.
Neither command starts a VM, talks to Kubernetes, or changes any file.

The planner proposes at most one next step per evaluation:
- Off / Light: never start a VM. If a Node is schedulable, propose cordon
  first. Once cordoned, propose native drain only with known active work.
  If Pod/node visibility is missing, require inspection, not shutdown.
  With verified zero workloads, it can propose stop_vm.
- Boost and explicitly enabled: from stopped propose start_vm; from running
  but unready, wait; propose admit only after independent RBAC and
  trusted-workload isolation verification. Otherwise keep node cordoned.
- Enabled=false: never start or admit. On a running Node, propose
  cordon, drain, then stop only when empty. Broken guests are not forced.

No action in a plan is an executable kubectl/limactl operation.
A later actuator will need its own opt-in and tests.

## Node-scoped RBAC example (NOT installed)

The public sample `examples/rbac/node-admission.yaml` illustrates a
ServiceAccount with GET/PATCH rights to **one fictitious example Node** named
`edge-worker-01`. Operators must replace this identity with their own
and review the permissions in their separate GitOps deployment. The
public repository never applies this YAML automatically, distributes
credentials or assumes a particular cluster.

Confirm effective rights for the chosen node and verify denied access to
other Nodes, Pods, eviction APIs and Secrets. A Node PATCH grant can edit
fields beyond the cordon flag, so the narrowly scoped identity and the
manual cordon-only helper must be independently reviewed.

## Drain constraint

Native kubectl drain needs a list of Pods and authorization to evict them.
Granting cluster-wide pods/eviction rights to a personal Mac is too broad.
Do NOT use cluster-admin, --force, --disable-eviction, or ignore PDB failure.
The ARC workloads will be restricted to an approved namespace and node.
Choose a minimal cluster-side drain authority or namespace-limited
eviction flow for that boundary, keeping the authority away from the Mac.

Power loss must block new admissions immediately. A bounded PDB-respecting
drain and explicit interruption handling are required before graceful
shutdown becomes automatic. If drain cannot finish, never silently claim
a safe stop. Critical uninterruptible work must not run on this node.

## Acceptance gates before automatic worker

- 48 to 72 hours interactive-latency and resource-pressure baseline
- No Boost if Hammerspoon status is stale (more than 60 seconds)
- AC loss, thermals, sleep, missing cluster API and VM failures
- Native PDB-aware drain and retry without custom leases or queues
- Scoped RBAC without a cluster-admin kubeconfig on the Mac
- Real ARC ephemeral runner policy and tested cancellation/retry
- No autonomous VM start or k3s scheduling until all gates pass

Sources:
https://kubernetes.io/docs/reference/kubectl/generated/kubectl_drain/
https://kubernetes.io/docs/reference/access-authn-authz/rbac/

[Historical maintainer pilot evidence](PILOT_HISTORY.md) is kept only
as an example and is not required for a new installation.

## Read-only node drain preflight (generic)

On a trusted cluster-administration host with the required read privileges:

~~~sh
python3 scripts/check-node-drain.py --node edge-worker-01 \
  --runner-namespace arc-edge --context YOUR_CONTEXT
~~~

Replace both example identities and context for your installation. The
preflight performs ONLY kubectl GET on the selected Node and a Pod inventory
filtered to that Node, requiring cordon and a project NoSchedule taint.
Exit 0 means no Pods observed (not permission to shut down the VM); exit
3 means scheduling open, foreign Pods or runner Pods needing review; exit
2 means unknown/fail-closed. Never copy cluster-admin credentials onto
a personal laptop.

## Optional manual node admission fence (not deployed)

`scripts/fence-node.py` is a **generic** and narrowly scoped cordon-only
safety tool. It is *not* an automatic actuator and must run only from a trusted
cluster-side host, never by copying cluster credentials to a personal device.
Its only write sets `spec.unschedulable=true` on the explicitly named Node.
It cannot uncordon, drain, evict, schedule CI, or start/stop a VM.

A user configures their own Kubernetes Node name and scoped context; no pilot
hostnames or cluster identifiers are built into the tool. Use a dedicated
identity with `get/patch` permission on **only** that Node, not cluster-admin.
The tool checks effective permission for the chosen Node and rejects unscoped
`patch nodes`; the operator must also independently audit Role rules.
The Node must have a matching `sparecore=true:NoSchedule` quarantine taint
(or an explicitly supplied alternative taint key/value).

~~~sh
# Read-only inventory:
python3 scripts/fence-node.py --node edge-worker-01 --context MY_SCOPED_CONTEXT
# Manual change, only with explicit authorization:
python3 scripts/fence-node.py --node edge-worker-01 --context MY_SCOPED_CONTEXT \
  --apply --confirm-node edge-worker-01
~~~

Default output is `would_cordon` / `already_cordoned` with
`applied=false`. For mutations, context, target name, matching confirmation,
specific RBAC, quarantine taint and fresh Node UID/resourceVersion are
required. An atomic JSON Patch checks UID/version then sets the scheduling
flag; a fresh GET verifies success. Unknown outcome is reported as
`applied="unknown"`, never silently retried or treated as successful.

This command is not wired to the Mac, GitOps, ARC, or any daemon. Actual
operation still requires an operator-reviewed scoped RBAC deployment,
PDB-aware evacuation rules and independent host responsiveness tests.
