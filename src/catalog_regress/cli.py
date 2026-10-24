"""Command-line entry point."""

from __future__ import annotations

import argparse
import json

from . import __version__
from .core import DEFAULT_MAX_BYTES, CatalogError, compare_catalogs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate loss of usable gettext translations.")
    parser.add_argument("baseline", help="UTF-8 PO catalog before the update")
    parser.add_argument("candidate", help="UTF-8 PO catalog after the update")
    parser.add_argument(
        "--allow-removed",
        action="store_true",
        help="Permit protected entries that are missing or obsolete",
    )
    parser.add_argument("--max-regressions", type=int, default=0, metavar="N")
    parser.add_argument("--max-findings", type=int, default=50, metavar="N")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        metavar="N",
        help="Per-input byte limit (default: 16777216)",
    )
    parser.add_argument("--json", action="store_true", help="Emit a content-free JSON receipt")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        result = compare_catalogs(
            args.baseline,
            args.candidate,
            allow_removed=args.allow_removed,
            max_regressions=args.max_regressions,
            max_findings=args.max_findings,
            max_bytes=args.max_bytes,
        )
    except CatalogError as exc:
        result = {
            "schema_version": 1,
            "status": "error",
            "error": {"code": exc.code, "side": exc.side},
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print(f"ERROR {exc.side}: {exc.code}")
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print(
            f"{result['status'].upper()}: {result['regression_count']} regression(s), "
            f"{result['protected']} protected, budget {result['budget']}"
        )
        for finding in result["findings"]:
            print(
                f"  {finding['reason']}: baseline line {finding['baseline_line']}, "
                f"candidate line {finding['candidate_line']}"
            )
        if result["findings_truncated"]:
            print("  Additional findings omitted; counts remain complete.")
    return 0 if result["status"] == "pass" else 1
