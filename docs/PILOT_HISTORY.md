# Historical pilot evidence (2026-11-14)

This is a dated record of the maintainer's personal cluster pilot. The Node,
host, namespace, GitOps repo and guest names below are **not SpareCore defaults**,
and no one needs these machines or accounts to run SpareCore. Use the generic
[worker lifecycle](WORKER_LIFECYCLE.md) for instructions.

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


