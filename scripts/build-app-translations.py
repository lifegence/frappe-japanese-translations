#!/usr/bin/env python3
"""Build the translation file this repository ships as an installable app.

Frappe merges `{app}/translations/{lang}.csv` from every installed app into one
dictionary per language, keyed by source string rather than by app. One app that
carries nothing but a translation file therefore localises the whole interface,
which is what makes this installable on Frappe Cloud, where there is no shell to
copy files into a bench with.

Merge policy:

  frappe -> erpnext    later wins, mirroring the order a stock bench loads them
                       in, so a site keeps the wording it already saw
  every other app      add-only; it may contribute a source string the core
                       apps have no entry for, but never reword one they do
  overrides/{ver}.csv  applied last, and may reword anything

The add-only rule matters because this app loads after all of them. Left to
override, `lending` would reword Age as 期間 and `healthcare` would reword
Active as アクティブ for every site that installs this, including the ones with
neither app.

Padded source strings are emitted twice, stripped and verbatim. `frappe._()`
strips the message before it looks the translation up, so an entry keyed on
" Status " could never match server-side, and upstream ships a few hundred of
them. The client-side `__()` does not strip, though, so dropping the padded key
outright loses every string the desk renders in JavaScript from a fixture that
carries upstream's stray whitespace. Where stripping collides with an entry that
was already correct, the correct one is kept.

Rows whose translation equals the source, or is empty, are dropped: they change
nothing on screen and only add weight.

Usage:
    python3 scripts/build-app-translations.py --version version-15
    python3 scripts/build-app-translations.py --version version-16 --check
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = "frappe_japanese_translations"
OUT = os.path.join(REPO, APP, "translations", "ja.csv")

# frappe and erpnext first, in the order a bench installs them; everything else
# follows alphabetically so the result does not depend on filesystem ordering.
PRIORITY = ["frappe", "erpnext"]


def source_path(app: str, version: str) -> str | None:
	"""Where the set for `app` at `version` lives, or None if it has none."""
	versioned = os.path.join(REPO, "translations", app, version, "ja.csv")
	if version != "develop" and os.path.exists(versioned):
		return versioned
	flat = os.path.join(REPO, "translations", app, "ja.csv")
	if version == "develop" and os.path.exists(flat):
		return flat
	return None


def load(path: str) -> tuple[dict[str, str], int]:
	"""Return the app's entries keyed on the string `_()` will actually look up."""
	exact: dict[str, str] = {}
	padded: dict[str, str] = {}
	with open(path, encoding="utf-8", newline="") as f:
		for row in csv.reader(f):
			if len(row) < 2 or not row[0].strip():
				continue
			if row[0] == row[0].strip():
				exact[row[0]] = row[1]
			else:
				padded[row[0]] = row[1]

	recovered = 0
	for raw, value in padded.items():
		key = raw.strip()
		if key not in exact:
			exact[key] = value
			recovered += 1
		# The padded form has to survive as a key of its own as well: only the
		# Python `_()` strips before it looks a message up. The client-side
		# `__()` (frappe/public/js/frappe/translate.js) uses the string
		# verbatim, and the strings the desk renders from fixture records --
		# Onboarding Step titles among them -- carry upstream's stray spaces.
		exact.setdefault(raw, value)
	return exact, recovered


def app_order(version: str, apps: list[str] | None) -> list[str]:
	if apps:
		available = [app for app in apps if source_path(app, version)]
	else:
		with open(os.path.join(REPO, "config.json"), encoding="utf-8") as f:
			config = json.load(f)
		available = [app for app in config["apps"] if source_path(app, version)]
	rest = sorted(app for app in available if app not in PRIORITY)
	return [app for app in PRIORITY if app in available] + rest


def build(version: str, apps: list[str] | None = None) -> tuple[str, list[str]]:
	merged: dict[str, str] = {}
	report: list[str] = []
	reworded = declined = rescued = 0

	for app in app_order(version, apps):
		entries, recovered = load(source_path(app, version))
		rescued += recovered
		clash = [key for key in entries if key in merged and merged[key] != entries[key]]
		if app in PRIORITY:
			merged.update(entries)
			reworded += len(clash)
			note = f"{len(clash):>4} reworded an earlier app"
		else:
			added = {key: value for key, value in entries.items() if key not in merged}
			merged.update(added)
			declined += len(clash)
			note = f"{len(added):>4} new, {len(clash)} rewordings declined"
		report.append(f"  {app:<12} {len(entries):>6} entries, {note}")

	overrides = os.path.join(REPO, "translations", "overrides", f"{version}.csv")
	if os.path.exists(overrides):
		entries, _ = load(overrides)
		merged.update(entries)
		report.append(f"  {'overrides':<12} {len(entries):>6} entries, applied last")

	dropped = [key for key, value in merged.items() if not value or value == key]
	for key in dropped:
		del merged[key]

	buffer = io.StringIO()
	writer = csv.writer(buffer, lineterminator="\n")
	for key in sorted(merged):
		writer.writerow([key, merged[key]])

	report.append(f"  {'-' * 46}")
	report.append(f"  {len(merged)} entries written, {len(dropped)} dropped as no-ops")
	report.append(f"  {reworded} core rewordings resolved by load order")
	report.append(f"  {declined} rewordings of core declined from non-core apps")
	report.append(f"  {rescued} entries rekeyed off padded source strings that could never match")
	return buffer.getvalue(), report


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--version", default="version-15", help="version-15, version-16 or develop")
	parser.add_argument(
		"--apps",
		help="comma-separated app list; defaults to every app in config.json with a set",
	)
	parser.add_argument(
		"--check",
		action="store_true",
		help="report without writing; exit 1 if the committed file is out of date",
	)
	args = parser.parse_args()

	content, report = build(args.version, args.apps.split(",") if args.apps else None)
	print(f"Building {APP}/translations/ja.csv from the {args.version} sets")
	print("\n".join(report))

	current = ""
	if os.path.exists(OUT):
		with open(OUT, encoding="utf-8", newline="") as f:
			current = f.read()

	if args.check:
		if current == content:
			print("\nCommitted file is up to date.")
			return 0
		print("\nCommitted file is out of date — run without --check to rebuild.", file=sys.stderr)
		return 1

	os.makedirs(os.path.dirname(OUT), exist_ok=True)
	with open(OUT, "w", encoding="utf-8", newline="") as f:
		f.write(content)
	print(f"\nWritten to {os.path.relpath(OUT, REPO)}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
