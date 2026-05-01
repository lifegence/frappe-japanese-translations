#!/usr/bin/env python3
"""csv-to-po.py — Convert Frappe legacy CSV translations to gettext PO format.

Uses the app's main.pot as the canonical source of msgids and fills msgstr
from the CSV target column. Entries where target equals source (or differs
only by surrounding whitespace) are treated as untranslated, so they appear
as gaps in Crowdin rather than fake translations.

Examples:
    # Convert frappe ja.csv against the upstream pot
    csv-to-po.py \\
        --pot ~/work/frappe/frappe/locale/main.pot \\
        --csv translations/frappe/ja.csv \\
        --output translations/frappe/ja.po

    # Also emit a sub-POT containing only the untranslated entries,
    # which can be fed into translate-ai.py for batch AI translation.
    csv-to-po.py --pot ... --csv ... --gap-pot _work/gaps/frappe.pot

    # Auto-fill from glossary on exact msgid matches.
    csv-to-po.py --pot ... --csv ... --apply-glossary glossary/glossary.csv

Requires: polib (pip install polib)
"""

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import polib

PLACEHOLDER_RE = re.compile(r"\{[\w.]*\}|%\([\w.]+\)s|%[sd]")

JA_HEADERS = {
    "Project-Id-Version": "frappe",
    "Report-Msgid-Bugs-To": "developers@frappe.io",
    "Last-Translator": "developers@frappe.io",
    "Language-Team": "Japanese",
    "Language": "ja",
    "MIME-Version": "1.0",
    "Content-Type": "text/plain; charset=UTF-8",
    "Content-Transfer-Encoding": "8bit",
    "Plural-Forms": "nplurals=1; plural=0;",
    "Generated-By": "csv-to-po.py",
}


@dataclass
class Stats:
    pot_entries: int = 0
    translated: int = 0
    untranslated: int = 0
    glossary_filled: int = 0
    csv_unmatched: list = field(default_factory=list)
    csv_whitespace_only: int = 0
    placeholder_mismatches: list = field(default_factory=list)


