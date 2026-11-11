"""Migrate closed session directories to verified raw archives, retaining sources."""

import argparse
import json
from pathlib import Path

from fall_detection.storage import Recording, create_archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sessions", type=Path)
    args = parser.parse_args()
    report = args.sessions / "archive-migration.jsonl"
    with report.open("a", encoding="utf-8", buffering=1) as log:
        for source in sorted(p.parent for p in args.sessions.glob("*/session.json")):
            destination = source.with_suffix(".zip")
            print(f"Migrating {source.name}", flush=True)
            if not destination.exists():
                create_archive(
                    source,
                    destination,
                    progress=lambda n, total, path: (
                        print(f"  {n}/{total}", flush=True) if n % 500 == 0 else None
                    ),
                )
            with Recording(destination) as recording:
                compared = recording.compare_source(source)
            entry = {
                "session": source.name,
                "archive": str(destination),
                "status": "verified",
                **compared,
                "archive_bytes": destination.stat().st_size,
            }
            log.write(json.dumps(entry) + "\n")
            print(json.dumps(entry), flush=True)


if __name__ == "__main__":
    main()
