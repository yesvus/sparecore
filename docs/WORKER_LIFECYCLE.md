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

## Node-scoped RBAC (NOT installed)

The example file deploy/zombie-admission-rbac.yaml describes a
ServiceAccount and ClusterRole scoped to get and patch the node named
zombie. It grants no Pods list, eviction, Secrets, other Nodes, or other
cluster permissions. No kubeconfig or token is copied onto the Mac.

Deploy via the user's existing GitOps workflow after review, and verify
the effective permissions with impersonation:

~~~sh
kubectl auth can-i patch nodes/zombie --as=system:serviceaccount:sparecore-system:zombie-admission
kubectl auth can-i patch nodes/gurbet --as=system:serviceaccount:sparecore-system:zombie-admission
kubectl auth can-i create pods/eviction --all-namespaces --as=system:serviceaccount:sparecore-system:zombie-admission
~~~

Expected after binding: yes, no, no. Kubernetes node patch permission can
modify more than spec.unschedulable, so the eventual actuator must restrict
the patch payload itself and verify the returned Node.

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

## Verified read-only pilot (2026-11-14)

- macOS Python 3.9 and Github CI both ran the planner and its tests.
- Zombie's real Hammerspoon report was Light and under the freshness limit;
  Lima VM showed Stopped with 2 vCPU, 2 GiB RAM, VZ, plain mode,
  no host mounts or host-loopback access.
- Using a temporary ServiceAccount/ClusterRole/Binding on Gurbet,
  actual authorization checks returned YES for get/patch nodes/zombie,
  and NO for patch nodes/gurbet, patch nodes/jelly, list nodes, list
  Pods, create pods/eviction, and get Secrets.
- All temporary RBAC objects were deleted after the permission test.
  No credentials were minted or installed on Zombie.
- The only persistent changes are application code/docs. VM and Node
  admission remain disabled; the Node stays cordoned and tainted.

Note that a future controller must independently confirm fresh Kubernetes
Pod/node state. A local read-only snapshot has no cluster authorization
and cannot certify that an offline Node is already safely cordoned.

## PDB-aware namespaced eviction proof (2026-11-14)

A disposable Gurbet-hosted, resource-limited BusyBox Pod was used to validate
the **real** native Kubernetes policy/v1 Eviction subresource.

- ServiceAccount was permitted only namespace-local Pod GET/LIST and
  CREATE on pods/eviction. The test identity could not evict in any
  neighboring namespace such as default or arc-ops.
- With the only Ready Pod protected by PDB minAvailable=1, the Eviction
  request was correctly denied with HTTP **429 TooManyRequests**.
- After setting **only this disposable test PDB** to minAvailable=0,
  eviction returned HTTP **201**, and the Pod gracefully disappeared.
- All temporary test namespaces, RBAC, PDB and Pods were deleted.
  No production Pod or workload was evicted; the Zombie VM stayed off.

Do not confuse PodDisruptionBudget with CI job completion guarantees:
ARC ephemeral runners may still be interrupted and retry behavior requires
separate validation. A namespace Role allows eviction of other Pods inside
that namespace, so use a dedicated trusted runner namespace and ensure a
trusted cluster-side preflight checks nodeName/owner/Pod phase before
requesting an eviction. A limited service account cannot use ordinary
kubectl drain across the whole cluster without broader Pod listing rights.

The planned GitOps identity is in yesvus/ops PR #584 and will not exist
until the existing manual Argo registration/sync process is completed.
It does not grant Pods/DELETE, node patch or Secret rights.

Correct effective-permission check on this K3s/kubectl version:

~~~sh
kubectl auth can-i create pods --subresource=eviction -n arc-sparecore --as=system:serviceaccount:arc-sparecore:zombie-eviction
kubectl auth can-i create pods --subresource=eviction -n arc-ops --as=system:serviceaccount:arc-sparecore:zombie-eviction
~~~

Expected after **approved GitOps sync**: yes, no. The superficially
similar form "create pods/eviction" in the kubectl auth helper returns
a misleading no here, despite the Role correctly granting the
subresource. Both authorization checks and real HTTP responses were
tested independently.

References: https://kubernetes.io/docs/concepts/scheduling-eviction/api-eviction/
and https://kubernetes.io/docs/reference/access-authn-authz/rbac/ .


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
