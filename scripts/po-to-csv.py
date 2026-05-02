#!/usr/bin/env python3
"""po-to-csv.py — Sync gettext PO into Frappe legacy CSV for bench deployment.

The PO file is the source of truth (matches Crowdin and upstream POT). The CSV
is the deployable form consumed by `scripts/deploy.sh` and the Frappe bench's
`apps/{app}/{app}/translations/{lang}.csv` loader. Run this after every
translate-po / fixup-po pass to bring the deployable CSV to the same coverage
as the PO.

Output format: standard Frappe CSV, three columns (source, target, context),
sorted by source. Untranslated entries are omitted by default; pass
--include-empty to emit `source,source,context` placeholder rows that match
the historical pre-Crowdin file shape.

Usage:
    po-to-csv.py --po translations/frappe/ja.po --csv translations/frappe/ja.csv
    po-to-csv.py --po ... --csv ... --include-empty   # legacy file shape
"""

import argparse
import csv
import sys
from pathlib import Path

import polib


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--po", required=True, type=Path)
    p.add_argument("--csv", required=True, type=Path)
    p.add_argument("--include-empty", action="store_true",
                   help="Emit source,source,ctx rows for untranslated entries (legacy shape)")
    args = p.parse_args()

    if not args.po.exists():
        p.error(f"po not found: {args.po}")

    po = polib.pofile(str(args.po))
    rows: list[tuple[str, str, str]] = []
    translated = 0
    placeholders = 0
    for e in po:
        if e.obsolete:
            continue
        ctx = e.msgctxt or ""
        if e.msgstr.strip():
            rows.append((e.msgid, e.msgstr, ctx))
            translated += 1
        elif args.include_empty:
            rows.append((e.msgid, e.msgid, ctx))
            placeholders += 1

    rows.sort(key=lambda r: (r[0], r[2]))

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        for r in rows:
            writer.writerow(r)

    msg = f"[po-to-csv] {args.csv.name}: translated={translated}"
    if args.include_empty:
        msg += f" placeholders={placeholders}"
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
