#!/usr/bin/env bash
# sync-csv.sh — Regenerate translations/{app}/ja.csv from translations/{app}/ja.po.
#
# Run after translate-po.py / fixup-po.py to bring the deployable CSV files up
# to the latest coverage level. The PO is the source of truth (matches Crowdin
# and the upstream POT); the CSV is consumed by scripts/deploy.sh and the
# Frappe bench's apps/{app}/{app}/translations/ja.csv loader.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPS=(frappe erpnext hrms healthcare lending)

INCLUDE_EMPTY=()
ONLY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --include-empty) INCLUDE_EMPTY=(--include-empty); shift;;
    --only)          ONLY="$2"; shift 2;;
    -h|--help)       sed -n '2,9p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

cd "$REPO_DIR"
for app in "${APPS[@]}"; do
  [[ -n "$ONLY" && "$ONLY" != "$app" ]] && continue
  po="translations/$app/ja.po"
  csv="translations/$app/ja.csv"
  [[ ! -f "$po" ]] && { echo "[skip] $po missing"; continue; }
  python3 scripts/po-to-csv.py --po "$po" --csv "$csv" "${INCLUDE_EMPTY[@]}"
done
