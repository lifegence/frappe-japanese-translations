#!/usr/bin/env python3
"""
validate-csv.py — Validate Frappe translation CSV files

Checks:
  - CSV format (proper quoting, column count)
  - Duplicate source strings
  - Placeholder consistency ({0}, {1}, etc.)
  - Empty translations
  - Encoding (UTF-8)

Usage:
  python3 scripts/validate-csv.py                    # All apps
  python3 scripts/validate-csv.py --app frappe        # Single app
  python3 scripts/validate-csv.py --fix               # Auto-fix duplicates
"""

import argparse
import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
TRANSLATIONS_DIR = REPO_DIR / "translations"

PLACEHOLDER_RE = re.compile(r"\{[\w.]+\}")


def validate_csv(app: str, csv_path: Path, fix: bool = False) -> dict:
    """Validate a single translation CSV file."""
    issues = {
        "errors": [],
        "warnings": [],
        "stats": {
            "total": 0,
            "translated": 0,
            "untranslated": 0,
            "duplicates": 0,
            "placeholder_mismatch": 0,
        },
    }

    if not csv_path.exists():
        issues["errors"].append(f"File not found: {csv_path}")
        return issues

    # Check encoding
    try:
        content = csv_path.read_bytes()
        content.decode("utf-8")
    except UnicodeDecodeError as e:
        issues["errors"].append(f"Encoding error (not valid UTF-8): {e}")
        return issues

    # Parse CSV
    rows = []
    source_counts = Counter()
    seen_sources = {}

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for line_num, row in enumerate(reader, 1):
                if len(row) < 2:
                    if len(row) == 1 and not row[0].strip():
                        continue  # empty line
                    issues["warnings"].append(
                        f"Line {line_num}: insufficient columns ({len(row)})"
                    )
                    continue

                source = row[0].strip()
                target = row[1].strip()
                context = row[2].strip() if len(row) > 2 else ""

                if not source:
                    continue

                issues["stats"]["total"] += 1
                rows.append((source, target, context, line_num))

                # Check translation status
                if source == target or not target:
                    issues["stats"]["untranslated"] += 1
                else:
                    issues["stats"]["translated"] += 1

                # Check duplicates
                source_counts[source] += 1
                if source in seen_sources:
                    issues["stats"]["duplicates"] += 1
                    prev_line = seen_sources[source]
                    issues["warnings"].append(
                        f"Line {line_num}: duplicate source (first at line {prev_line}): "
                        f"{source[:60]}{'...' if len(source) > 60 else ''}"
                    )
                else:
                    seen_sources[source] = line_num

                # Check placeholder consistency
                if target and source != target:
                    src_placeholders = sorted(PLACEHOLDER_RE.findall(source))
                    tgt_placeholders = sorted(PLACEHOLDER_RE.findall(target))
                    if src_placeholders != tgt_placeholders:
                        issues["stats"]["placeholder_mismatch"] += 1
                        issues["warnings"].append(
                            f"Line {line_num}: placeholder mismatch: "
                            f"source={src_placeholders} target={tgt_placeholders}"
                        )

    except csv.Error as e:
        issues["errors"].append(f"CSV parse error: {e}")
        return issues

    # Auto-fix duplicates
    if fix and issues["stats"]["duplicates"] > 0:
        deduplicated = {}
        for source, target, context, _ in rows:
            if source not in deduplicated or (
                target and source != target and deduplicated[source][0] == source
            ):
                deduplicated[source] = (target, context)

        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            for source, (target, context) in deduplicated.items():
                writer.writerow([source, target, context])

        removed = issues["stats"]["duplicates"]
        issues["warnings"].append(f"Fixed: removed {removed} duplicate entries")

    return issues


def main():
    parser = argparse.ArgumentParser(description="Validate Frappe translation CSV files")
    parser.add_argument("--app", help="Validate only this app")
    parser.add_argument(
        "--fix", action="store_true", help="Auto-fix issues (remove duplicates)"
    )
    args = parser.parse_args()

    apps = []
    if args.app:
        apps = [args.app]
    else:
        apps = sorted(
            d.name
            for d in TRANSLATIONS_DIR.iterdir()
            if d.is_dir() and (d / "ja.csv").exists()
        )

    if not apps:
        print("No translation files found.")
        sys.exit(1)

    total_errors = 0
    total_warnings = 0

    for app in apps:
        csv_path = TRANSLATIONS_DIR / app / "ja.csv"
        result = validate_csv(app, csv_path, fix=args.fix)

        errors = len(result["errors"])
        warnings = len(result["warnings"])
        stats = result["stats"]
        total_errors += errors
        total_warnings += warnings

        # Status icon
        if errors > 0:
            icon = "FAIL"
        elif warnings > 0:
            icon = "WARN"
        else:
            icon = " OK "

        pct = (
            (stats["translated"] / stats["total"] * 100) if stats["total"] > 0 else 0
        )
        print(
            f"[{icon}] {app:<15} "
            f"entries={stats['total']:>6,}  "
            f"translated={stats['translated']:>6,}  "
            f"coverage={pct:5.1f}%  "
            f"dupes={stats['duplicates']:>3}  "
            f"placeholders={stats['placeholder_mismatch']:>3}"
        )

        for err in result["errors"]:
            print(f"       ERROR: {err}")
        for warn in result["warnings"][:10]:
            print(f"       WARN:  {warn}")
        if warnings > 10:
            print(f"       ... and {warnings - 10} more warnings")

    print()
    if total_errors > 0:
        print(f"FAILED: {total_errors} errors, {total_warnings} warnings")
        sys.exit(1)
    elif total_warnings > 0:
        print(f"PASSED with {total_warnings} warnings")
    else:
        print("PASSED: all files valid")


if __name__ == "__main__":
    main()
