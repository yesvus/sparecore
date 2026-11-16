# Agent instructions for SpareCore

Read README.md and INSTALL_PROMPT.md before any installation task.
Read docs/INSTALLATION.md for help and docs/K3S_PILOT.md for a manual pilot.

- The main `python3 -m sparecore` CLI and Hammerspoon menu are observe-only.
  The separate `python3 -m sparecore.lima_control` CLI is manual opt-in,
  NOT wired to the Hammerspoon menu or an unattended service.
- Preserve existing user configuration. Do not overwrite Hammerspoon init.lua.
- Ask before installing packages, granting permissions, connecting a tailnet,
  creating VMs, joining Kubernetes, or changing secrets/production systems.
- Use proven Hammerspoon, Lima VZ, Tailscale, k3s and official ARC primitives.
- OrbStack Linux machines failed real k3s kubelet preflight (missing /dev/kmsg);
  do not recommend them as full-kernel workers by default.
- Never write custom lease management, queue, CI broker or schedulers.
- No private addresses, credentials, authentication URLs or kubeconfigs in Git.
- Tests: python3 -m unittest discover -s tests -v.
- No untrusted CI on personal devices.

- python3 -m sparecore worker and worker --input are READ-ONLY. They must not
  start a VM, cordon/drain/uncordon a node or claim to have done so.
- Never put a cluster-admin kubeconfig on the owner laptop.

- The optional scripts/check-node-drain.py requires explicit --node and
  --runner-namespace, and is a READ-ONLY cluster-host snapshot, never
  permission for unattended VM shutdown.
- The macOS worker inspector requires --vm to select an existing guest.
  Never hard-code a maintainer's VM into the public runtime.
- Keep pilot identities in historical documentation, separate from product
  defaults and reusable unit tests.

- The optional scripts/fence-node.py is generic, node-name parameterized and
  manual cordon-only; run it only from a trusted cluster-side host with scoped
  credentials, never automatically on a personal device.
- Public library/runtime code must not depend on deployment-specific names
  (personal machines, cluster nodes, cloud tenants, domains or private paths).
  Keep pilot configuration and local Kubernetes manifests separate from the
  reusable implementation; avoid adding new machine-specific defaults.

- scripts/evict-node-runners.py is a manual **trusted-cluster-host only**
  single-Pod native Eviction API request, never macOS actuator, automated
  drain, VM shutdown permission or general eviction authorization.
- Reject Pod/Node inventory uncertainty and any foreign or untrusted Pod.
  A PDB denial or timeout blocks shutdown; never force-delete Pods.
  Do not run this script against a live cluster without separate approval.

- The one-shot Lima CLI must never bypass the Mac boost/AC/pressure gate on
  start, the fresh trusted cluster-side cordon-and-zero-Pod preflight for
  either direction, or exact VM+Node confirmation for apply. It must not
  carry Kubernetes credentials, invoke guest kubelet, patch Nodes, or evict
  Pods. Neither a read-only cluster snapshot nor successful VM boot proves
  safe automatic lifecycle. Real VM action needs separate owner approval.
