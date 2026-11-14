#!/usr/bin/env bash
# Interactive, manual Tailnet registration for an EXISTING isolated OrbStack guest.
# Does not create the VM, install packages, touch Kubernetes or save keys in Git.
set -euo pipefail

if [[ $# -gt 0 && "$1" == "--help" ]]; then
    cat <<'TXT'
Usage: bash scripts/enroll-guest-tailscale.sh [machine-name]
Requires macOS, an existing stopped isolated OrbStack machine with Tailscale
installed, AC power, and an eligible SpareCore menu state.
Asks for explicit consent, displays the official browser login URL, verifies
the guest tailnet IP, then stops the temporary guest. No k3s join occurs.
TXT
    exit 0
fi

machine=sparecore-pilot
if [[ $# -gt 0 ]]; then machine="$1"; fi
if [[ ! "$machine" =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{0,60}$ ]]; then
    echo "Invalid machine name"; exit 2
fi
command -v orb >/dev/null || { echo "Missing OrbStack CLI"; exit 2; }
command -v pmset >/dev/null || { echo "macOS is required"; exit 2; }
command -v python3 >/dev/null || { echo "Python 3 required"; exit 2; }
if [[ ! -t 0 ]]; then
    echo "This authorization step must run in your interactive Terminal"; exit 2
fi
if [[ ! -x /opt/homebrew/bin/hs ]]; then
    echo "SpareCore/Hammerspoon CLI unavailable"; exit 3
fi

power=$(pmset -g batt | head -1)
if [[ "$power" != *"AC Power"* ]]; then
    echo "NO-GO: the Mac must be plugged in"; exit 3
fi
pressure=$(/usr/sbin/sysctl -n kern.memorystatus_vm_pressure_level)
if [[ "$pressure" != 1 ]]; then
    echo "NO-GO: macOS memory pressure is not nominal"; exit 3
fi
tier=$(/opt/homebrew/bin/hs -c 'return sparecore.status()' </dev/null | awk 'NR==1{print $1}')
if [[ "$tier" != "light" && "$tier" != "boost" ]]; then
    echo "NO-GO: SpareCore policy is $tier"; exit 3
fi

# Check exact resource limits and the pre-existing stopped state before starting.
orb info -f json "$machine" | python3 -c '
import json,sys
d=json.load(sys.stdin)["record"]
c=d["config"]
assert d["state"] == "stopped", "VM already active; refusing to take ownership"
assert c["isolated"] is True and c["forward_ssh_agent"] is False
assert c["cpu_limit"] <= 2 and c["memory_limit_mib"] <= 2048
assert c["disk_limit_bytes"] <= 20 * 1024**3
'

echo "This connects the isolated guest ($machine) to your private Tailscale network."
echo "You will see an official Tailscale browser login URL to approve the device."
echo "No kubelet, production Pod, token file or GitHub runner will be installed."
read -r -p "Type ENROLL to continue: " consent
if [[ "$consent" != "ENROLL" ]]; then
    echo "Canceled; no VM started"; exit 1
fi

# Do not leave the VM running if login fails, is interrupted or the user
# closes the Terminal. This is a manual enrollment step, not a daemon.
trap 'orb stop "$machine" >/dev/null 2>&1 || true; echo "Temporary guest stopped"' EXIT
orb start "$machine"
echo "Open the login URL shown below in your browser; approve only this guest."
echo "Ctrl-C cancels enrollment and stops the VM."
orb run -m "$machine" sudo -n tailscale up --hostname="$machine" </dev/null

echo "Guest tailnet IPv4:"
orb run -m "$machine" tailscale ip -4 </dev/null
echo "Registration complete. VM will now stop until a separate pilot is approved."
