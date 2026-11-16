#!/usr/bin/env bash
# Interactive registration for an EXISTING stopped Lima full VM.
# Never touches Kubernetes, runs agents, or copies tailnet credentials.
set -euo pipefail
if [[ $# -eq 1 && "$1" == "--help" ]]; then
  echo "Usage: bash scripts/enroll-lima-tailscale.sh <existing-lima-vm-name>"
  echo "Enroll only the selected stopped VM with explicit browser login."
  exit 0
fi
[[ $# -eq 1 ]] || { echo "Specify exactly one existing Lima VM"; exit 2; }
name=$1
# Lima permits names that the Tailscale --hostname option rejects.
# Enrollment is intentionally more restrictive than read-only inspection.
[[ "$name" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] || {
  echo "Invalid VM name"; exit 2;
}
[[ -t 0 ]] || { echo "Run in an interactive Mac Terminal"; exit 2; }
command -v limactl >/dev/null || { echo "Lima CLI not found"; exit 2; }
command -v pmset >/dev/null || { echo "macOS required"; exit 2; }
[[ -x /opt/homebrew/bin/hs ]] || { echo "Hammerspoon CLI required"; exit 2; }

power=$(pmset -g batt | head -1)
[[ "$power" == *"AC Power"* ]] || { echo "Mac not connected to power"; exit 3; }
memory=$(/usr/sbin/sysctl -n kern.memorystatus_vm_pressure_level)
[[ "$memory" == 1 ]] || { echo "Mac memory pressure elevated"; exit 3; }
tier=$(/opt/homebrew/bin/hs -c 'return sparecore.status()' </dev/null | awk 'NR==1{print $1}')
[[ "$tier" == light || "$tier" == boost ]] || { echo "SpareCore is unavailable"; exit 3; }
thermal=$(/opt/homebrew/bin/hs -c 'return hs.host.thermalState()' </dev/null | head -1)
[[ "$thermal" == nominal ]] || { echo "Mac thermal state elevated"; exit 3; }

# Inspect existing VM only; creation is out of scope and user-owned VMs
# must not be accidentally stopped, recreated or modified.
limactl list --json | /usr/bin/python3 -c '
import json,sys
v=[json.loads(line) for line in sys.stdin if line.strip()]
m=[x for x in v if x.get("name")==sys.argv[1]]
assert len(m)==1, "Expected exactly one selected Lima VM"
x=m[0]
cfg=x.get("config",{})
assert x.get("status")=="Stopped", "VM already running"
assert x.get("vmType")=="vz" and x.get("arch")=="aarch64"
assert x.get("cpus")<=2 and x.get("memory")<=2*1024**3
assert x.get("disk")<=20*1024**3
assert cfg.get("plain") is True, "Plain mode required"
assert cfg.get("networkOpts",{}).get("hostLoopback") is False, "Host loopback must be disabled"
assert not cfg.get("mounts"), "Host mounts are not allowed"
assert not cfg.get("ssh",{}).get("forwardAgent", False)
print("Lima VZ VM settings verified")
' "$name"
echo "This enrolls a DISTINCT full Linux VM. Existing Mac/OrbStack tailnet IDs are untouched."
echo "No k3s or CI jobs will be started."
read -r -p "Type ENROLL to continue: " approval
[[ "$approval" == ENROLL ]] || { echo "Canceled"; exit 1; }
trap 'limactl stop "$name" >/dev/null 2>&1 || true; echo "Lima VM stopped"' EXIT
limactl start --tty=false --timeout=70s "$name"
echo "Approve the Tailscale browser login URL shown by the official client."
limactl shell "$name" sudo tailscale up --hostname="$name"
limactl shell "$name" sudo tailscale status --json | /usr/bin/python3 -c '
import json,sys
s=json.load(sys.stdin)
assert s.get("BackendState")=="Running", "Tailnet enrollment incomplete"
print("Guest Tailscale registration successful.")
print("Guest IPs:",", ".join(s.get("Self",{}).get("TailscaleIPs",[])))
'
echo "No k3s join attempted."
