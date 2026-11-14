"""Read-only JSON policy and onboarding CLI."""
import argparse
import json
import sys
from .policy import Signals, decide


def main(argv=None):
    parser = argparse.ArgumentParser(description="SpareCore: observe-only")
    parser.add_argument("command", choices=["decide", "doctor"])
    parser.add_argument("--input", help="JSON signals for decide")
    parser.add_argument("--macos-pressure", action="store_true",
                        help="Read macOS memory pressure when deciding")
    parser.add_argument("--json", action="store_true", help="Output doctor results as JSON")
    args = parser.parse_args(argv)

    if args.command == "doctor":
        from .doctor import report
        details = report()
        if args.json:
            print(json.dumps(details, indent=2))
        else:
            print("SpareCore doctor (read-only, observe-only)")
            for check in details["checks"]:
                print("[{:<11}] {:<23} {}".format(check["status"], check["name"], check["detail"]))
                if check["next_step"]:
                    print("              Next: {}".format(check["next_step"]))
            print(details["warning"])
        return 0

    if not args.input:
        parser.error("--input is required for decide")
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
        return 2
    print(json.dumps({"tier": result.tier, "reason": result.reason,
                      "applied": False, **extra}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
