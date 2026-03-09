#!/usr/bin/env bash
# ============================================================================
# coverage.sh — Report translation coverage for all managed apps
#
# Counts translated vs untranslated entries in each ja.csv file.
# An entry is "untranslated" if source == target (identical strings).
#
# Usage:
#   ./scripts/coverage.sh                # Table output
#   ./scripts/coverage.sh --json         # JSON output
#   ./scripts/coverage.sh --markdown     # Markdown table
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
TRANSLATIONS_DIR="$REPO_DIR/translations"

OUTPUT_FORMAT="table"

# ── Parse Arguments ─────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --json)     OUTPUT_FORMAT="json"; shift ;;
        --markdown) OUTPUT_FORMAT="markdown"; shift ;;
        -h|--help)
            echo "Usage: $(basename "$0") [--json|--markdown]"
            echo "Report translation coverage for all managed apps."
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Coverage calculation ───────────────────────────
# Uses Python for reliable CSV parsing (handles quoted fields, embedded commas)
calculate_coverage() {
    python3 -c "
import csv
import json
import os
import sys

translations_dir = '$TRANSLATIONS_DIR'
output_format = '$OUTPUT_FORMAT'

results = []
total_entries = 0
total_translated = 0
total_untranslated = 0

for app_dir in sorted(os.listdir(translations_dir)):
    csv_path = os.path.join(translations_dir, app_dir, 'ja.csv')
    if not os.path.isfile(csv_path):
        continue

    entries = 0
    translated = 0
    untranslated = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            source, target = row[0].strip(), row[1].strip()
            if not source:
                continue
            entries += 1
            if source == target or not target:
                untranslated += 1
            else:
                translated += 1

    pct = (translated / entries * 100) if entries > 0 else 0
    results.append({
        'app': app_dir,
        'entries': entries,
        'translated': translated,
        'untranslated': untranslated,
        'coverage': round(pct, 1)
    })
    total_entries += entries
    total_translated += translated
    total_untranslated += untranslated

total_pct = (total_translated / total_entries * 100) if total_entries > 0 else 0

if output_format == 'json':
    output = {
        'apps': results,
        'total': {
            'entries': total_entries,
            'translated': total_translated,
            'untranslated': total_untranslated,
            'coverage': round(total_pct, 1)
        }
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))

elif output_format == 'markdown':
    print('| App | Entries | Translated | Untranslated | Coverage |')
    print('|-----|---------|------------|--------------|----------|')
    for r in results:
        print(f\"| {r['app']} | {r['entries']:,} | {r['translated']:,} | {r['untranslated']:,} | {r['coverage']}% |\")
    print(f\"| **Total** | **{total_entries:,}** | **{total_translated:,}** | **{total_untranslated:,}** | **{round(total_pct, 1)}%** |\")

else:
    # Table format
    header = f\"{'App':<15} {'Entries':>8} {'Translated':>12} {'Untranslated':>14} {'Coverage':>10}\"
    print(header)
    print('-' * len(header))
    for r in results:
        bar_len = int(r['coverage'] / 5)
        bar = '█' * bar_len + '░' * (20 - bar_len)
        print(f\"{r['app']:<15} {r['entries']:>8,} {r['translated']:>12,} {r['untranslated']:>14,} {r['coverage']:>8.1f}%  {bar}\")
    print('-' * len(header))
    print(f\"{'TOTAL':<15} {total_entries:>8,} {total_translated:>12,} {total_untranslated:>14,} {round(total_pct, 1):>8.1f}%\")
"
}

calculate_coverage
