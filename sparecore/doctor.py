"""Read-only onboarding checks. Do not install, log in, or start services."""
from dataclasses import asdict, dataclass
from pathlib import Path
import platform
import shutil


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    next_step: str = ""


def inspect_environment(system=None, home=None, find_executable=None):
    """No subprocesses, no file modifications, and no privileged operations."""
    system = platform.system() if system is None else system
    home = Path.home() if home is None else Path(home)
    find_executable = shutil.which if find_executable is None else find_executable
    checks = []
    if system != "Darwin":
        checks.append(Check("macOS", "unsupported", "The current menu adapter supports macOS only",
                            "Run on macOS or follow the project roadmap for other platforms"))
    else:
        checks.append(Check("macOS", "ok", "macOS detected"))
    py_exe = find_executable("python3")
    checks.append(Check("Python", "ok" if py_exe else "missing",
                        py_exe or "Python 3 not on PATH",
                        "" if py_exe else "Install a supported Python 3 runtime"))
    lima = find_executable("limactl")
    checks.append(Check("Lima (optional worker)", "ok" if lima else "optional",
                        lima or "Lima CLI not found",
                        "" if lima else "Install Lima for a full Linux VM k3s worker later"))
    orb = find_executable("orb")
    checks.append(Check("OrbStack (optional)", "ok" if orb else "optional",
                        orb or "OrbStack CLI not found",
                        "" if orb else "OrbStack is not required for the full-VM k3s backend"))
    hs = find_executable("hs")
    checks.append(Check("Hammerspoon", "ok" if hs else "missing",
                        hs or "Hammerspoon CLI not found",
                        "" if hs else "Install Hammerspoon and enable the CLI integration"))
    config = home / ".hammerspoon" / "init.lua"
    checks.append(Check("Menu configuration", "ok" if config.is_file() else "missing",
                        "File present (not parsed)" if config.is_file() else "No Hammerspoon init.lua",
                        "" if config.is_file() else "Follow the README menu integration guide"))
    ts = find_executable("tailscale")
    checks.append(Check("Tailscale (optional)", "ok" if ts else "optional",
                        ts or "Not installed on host PATH",
                        "Only needed later for private cluster connectivity" if not ts else ""))
    return checks


def report():
    return {"mode": "observe-only", "checks": [asdict(x) for x in inspect_environment()],
            "warning": "Checks do not verify whether a service is running or authenticate tailnet. No worker is started."}
