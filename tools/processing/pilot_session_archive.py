"""Create, verify, compare or extract a raw session archive."""

import argparse
from pathlib import Path

from fall_detection.storage.session_archive import create_archive, verify_archive
from fall_detection.storage import Recording


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("source", type=Path)
    create.add_argument("destination", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("archive", type=Path)
    extract = commands.add_parser("extract")
    extract.add_argument("archive", type=Path)
    extract.add_argument("destination", type=Path)
    compare = commands.add_parser("compare")
    compare.add_argument("archive", type=Path)
    compare.add_argument("source", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        result = create_archive(
            args.source,
            args.destination,
            progress=lambda index, total, path: print(
                f"{index}/{total} {path}", flush=True
            ),
        )
    elif args.command == "verify":
        result = verify_archive(args.archive)
    else:
        with Recording(args.archive) as recording:
            if args.command == "extract":
                print(recording.extract(args.destination))
            else:
                print(recording.compare_source(args.source))
        return
    print(
        f"Verified {len(result['files'])} original files and {len(result['tables'])} tables"
    )


if __name__ == "__main__":
    main()
