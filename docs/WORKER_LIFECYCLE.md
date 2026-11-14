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
python3 -m sparecore worker
python3 -m sparecore worker --input '{"tier":"boost","vm":"stopped","node_ready":null,"node_cordoned":true,"workloads":0,"enabled":true,"admission_verified":false}'
~~~

The first command reads local macOS Hammerspoon/Lima state and explicitly
reports that cluster state was not queried. The second plans a theoretical
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
