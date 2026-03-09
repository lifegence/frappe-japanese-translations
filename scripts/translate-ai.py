#!/usr/bin/env python3
"""
translate-ai.py — AI-powered batch translation using Claude API

Translates untranslated strings in Frappe translation CSV files using
Anthropic's Claude API, with glossary support and placeholder preservation.

Usage:
  python3 scripts/translate-ai.py --app frappe
  python3 scripts/translate-ai.py --app frappe --review
  python3 scripts/translate-ai.py --app frappe --glossary glossary/glossary.csv
  python3 scripts/translate-ai.py --input _work/untranslated/frappe.txt --output _work/translated/frappe.csv

Requirements:
  pip install anthropic
  export ANTHROPIC_API_KEY=sk-ant-...
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
TRANSLATIONS_DIR = REPO_DIR / "translations"
WORK_DIR = REPO_DIR / "_work"

BATCH_SIZE = 50  # strings per API call
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096

PLACEHOLDER_RE = re.compile(r"\{[\w.]+\}")


def load_glossary(glossary_path: str) -> dict:
    """Load glossary CSV into a dict."""
    glossary = {}
    if not glossary_path or not os.path.exists(glossary_path):
        return glossary
    with open(glossary_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source = row.get("source", "").strip()
            target = row.get("target", "").strip()
            if source and target:
                glossary[source] = target
    return glossary


def get_untranslated(csv_path: Path) -> list[tuple[str, int]]:
    """Get untranslated entries from a translation CSV."""
    untranslated = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for line_num, row in enumerate(reader, 1):
            if len(row) < 2:
                continue
            source = row[0].strip()
            target = row[1].strip()
            if source and (source == target or not target):
                untranslated.append((source, line_num))
    return untranslated


def translate_batch(
    strings: list[str], glossary: dict, client
) -> list[dict]:
    """Translate a batch of strings using Claude API."""
    glossary_section = ""
    if glossary:
        glossary_lines = [f"- {k} → {v}" for k, v in list(glossary.items())[:100]]
        glossary_section = f"""
## Glossary (use these translations consistently)
{chr(10).join(glossary_lines)}
"""

    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(strings))

    prompt = f"""Translate the following English strings to Japanese for a Frappe/ERPNext business application.

## Rules
1. Preserve all placeholders exactly: {{0}}, {{1}}, {{name}}, etc.
2. Preserve HTML tags exactly: <b>, <br>, etc.
3. Use polite/formal Japanese (です/ます form) for user-facing messages
4. Use concise terms for UI labels (e.g., buttons, column headers)
5. Keep technical terms that are commonly used in katakana (e.g., サーバー, データベース)
6. Do NOT translate code identifiers, variable names, or file paths
{glossary_section}
## Strings to translate (one per line, numbered)
{numbered}

## Output format
Return a JSON array of objects, one per input string, in the same order:
[{{"index": 1, "source": "original", "target": "翻訳"}}, ...]

Return ONLY the JSON array, no other text."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Extract JSON from response (handle markdown code blocks)
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    try:
        results = json.loads(text)
    except json.JSONDecodeError:
        print(f"  WARNING: Failed to parse API response as JSON", file=sys.stderr)
        results = []

    return results


def update_csv(csv_path: Path, translations: dict[str, str]):
    """Update CSV file with new translations."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2:
                source = row[0].strip()
                if source in translations:
                    row[1] = translations[source]
            rows.append(row)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description="AI-powered batch translation using Claude API"
    )
    parser.add_argument("--app", help="App to translate")
    parser.add_argument("--input", help="Input file with untranslated strings")
    parser.add_argument("--output", help="Output CSV for translated strings")
    parser.add_argument("--glossary", help="Glossary CSV path")
    parser.add_argument(
        "--review",
        action="store_true",
        help="Review mode: confirm each batch before applying",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Strings per API call (default: {BATCH_SIZE})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be translated without calling API")
    args = parser.parse_args()

    # Validate
    if not args.app and not args.input:
        print("ERROR: --app or --input is required", file=sys.stderr)
        sys.exit(1)

    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    # Initialize client
    client = None
    if not args.dry_run:
        try:
            import anthropic
        except ImportError:
            print("ERROR: 'anthropic' package not installed. Run: pip install anthropic", file=sys.stderr)
            sys.exit(1)
        client = anthropic.Anthropic(api_key=api_key)

    # Load glossary
    glossary_path = args.glossary or str(REPO_DIR / "glossary" / "glossary.csv")
    glossary = load_glossary(glossary_path)
    if glossary:
        print(f"Loaded glossary: {len(glossary)} terms")

    # Get untranslated strings
    if args.input:
        untranslated = []
        with open(args.input, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    untranslated.append((line, line_num))
        csv_path = None
    else:
        csv_path = TRANSLATIONS_DIR / args.app / "ja.csv"
        if not csv_path.exists():
            print(f"ERROR: {csv_path} not found", file=sys.stderr)
            sys.exit(1)
        untranslated = get_untranslated(csv_path)

    print(f"Found {len(untranslated)} untranslated strings")

    if not untranslated:
        print("Nothing to translate.")
        return

    if args.dry_run:
        print("\nDry run — first 20 untranslated strings:")
        for source, _ in untranslated[:20]:
            print(f"  {source[:80]}")
        if len(untranslated) > 20:
            print(f"  ... and {len(untranslated) - 20} more")
        return

    # Process in batches
    all_translations = {}
    total_batches = (len(untranslated) + args.batch_size - 1) // args.batch_size

    for batch_num in range(total_batches):
        start = batch_num * args.batch_size
        end = min(start + args.batch_size, len(untranslated))
        batch = untranslated[start:end]
        strings = [s for s, _ in batch]

        print(f"\nBatch {batch_num + 1}/{total_batches} ({len(strings)} strings)...")

        results = translate_batch(strings, glossary, client)

        if not results:
            print("  No results from API, skipping batch")
            continue

        batch_translations = {}
        for r in results:
            source = r.get("source", "")
            target = r.get("target", "")
            if source and target:
                batch_translations[source] = target

        # Review mode
        if args.review:
            print("\n  Translations for review:")
            for source, target in batch_translations.items():
                print(f"    {source[:50]}")
                print(f"    → {target}")
                print()

            confirm = input("  Accept this batch? [y/N/e(dit)] ").strip().lower()
            if confirm == "e":
                print("  Edit mode not supported in CLI. Skipping batch.")
                continue
            elif confirm != "y":
                print("  Skipped.")
                continue

        all_translations.update(batch_translations)
        print(f"  Translated: {len(batch_translations)} strings")

        # Rate limiting
        if batch_num < total_batches - 1:
            time.sleep(1)

    print(f"\nTotal translated: {len(all_translations)} strings")

    # Save results
    if args.output:
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            for source, target in all_translations.items():
                writer.writerow([source, target, ""])
        print(f"Saved to: {output_path}")
    elif csv_path:
        update_csv(csv_path, all_translations)
        print(f"Updated: {csv_path}")
    else:
        # Print to stdout
        writer = csv.writer(sys.stdout)
        for source, target in all_translations.items():
            writer.writerow([source, target, ""])


if __name__ == "__main__":
    main()
