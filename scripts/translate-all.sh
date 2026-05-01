#!/usr/bin/env bash
# translate-all.sh — Run translate-po.py across all Crowdin-managed apps.
#
# Requires: GEMINI_API_KEY exported.
# Usage:
#   ./scripts/translate-all.sh                  # all apps
#   ./scripts/translate-all.sh --limit 100      # smoke test (100 each)
#   ./scripts/translate-all.sh --only frappe    # one app
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPS=(frappe erpnext hrms healthcare lending)

LIMIT_ARGS=()
ONLY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --limit) LIMIT_ARGS=(--limit "$2"); shift 2;;
    --only)  ONLY="$2"; shift 2;;
    -h|--help) sed -n '2,8p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "error: GEMINI_API_KEY not set" >&2
  exit 2
fi

cd "$REPO_DIR"
START=$(date +%s)
for app in "${APPS[@]}"; do
  [[ -n "$ONLY" && "$ONLY" != "$app" ]] && continue
  po="translations/$app/ja.po"
  [[ ! -f "$po" ]] && { echo "[skip] $po missing"; continue; }
  echo
  echo "================================================================"
  echo "  $app"
  echo "================================================================"
  python3 scripts/translate-po.py \
    --po "$po" \
    --glossary glossary/glossary.csv \
    "${LIMIT_ARGS[@]}"
done
echo
echo "[total] $(($(date +%s) - START))s elapsed"
