"""Pure capacity policy: no Kubernetes leases, no device side effects."""
from dataclasses import dataclass
from math import isfinite
from typing import Optional


@dataclass(frozen=True)
class Signals:
    on_ac: bool
    idle_seconds: float
    displays_asleep: bool
    cpu_busy_percent: Optional[float]
    memory_safe: Optional[bool] = None
    mode: str = "auto"
    thermal_state: Optional[str] = None

    def __post_init__(self):
        if type(self.on_ac) is not bool or type(self.displays_asleep) is not bool:
            raise ValueError("invalid power or display state")
        if self.mode not in ("auto", "on", "off"):
            raise ValueError("invalid mode")
        if type(self.idle_seconds) not in (int, float) or not isfinite(self.idle_seconds) or not 0 <= self.idle_seconds <= 864000:
            raise ValueError("invalid idle time")
        if self.cpu_busy_percent is not None and (type(self.cpu_busy_percent) not in (int, float) or not isfinite(self.cpu_busy_percent) or not 0 <= self.cpu_busy_percent <= 100):
            raise ValueError("invalid CPU percentage")
        if self.memory_safe is not None and type(self.memory_safe) is not bool:
            raise ValueError("invalid memory safety state")
        if self.thermal_state not in (None, "nominal", "fair", "serious", "critical", "unknown"):
            raise ValueError("invalid thermal state")


@dataclass(frozen=True)
class Decision:
    tier: str
    reason: str


def decide(s: Signals) -> Decision:
    if not s.on_ac:
        return Decision("off", "AC power required")
    if s.mode == "off":
        return Decision("off", "Manually disabled")
    if s.cpu_busy_percent is None:
        return Decision("off", "CPU unknown")
    if s.memory_safe is False:
        return Decision("off", "Memory pressure or swap activity unsafe")
    if s.thermal_state in ("serious", "critical"):
        return Decision("off", "System thermal state elevated")
    if s.cpu_busy_percent >= 60:
        return Decision("off", "CPU busy")
    if (s.displays_asleep or s.idle_seconds >= 300) and s.cpu_busy_percent < 40 and s.memory_safe is True and s.thermal_state == "nominal":
        return Decision("boost", "Idle on AC with measured headroom")
    return Decision("light", "Owner-priority light capacity")
