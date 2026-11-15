# Agent instructions for SpareCore

Read README.md and INSTALL_PROMPT.md before any installation task.
Read docs/INSTALLATION.md for help and docs/K3S_PILOT.md for a manual pilot.

- The main CLI and Hammerspoon menu are observe-only. Never imply otherwise.
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

- The optional scripts/check-zombie-drain.py is a READ-ONLY snapshot for
  a trusted cluster administration host, not the Mac, and never authorizes
  an unattended VM shutdown by itself.

- scripts/fence-zombie.py is a separate, OPTIONAL manual cordon-only tool for
  a trusted cluster-side host with narrowly scoped node RBAC. It must never be
  invoked automatically from macOS or with cluster-admin credentials.
  No uncordon/drain/eviction/VM control is permitted by that tool.
