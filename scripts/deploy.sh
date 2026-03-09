#!/usr/bin/env bash
# ============================================================================
# deploy.sh — Deploy Japanese translation files to a Frappe bench
#
# Copies translations/{app}/ja.csv → {bench}/apps/{app}/{app}/translations/ja.csv
#
# Usage:
#   ./scripts/deploy.sh                                    # Local (default bench)
#   ./scripts/deploy.sh --bench-path ~/work/frappe-bench   # Local (custom path)
#   ./scripts/deploy.sh --app frappe                       # Single app
#   ./scripts/deploy.sh --docker --project bench-01        # Docker
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
TRANSLATIONS_DIR="$REPO_DIR/translations"
CONFIG_FILE="$REPO_DIR/config.json"

# Defaults
BENCH_PATH=""
DOCKER_MODE=false
DOCKER_PROJECT="bench-01"
DOCKER_BENCH_PATH="/home/frappe/frappe-bench"
TARGET_APP=""

# ── Logging ─────────────────────────────────────────
log()       { echo "[$(date '+%H:%M:%S')] $*"; }
log_error() { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }

# ── Usage ───────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Deploy Japanese translation CSV files to a Frappe bench.

Options:
  --bench-path <path>   Path to frappe-bench (default: ~/work/frappe-bench)
  --app <name>          Deploy only this app (default: all managed apps)
  --docker              Run in Docker environment
  --project <name>      Docker compose project name (default: bench-01)
  -h, --help            Show this help

Examples:
  $(basename "$0")                                    # Local default
  $(basename "$0") --bench-path /opt/frappe-bench     # Custom bench
  $(basename "$0") --app hrms                         # Single app
  $(basename "$0") --docker --project bench-01        # Docker
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
        -h|--help)    usage ;;
        *)            log_error "Unknown option: $1"; usage ;;
    esac
done

# Resolve bench path
if [ -z "$BENCH_PATH" ]; then
    BENCH_PATH="${FRAPPE_BENCH_PATH:-$HOME/work/frappe-bench}"
fi

# ── Get app list ────────────────────────────────────
get_apps() {
    if [ -n "$TARGET_APP" ]; then
        echo "$TARGET_APP"
        return
    fi

    # List directories under translations/
    for dir in "$TRANSLATIONS_DIR"/*/; do
        [ -d "$dir" ] && basename "$dir"
    done
}

# ── Docker helpers ──────────────────────────────────
docker_exec() {
    docker compose --project-name "$DOCKER_PROJECT" exec -T backend "$@"
}

# ── Deploy ──────────────────────────────────────────
deploy() {
    local count=0
    local skipped=0
    local apps
    apps=$(get_apps)

    log "Deploying translations..."
    if [ "$DOCKER_MODE" = true ]; then
        log "  Mode: Docker (project=$DOCKER_PROJECT)"
    else
        log "  Mode: Local (bench=$BENCH_PATH)"
    fi

    for app in $apps; do
        local src="$TRANSLATIONS_DIR/$app/ja.csv"

        if [ ! -f "$src" ]; then
            log "  SKIP: $app (no ja.csv in repo)"
            skipped=$((skipped + 1))
            continue
        fi

        if [ "$DOCKER_MODE" = true ]; then
            # Check app exists in container
            if ! docker_exec test -d "$DOCKER_BENCH_PATH/apps/$app" 2>/dev/null; then
                log "  SKIP: $app (not installed)"
                skipped=$((skipped + 1))
                continue
            fi

            docker_exec mkdir -p "$DOCKER_BENCH_PATH/apps/$app/$app/translations"
            docker compose --project-name "$DOCKER_PROJECT" \
                cp "$src" "backend:$DOCKER_BENCH_PATH/apps/$app/$app/translations/ja.csv"
        else
            # Check app exists locally
            if [ ! -d "$BENCH_PATH/apps/$app" ]; then
                log "  SKIP: $app (not installed)"
                skipped=$((skipped + 1))
                continue
            fi

            mkdir -p "$BENCH_PATH/apps/$app/$app/translations"
            cp "$src" "$BENCH_PATH/apps/$app/$app/translations/ja.csv"
        fi

        local lines
        lines=$(wc -l < "$src")
        log "  OK: $app ($lines lines)"
        count=$((count + 1))
    done

    echo ""
    log "Deployed: $count apps, Skipped: $skipped apps"
    log "Run 'bench --site <site> clear-cache' to apply changes."
}

deploy
