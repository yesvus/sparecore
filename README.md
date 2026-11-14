# SpareCore

Turn **spare capacity on personal devices** into opt-in, low-impact compute.
The device owner's responsiveness and battery come first.

**Status: pre-alpha / observe-only.** This version never starts OrbStack,
joins Kubernetes, schedules jobs or modifies any cluster.

## MVP

- Pure, deterministic safety policy: off / light / boost.
- On battery: off, even with manual On selected.
- Interactive AC: light only; idle AC can boost after memory-pressure checks.
- Missing CPU info fails closed. Unknown memory safety forbids boost.
- Portable Python 3.9+ CLI and Hammerspoon macOS status menu prototype.

To test: python3 -m unittest discover -s tests -v

To try the policy:

    python3 -m sparecore decide --input '{"on_ac":true,"idle_seconds":400,"displays_asleep":false,"cpu_busy_percent":20,"memory_safe":true,"mode":"auto"}'

The Hammerspoon demo can be loaded with an absolute-path dofile call from
~/.hammerspoon/init.lua. It currently does not collect a validated
memory-pressure signal and cannot boost.

## Architecture

- Host sensor adapters: macOS Hammerspoon, future Linux and Android/Termux.
- Portable policy core: decides whether capacity may be offered.
- Actuator (future): OrbStack VM; Kubernetes cordon, drain and uncordon.
- Kubernetes scheduler and **official ARC** manage jobs and ephemeral runners.
- Built-in Kubernetes node lifecycle and ARC manage readiness, retry,
  lifecycle and leases: **SpareCore does not implement any of these.**
- No new broker, controller, job queue, custom retry or lease implementation.
- Android without root should use an established rootless task executor,
  rather than pretending to be a native Kubernetes worker.
- Never run untrusted fork PR code on a personal device by default.
- Hard CPU/RAM/disk limits and safe shutdown are prerequisites to actuation.

Prior art: archived Cindral is only a reference for deterministic policy and
failure boundaries, not code to port.

Next steps: 48-72 hours of Prometheus measurements; memory/swap/thermal
sensors; hysteresis; sandboxed ARM64 OrbStack VM and manual networking checks;
safe actuator pilot, ARC integration.

MIT licensed.

## macOS guardrails (observe-only)

The macOS adapter now measures:

- Charging state, user idle time, screen sleep and CPU utilization (asynchronously)
- ProcessInfo thermal state via Hammerspoon
- VM swap I/O rate across 30-second samples
- macOS memory-pressure level via a bounded sysctl subprocess

Swap allocated historically is not treated as current swapping; only new swap
traffic is used for the high-capacity guard. The macOS memory-pressure sysctl
is not a public Apple API: if unavailable or unrecognized, high-capacity mode
fails closed. Serious/critical heat or memory warning stops eligibility.
Entering boost requires 2 minutes of stable qualified samples after the
host is already idle. A deterioration reduces the observed tier immediately.

This is not a performance guarantee. VM limits and workload admission are not
implemented; the UI reports *hypothetical* tiers only.
