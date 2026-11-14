"""Stateless JSON adapter API."""
import argparse
import json
import sys
from .policy import Signals, decide

parser = argparse.ArgumentParser(description="SpareCore dry-run capacity")
parser.add_argument("command", choices=["decide"])
parser.add_argument("--input", required=True, help="JSON signal object")
args = parser.parse_args()
try:
    data = json.loads(args.input)
    if type(data) is not dict:
        raise ValueError("Expected JSON object")
    signals = Signals(**data)
    result = decide(signals)
except (ValueError, TypeError) as exc:
    print(json.dumps({"error": str(exc)}), file=sys.stderr)
    sys.exit(2)
print(json.dumps({"tier": result.tier, "reason": result.reason, "applied": False}))
