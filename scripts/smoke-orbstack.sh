#!/usr/bin/env bash
# Read-only guest diagnostics. Requires an EXISTING VM and never joins k3s.
# Intended for an Apple Silicon Mac with Hammerspoon + OrbStack.
set -euo pipefail
machine=sparecore-pilot
if [[ $# -gt 0 ]]; then machine="$1"; fi
command -v orb >/dev/null || { echo "Missing OrbStack CLI"; exit 2; }
command -v pmset >/dev/null || { echo "macOS only"; exit 2; }

power=$(pmset -g batt | head -1)
if [[ "$power" != *"AC Power"* ]]; then
    echo "NO-GO: not connected to power"; exit 3
fi
pressure=$(/usr/sbin/sysctl -n kern.memorystatus_vm_pressure_level)
if [[ "$pressure" != "1" ]]; then
    echo "NO-GO: macOS memory pressure is not nominal"; exit 3
fi
if [[ ! -x /opt/homebrew/bin/hs ]]; then
    echo "NO-GO: Hammerspoon CLI unavailable"; exit 3
fi
tier=$(/opt/homebrew/bin/hs -c 'return sparecore.status()' </dev/null | awk 'NR==1 {print $1}')
if [[ "$tier" != "light" && "$tier" != "boost" ]]; then
    echo "NO-GO: SpareCore policy is $tier"; exit 3
fi
thermal=$(/opt/homebrew/bin/hs -c 'return hs.host.thermalState()' </dev/null | head -1)
if [[ "$thermal" != "nominal" && "$thermal" != "fair" ]]; then
    echo "NO-GO: thermal state is $thermal"; exit 3
fi

# Fail if the existing guest is unexpectedly privileged or too large.
# No create, no secrets, no k3s join.
orb info -f json "$machine" | /usr/bin/python3 -c '
import json,sys
info=json.load(sys.stdin)["record"]["config"]
assert info["isolated"] is True, "not an isolated machine"
assert info["forward_ssh_agent"] is False, "SSH agent forwarding enabled"
assert info["cpu_limit"] <= 2, "CPU limit too high"
assert info["memory_limit_mib"] <= 2048, "memory limit too high"
assert info["disk_limit_bytes"] <= 20 * 1024**3, "disk limit too high"
'
# Never take over an existing user's running machine.
state=$(orb info -f json "$machine" | /usr/bin/python3 -c 'import json,sys;print(json.load(sys.stdin)["record"]["state"])')
if [[ "$state" != "stopped" ]]; then
    echo "NO-GO: machine is already $state"; exit 3
fi
echo "Safe preflight: AC, thermal, memory, policy and OrbStack limits"
# Install cleanup first, so even a partially successful boot gets stopped.
trap 'orb stop "$machine" >/dev/null 2>&1 || true; echo "Pilot guest stopped"' EXIT
orb start "$machine"

# OrbStack consumes the host's input stream by default. Explicitly detach stdin.
echo "Guest kernel, cgroups and network:"
orb run -m "$machine" bash -lc '
set -eu
uname -a
test "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs
cat /sys/fs/cgroup/cgroup.controllers
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/memory.max
test "$(cat /sys/fs/cgroup/memory.max)" -le 2147483648
awk "{exit !(\$1 <= 200000 && \$2 == 100000)}" /sys/fs/cgroup/cpu.max
test -c /dev/net/tun && echo TUN_PRESENT
ip route | head -5
' </dev/null
echo "Read-only guest smoke successful. No Kubernetes changes."
