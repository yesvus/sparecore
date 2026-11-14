"""macOS memory-pressure adapter. All failures are treated as unknown.

The sysctl is macOS-specific and is not a public stable Apple API, so the
adapter must fail closed when a future system no longer exposes it.
"""
import subprocess
from typing import Optional


def pressure_level() -> Optional[int]:
    try:
        p = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            capture_output=True, text=True, timeout=1, check=True,
        )
        level = int(p.stdout.strip())
        return level if level in (1, 2, 4) else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def memory_safe(level: Optional[int], swap_io_mib_s: Optional[float]) -> Optional[bool]:
    """Normal pressure AND low swap I/O required for boost.

    1 = normal, 2 = warning, 4 = critical. Do not confuse with XNU's
    internal five-state enumeration.
    """
    if level in (2, 4):
        return False
    if level != 1 or swap_io_mib_s is None:
        return None
    if not 0 <= swap_io_mib_s < float("inf"):
        return None
    return swap_io_mib_s <= 1.0
