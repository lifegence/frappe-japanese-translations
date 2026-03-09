#!/usr/bin/env bash
# ============================================================================
# extract.sh — Extract untranslated strings from Frappe apps
#
# Runs `bench get-untranslated` for each app and saves results to _work/untranslated/
#
# Usage:
#   ./scripts/extract.sh --site dev.localhost                 # All apps
#   ./scripts/extract.sh --site dev.localhost --app frappe    # Single app
#   ./scripts/extract.sh --site dev.localhost --docker --project bench-01
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
TRANSLATIONS_DIR="$REPO_DIR/translations"
OUTPUT_DIR="$REPO_DIR/_work/untranslated"

# Defaults
SITE=""
BENCH_PATH=""
DOCKER_MODE=false
DOCKER_PROJECT="bench-01"
TARGET_APP=""

# ── Logging ─────────────────────────────────────────
log()       { echo "[$(date '+%H:%M:%S')] $*"; }
log_error() { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }

# ── Usage ───────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") --site <site> [OPTIONS]

Extract untranslated strings from Frappe apps.

Required:
  --site <site>         Target Frappe site name

Options:
  --bench-path <path>   Path to frappe-bench (default: ~/work/frappe-bench)
  --app <name>          Extract only this app (default: all managed apps)
  --docker              Run in Docker environment
  --project <name>      Docker compose project name (default: bench-01)
  -h, --help            Show this help

Output:
  _work/untranslated/{app}.txt per app
EOF
    exit 0
}

# ── Parse Arguments ─────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --site)       SITE="$2"; shift 2 ;;
        --bench-path) BENCH_PATH="$2"; shift 2 ;;
        --app)        TARGET_APP="$2"; shift 2 ;;
        --docker)     DOCKER_MODE=true; shift ;;
        --project)    DOCKER_PROJECT="$2"; shift 2 ;;
        -h|--help)    usage ;;
        *)            log_error "Unknown option: $1"; usage ;;
    esac
done

if [ -z "$SITE" ]; then
    log_error "--site is required"
    usage
fi

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

# ── Extract ─────────────────────────────────────────
extract() {
    mkdir -p "$OUTPUT_DIR"
    local count=0
    local apps
    apps=$(get_apps)

    log "Extracting untranslated strings..."
    log "  Site: $SITE"

    for app in $apps; do
        local outfile="$OUTPUT_DIR/$app.txt"

        log "  Extracting: $app ..."

        if [ "$DOCKER_MODE" = true ]; then
            docker compose --project-name "$DOCKER_PROJECT" exec -T backend \
                bench --site "$SITE" get-untranslated ja "$outfile" --app "$app" 2>&1 \
                || log "  WARN: $app extraction may have issues"

            # Copy output from container
            docker compose --project-name "$DOCKER_PROJECT" \
                cp "backend:$outfile" "$outfile" 2>/dev/null || true
        else
            (cd "$BENCH_PATH" && bench --site "$SITE" get-untranslated ja "$outfile" --app "$app" 2>&1) \
                || log "  WARN: $app extraction may have issues"
        fi

        if [ -f "$outfile" ]; then
            local lines
            lines=$(wc -l < "$outfile")
            log "  OK: $app ($lines untranslated strings)"
            count=$((count + 1))
        else
            log "  SKIP: $app (no output)"
        fi
    done

    echo ""
    log "Extracted $count apps → $OUTPUT_DIR/"
}

extract
