#!/usr/bin/env bash
# ============================================================================
# import-back.sh — Import translations from bench back to this repo
#
# Copies {bench}/apps/{app}/{app}/translations/ja.csv → translations/{app}/ja.csv
# Shows diff before overwriting.
#
# Usage:
#   ./scripts/import-back.sh --bench-path ~/work/frappe-bench
#   ./scripts/import-back.sh --app frappe --bench-path ~/work/frappe-bench
#   ./scripts/import-back.sh --docker --project bench-01
#   ./scripts/import-back.sh --force    # Skip diff confirmation
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
TRANSLATIONS_DIR="$REPO_DIR/translations"

# Defaults
BENCH_PATH=""
DOCKER_MODE=false
DOCKER_PROJECT="bench-01"
DOCKER_BENCH_PATH="/home/frappe/frappe-bench"
TARGET_APP=""
FORCE=false

# ── Logging ─────────────────────────────────────────
log()       { echo "[$(date '+%H:%M:%S')] $*"; }
log_error() { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }

# ── Usage ───────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Import translation files from a Frappe bench back to this repo.

Options:
  --bench-path <path>   Path to frappe-bench (default: ~/work/frappe-bench)
  --app <name>          Import only this app (default: all managed apps)
  --docker              Run in Docker environment
  --project <name>      Docker compose project name (default: bench-01)
  --force               Skip diff confirmation
  -h, --help            Show this help
EOF
    exit 0
}

# ── Parse Arguments ─────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --bench-path) BENCH_PATH="$2"; shift 2 ;;
        --app)        TARGET_APP="$2"; shift 2 ;;
        --docker)     DOCKER_MODE=true; shift ;;
        --project)    DOCKER_PROJECT="$2"; shift 2 ;;
        --force)      FORCE=true; shift ;;
        -h|--help)    usage ;;
        *)            log_error "Unknown option: $1"; usage ;;
    esac
done

if [ -z "$BENCH_PATH" ]; then
    BENCH_PATH="${FRAPPE_BENCH_PATH:-$HOME/work/frappe-bench}"
fi

# ── Get app list ────────────────────────────────────
get_apps() {
    if [ -n "$TARGET_APP" ]; then
        echo "$TARGET_APP"
        return
    fi
    for dir in "$TRANSLATIONS_DIR"/*/; do
        [ -d "$dir" ] && basename "$dir"
    done
}

# ── Import ──────────────────────────────────────────
import_back() {
    local count=0
    local tmpdir
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' EXIT

    local apps
    apps=$(get_apps)

    log "Importing translations from bench..."

    for app in $apps; do
        local src=""
        local dest="$TRANSLATIONS_DIR/$app/ja.csv"
        local tmp="$tmpdir/$app-ja.csv"

        if [ "$DOCKER_MODE" = true ]; then
            local container_path="$DOCKER_BENCH_PATH/apps/$app/$app/translations/ja.csv"
            if ! docker compose --project-name "$DOCKER_PROJECT" exec -T backend \
                test -f "$container_path" 2>/dev/null; then
                log "  SKIP: $app (no ja.csv in bench)"
                continue
            fi
            docker compose --project-name "$DOCKER_PROJECT" \
                cp "backend:$container_path" "$tmp" 2>/dev/null || continue
            src="$tmp"
        else
            src="$BENCH_PATH/apps/$app/$app/translations/ja.csv"
            if [ ! -f "$src" ]; then
                log "  SKIP: $app (no ja.csv in bench)"
                continue
            fi
        fi

        # Show diff if file exists and not forced
        if [ -f "$dest" ] && [ "$FORCE" != true ]; then
            local diff_output
            diff_output=$(diff "$dest" "$src" 2>/dev/null || true)

            if [ -z "$diff_output" ]; then
                log "  SKIP: $app (no changes)"
                continue
            fi

            echo ""
            echo "=== $app: changes ==="
            echo "$diff_output" | head -30
            local diff_lines
            diff_lines=$(echo "$diff_output" | wc -l)
            if [ "$diff_lines" -gt 30 ]; then
                echo "... ($((diff_lines - 30)) more lines)"
            fi

            echo ""
            read -r -p "  Import $app? [y/N] " confirm
            if [[ ! "$confirm" =~ ^[Yy] ]]; then
                log "  SKIP: $app (declined)"
                continue
            fi
        fi

        mkdir -p "$(dirname "$dest")"
        cp "$src" "$dest"
        local lines
        lines=$(wc -l < "$dest")
        log "  OK: $app ($lines lines)"
        count=$((count + 1))
    done

    echo ""
    log "Imported: $count apps"
}

import_back