def load_csv(path: Path) -> dict[tuple[str, str], str]:
    """Return {(source, context): target} where target is meaningfully translated."""
    table: dict[tuple[str, str], str] = {}
    duplicates = []
    with path.open(encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or len(row) < 2:
                continue
            source, target = row[0], row[1]
            context = row[2] if len(row) >= 3 else ""
            key = (source, context)
            if key in table and table[key] != target:
                duplicates.append(source[:60])
            table[key] = target
    if duplicates:
        print(f"  warn: {len(duplicates)} duplicate CSV keys (last value kept)", file=sys.stderr)
    return table


def load_glossary(path: Path) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    glossary = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            src = (row.get("source") or "").strip()
            tgt = (row.get("target") or "").strip()
            if src and tgt:
                glossary[src] = tgt
    return glossary


def is_real_translation(source: str, target: str) -> tuple[bool, bool]:
    """Return (is_translated, is_whitespace_only_diff)."""
    if not target.strip():
        return False, False
    if source == target:
        return False, False
    if source.strip() == target.strip():
        return False, True
    return True, False


def placeholders_match(source: str, target: str) -> bool:
    return sorted(PLACEHOLDER_RE.findall(source)) == sorted(PLACEHOLDER_RE.findall(target))


def convert(
    pot_path: Path,
    csv_path: Path,
    out_path: Path,
    gap_pot_path: Path | None,
    glossary_path: Path | None,
    strict_placeholders: bool,
) -> Stats:
    pot = polib.pofile(str(pot_path))
    csv_table = load_csv(csv_path)
    glossary = load_glossary(glossary_path) if glossary_path else {}
    stats = Stats(pot_entries=len(pot))

    used_keys: set[tuple[str, str]] = set()
    out_po = polib.POFile()
    out_po.metadata = JA_HEADERS.copy()
    out_po.metadata["PO-Revision-Date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M+0000")
    if "X-Crowdin-Project" in (pot.metadata or {}):
        out_po.metadata["X-Crowdin-Project"] = pot.metadata["X-Crowdin-Project"]

    gap_pot = polib.POFile() if gap_pot_path else None
    if gap_pot is not None:
        gap_pot.metadata = (pot.metadata or {}).copy()
        gap_pot.metadata["Language"] = "ja"

    for entry in pot:
        if entry.obsolete:
            continue
        key = (entry.msgid, entry.msgctxt or "")
        target = csv_table.get(key)
        msgstr = ""

        if target is not None:
            used_keys.add(key)
            real, ws_only = is_real_translation(entry.msgid, target)
            if real:
                msgstr = target
                if not placeholders_match(entry.msgid, target):
                    stats.placeholder_mismatches.append(entry.msgid[:80])
            elif ws_only:
                stats.csv_whitespace_only += 1

        if not msgstr and entry.msgid in glossary:
            msgstr = glossary[entry.msgid]
            stats.glossary_filled += 1

        new_entry = polib.POEntry(
            msgid=entry.msgid,
            msgstr=msgstr,
            msgctxt=entry.msgctxt,
            occurrences=entry.occurrences,
            comment=entry.comment,
            tcomment=entry.tcomment,
            flags=list(entry.flags),
        )
        out_po.append(new_entry)
        if msgstr:
            stats.translated += 1
        else:
            stats.untranslated += 1
            if gap_pot is not None:
                gap_pot.append(polib.POEntry(
                    msgid=entry.msgid,
                    msgctxt=entry.msgctxt,
                    occurrences=entry.occurrences,
                    comment=entry.comment,
                ))

    stats.csv_unmatched = sorted(k[0][:80] for k in csv_table.keys() - used_keys)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_po.save(str(out_path))
    if gap_pot is not None:
        gap_pot_path.parent.mkdir(parents=True, exist_ok=True)
        gap_pot.save(str(gap_pot_path))

    if strict_placeholders and stats.placeholder_mismatches:
        raise SystemExit(
            f"strict-placeholders: {len(stats.placeholder_mismatches)} mismatch(es); aborted"
        )
    return stats


def print_report(stats: Stats, app: str) -> None:
    coverage = (stats.translated / stats.pot_entries * 100) if stats.pot_entries else 0
    print(f"== {app} ==")
    print(f"  pot entries        : {stats.pot_entries}")
    print(f"  translated         : {stats.translated}  ({coverage:.1f}%)")
    print(f"  untranslated (gap) : {stats.untranslated}")
    if stats.glossary_filled:
        print(f"  glossary auto-fill : {stats.glossary_filled}")
    if stats.csv_whitespace_only:
        print(f"  csv ws-only diffs  : {stats.csv_whitespace_only}  (treated as gap)")
    if stats.csv_unmatched:
        print(f"  csv unmatched      : {len(stats.csv_unmatched)}  (obsolete in pot)")
    if stats.placeholder_mismatches:
        print(f"  placeholder warns  : {len(stats.placeholder_mismatches)}")
        for s in stats.placeholder_mismatches[:5]:
            print(f"    - {s!r}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pot", required=True, type=Path, help="Source main.pot file")
    p.add_argument("--csv", required=True, type=Path, help="Frappe legacy ja.csv")
    p.add_argument("--output", type=Path, help="Output .po path (default: <csv-dir>/ja.po)")
    p.add_argument("--gap-pot", type=Path, help="Write sub-POT of untranslated entries")
    p.add_argument("--apply-glossary", type=Path, help="Auto-fill from glossary CSV on exact msgid match")
    p.add_argument("--strict-placeholders", action="store_true", help="Fail on placeholder mismatches")
    p.add_argument("--app", default=None, help="Label used in the report (default: csv parent dir)")
    args = p.parse_args()

    if not args.pot.exists():
        p.error(f"pot not found: {args.pot}")
    if not args.csv.exists():
        p.error(f"csv not found: {args.csv}")

    out_path = args.output or args.csv.with_name("ja.po")
    app = args.app or args.csv.parent.name

    stats = convert(
        pot_path=args.pot,
        csv_path=args.csv,
        out_path=out_path,
        gap_pot_path=args.gap_pot,
        glossary_path=args.apply_glossary,
        strict_placeholders=args.strict_placeholders,
    )
    print_report(stats, app)
    print(f"  -> {out_path}")
    if args.gap_pot:
        print(f"  -> {args.gap_pot}  (gap pot)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
