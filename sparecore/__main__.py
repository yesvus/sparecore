"""Stateless JSON adapter API."""
import argparse
import json
import sys
from .policy import Signals, decide

parser = argparse.ArgumentParser(description="SpareCore dry-run capacity")
parser.add_argument("command", choices=["decide"])
parser.add_argument("--input", required=True, help="JSON signal object")
parser.add_argument("--macos-pressure", action="store_true",
                    help="Read macOS system memory pressure; overrides memory_safe")
args = parser.parse_args()
try:
    data = json.loads(args.input)
    if type(data) is not dict:
        raise ValueError("Expected JSON object")
    extra = {}
    if args.macos_pressure:
        from .macos import memory_safe, pressure_level
        rate = data.pop("swap_io_mib_s", None)
        level = pressure_level()
        data["memory_safe"] = memory_safe(level, rate)
        extra = {"memory_pressure_level": level, "swap_io_mib_s": rate,
                 "memory_safe": data["memory_safe"]}
    signals = Signals(**data)
    result = decide(signals)
except (ValueError, TypeError) as exc:
    print(json.dumps({"error": str(exc)}), file=sys.stderr)
    sys.exit(2)
print(json.dumps({"tier": result.tier, "reason": result.reason,
                  "applied": False, **extra}))
