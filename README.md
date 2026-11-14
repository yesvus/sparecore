# SpareCore

**Borrow spare compute from your personal device without sacrificing responsiveness.**

SpareCore is open-source, opt-in compute capacity management. The first platform is
macOS: it observes power, CPU, memory pressure, swap traffic, thermals and idle time.

> **Pre-alpha / observe only.** The current menu displays hypothetical Off,
> Light, and Boost eligibility. It does not start a VM, join Kubernetes, or run CI.

## Quick start (macOS)

Want an AI coding agent to install it? Copy this prompt:

~~~text
Help me set up SpareCore on my Mac: https://github.com/yesvus/sparecore
Read INSTALL_PROMPT.md and README.md before making changes.
Start with observe-only mode, run doctor and tests, and preserve my
existing Hammerspoon config. Ask before installing software, creating
VMs or changing network/cluster settings. Never request secret keys.
~~~

[Complete install prompt](INSTALL_PROMPT.md)

Requirements: Python 3.9+, macOS and Hammerspoon. For the experimental
external k3s worker, prefer Lima with native macOS Virtualization.framework.
OrbStack is optional for general Linux development; its shared-kernel machines
did not pass our kubelet preflight. Tailscale is optional until cluster join.

Clone and verify:

~~~sh
git clone https://github.com/yesvus/sparecore.git
cd sparecore
python3 -m unittest discover -s tests -v
python3 -m sparecore doctor
~~~

If necessary, install Hammerspoon via Homebrew (with your approval):

~~~sh
brew install --cask hammerspoon
~~~

Open Hammerspoon once. Add **one** line to your existing
~/.hammerspoon/init.lua, replacing the path with your absolute clone path:

~~~lua
sparecore = dofile("/absolute/path/to/sparecore/adapters/hammerspoon/init.lua")
~~~

Do not overwrite an existing Hammerspoon configuration. Choose Reload Config.
A single CPU-shaped icon should appear in the menu bar.

The menu has Auto, On, Off modes. These are **safety decisions only** until
the guarded worker actuator is implemented. Battery power always blocks compute.

See [installation and troubleshooting](docs/INSTALLATION.md).

## Components

| Layer | Implementation |
| --- | --- |
| macOS sensing / menu | Hammerspoon |
| Pure capacity policy and read-only doctor | Python 3.9+ standard library |
| Full Linux VM for k3s (manual pilot) | Lima native VZ driver |
| Optional shared-kernel dev Linux | OrbStack (not a verified k3s backend) |
| Optional private networking | Tailscale |
| Future trusted CI worker | k3s + official ARC |

SpareCore does not implement custom queues, schedulers, heartbeats or leases.
It does not promise interaction is unaffected until resource limits and
real-world latency tests are completed. Do not run untrusted CI on personal devices.

## Current status and roadmap

- [x] Pure safety policy, CPU/memory/swap/thermal sensing, one menu icon
- [x] AC-only safety and read-only system doctor
- [x] OrbStack k3s limitation identified (missing kernel log device)
- [x] Full Lima Ubuntu 24.04 LTS VM with kernel device and cgroups verified
- [ ] Guided installer/wizard with explicit confirmation before mutations
- [x] Dedicated Lima guest Tailscale identity and bidirectional Pod network smoke
- [x] K3s ARM64 node named zombie joined, with NoSchedule taint and strict
      resource reservations; restart/rejoin verified using existing certificates
- [ ] Safe owner-priority VM/Node actuator and official ARC integration
- [ ] Linux and rootless Termux adapters

[Architecture](docs/ARCHITECTURE.md) ·
[Current Lima k3s pilot](docs/LIMA_PILOT.md) ·
[Historical OrbStack pilot](docs/K3S_PILOT.md) ·
[Contributing](CONTRIBUTING.md)

MIT licensed. SpareCore is experimental software.
