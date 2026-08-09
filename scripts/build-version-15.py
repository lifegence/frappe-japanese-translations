#!/usr/bin/env python3
"""Build the version-15 translation set for frappe / erpnext.

Unlike version-16, the v15 branches ship Japanese as the legacy CSV
(`{app}/translations/ja.csv`); erpnext v15 has no `locale/` directory at all.
So the v15 set is CSV-first and is built by merging upstream v15 with this
repo's develop-tracking PO.

Merge policy — additive, no regression against the shipped product:

  base      upstream `{app}/translations/ja.csv` at the version-15 branch
  add       msgids the upstream CSV has no entry for, taken from ja.po
  override  only where the upstream entry is objectively broken and the PO
            entry is not — a source word left untranslated, or placeholders
            ({0}, markup) that no longer match the source. Small and reviewable.
  keep      every other overlapping msgid stays at the upstream value

Rationale: the PO tracks develop, so on shared msgids neither side is
systematically better (measured: for frappe, PO entries that differ from
upstream leave English in 50% of cases against upstream's 6%). The gain is in
coverage — stock v15 frappe translates only 60% of its own POT.

Usage:
    python3 scripts/build-version-15.py [--check]

`--check` reports the numbers without writing files.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import subprocess
import sys
import tempfile

import polib

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKOUTS = os.path.expanduser("~/work")
BRANCH = "origin/version-15"
APPS = ("frappe", "erpnext")

LATIN = re.compile(r"[A-Za-z]{2,}")
PLACEHOLDER = re.compile(r"\{[^}]*\}|<[^>]+>|%\w")


def key_of(msgid: str, context: str | None) -> tuple[str, str]:
    """Frappe keys a translation by source string plus optional context.

    Kept as a tuple rather than a joined string: source strings routinely
    contain ":" themselves, so any separator would be ambiguous.
    """
    return (msgid, context or "")


def git_show(repo: str, path: str) -> str:
    result = subprocess.run(
        ["git", "-C", os.path.join(CHECKOUTS, repo), "show", f"{BRANCH}:{path}"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        sys.exit(f"cannot read {BRANCH}:{path} from {repo}: {result.stderr.strip()}")
    return result.stdout


def read_csv(text: str) -> dict[tuple[str, str], str]:
    """(source, context) -> translation"""
    entries = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2 or not row[0]:
            continue
        entries[key_of(row[0], row[2] if len(row) > 2 else "")] = row[1]
    return entries


def read_po(path: str) -> dict[tuple[str, str], str]:
    entries = {}
    for entry in polib.pofile(path):
        if not entry.msgid or not entry.msgstr:
            continue
        entries[key_of(entry.msgid, entry.msgctxt)] = entry.msgstr
    return entries


def read_pot(repo: str, path: str) -> set[tuple[str, str]] | None:
    result = subprocess.run(
        ["git", "-C", os.path.join(CHECKOUTS, repo), "show", f"{BRANCH}:{path}"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".pot", delete=False, encoding="utf-8") as handle:
        handle.write(result.stdout)
        temp = handle.name
    try:
        return {key_of(e.msgid, e.msgctxt) for e in polib.pofile(temp) if e.msgid}
    finally:
        os.unlink(temp)


def leaves_english(translation: str, source: str) -> bool:
    """True when the translation still carries a word from the source string."""
    strip = lambda s: PLACEHOLDER.sub("", s)
    in_translation = {w.lower() for w in LATIN.findall(strip(translation))}
    in_source = {w.lower() for w in LATIN.findall(strip(source))}
    return bool(in_translation & in_source)


def breaks_placeholders(translation: str, source: str) -> bool:
    """True when the translation does not carry the source's {0}-style slots."""
    return set(PLACEHOLDER.findall(source)) != set(PLACEHOLDER.findall(translation))


def repairs(candidate: str, current: str, source: str) -> bool:
    """True when `candidate` fixes a defect in `current` without adding one.

    The two defects are judged independently: a broken {0} slot is a functional
    bug and is worth taking the PO entry for even if that entry keeps an English
    proper noun (DocType, BOM) that the leak heuristic cannot tell apart from an
    untranslated word.
    """
    if breaks_placeholders(current, source) and not breaks_placeholders(candidate, source):
        return True
    if leaves_english(current, source) and not leaves_english(candidate, source):
        return not breaks_placeholders(candidate, source)
    return False


def build(app: str, check_only: bool) -> None:
    upstream = read_csv(git_show(app, f"{app}/translations/ja.csv"))
    develop = read_po(os.path.join(REPO_ROOT, "translations", app, "ja.po"))

    merged = dict(upstream)
    added = overridden = 0

    for key, translation in develop.items():
        source = key[0]
        if not source.strip():
            # whitespace-only msgid: not a real UI string
            merged.pop(key, None)
            continue
        if key not in upstream:
            merged[key] = translation
            added += 1
        else:
            current = upstream[key]
            if current != translation and repairs(translation, current, source):
                merged[key] = translation
                overridden += 1

    print(f"=== {app}")
    print(f"  upstream v15        : {len(upstream):>6}")
    print(f"  + PO で穴埋め        : {added:>6}")
    print(f"  + 欠陥訳の差し替え   : {overridden:>6}")
    print(f"  = version-15 set    : {len(merged):>6}")

    pot = read_pot(app, f"{app}/locale/main.pot")
    if pot:
        before = len(pot & set(upstream))
        after = len(pot & set(merged))
        print(f"  POT {len(pot)} 件に対する網羅率: {before * 100 // len(pot)}% -> {after * 100 // len(pot)}%")
    else:
        print("  POT なし（網羅率は実機の bench get-untranslated で測る）")

    if check_only:
        return

    out_dir = os.path.join(REPO_ROOT, "translations", app, "version-15")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "ja.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        for source, context in sorted(merged):
            writer.writerow([source, merged[(source, context)], context])
    print(f"  -> {os.path.relpath(out_path, REPO_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report numbers without writing")
    args = parser.parse_args()
    for app in APPS:
        build(app, args.check)


if __name__ == "__main__":
    main()
