from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulator.catalog import build_catalog
from simulator.engine import IncidentSimulator


def materialize(root: Path | None = None) -> Path:
    base = root or Path(__file__).resolve().parent
    destination = base / "scenarios" / "catalog.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = [scenario.model_dump(mode="json") for scenario in build_catalog()]
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap the deterministic Sentinel simulator")
    parser.add_argument("--materialize", action="store_true", help="write the scenario catalog")
    parser.add_argument("--scenario", default="oom_killed_001", help="scenario to inject")
    args = parser.parse_args()
    if args.materialize:
        print(materialize())
    snapshot = IncidentSimulator().inject(args.scenario)
    print(
        json.dumps(
            {
                "scenario": snapshot.scenario.id,
                "points": len(snapshot.telemetry),
                "logs": len(snapshot.logs),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
