#!/usr/bin/env bash
# ============================================================================
# setup-locale.sh — Full Japanese locale setup for Frappe
#
# Three-step process:
#   1. Deploy translation files (calls deploy.sh)
#   2. Enable Language DocType 'ja' and configure System Settings
#   3. Clear cache
#
# Usage:
#   ./scripts/setup-locale.sh --site dev.localhost
#   ./scripts/setup-locale.sh --docker --project bench-01
#   ./scripts/setup-locale.sh --docker --project bench-01 --site admin.example.com
#   ./scripts/setup-locale.sh --translations-only --bench-path ~/work/frappe-bench
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Defaults
BENCH_PATH=""
DOCKER_MODE=false
DOCKER_PROJECT="bench-01"
SITE="all"
TRANSLATIONS_ONLY=false

# ── Logging ─────────────────────────────────────────
log()       { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

# ── Usage ───────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Full Japanese locale setup for Frappe sites.

Options:
  --bench-path <path>     Path to frappe-bench (default: ~/work/frappe-bench)
  --site <site>           Target site (default: all)
  --docker                Run in Docker environment
  --project <name>        Docker compose project name (default: bench-01)
  --translations-only     Deploy translation files only (skip language settings)
  -h, --help              Show this help
EOF
    exit 0
}

# ── Parse Arguments ─────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --bench-path)        BENCH_PATH="$2"; shift 2 ;;
        --site)              SITE="$2"; shift 2 ;;
        --docker)            DOCKER_MODE=true; shift ;;
        --project)           DOCKER_PROJECT="$2"; shift 2 ;;
        --translations-only) TRANSLATIONS_ONLY=true; shift ;;
        -h|--help)           usage ;;
        *)                   log_error "Unknown option: $1"; usage ;;
    esac
done

if [ -z "$BENCH_PATH" ]; then
    BENCH_PATH="${FRAPPE_BENCH_PATH:-$HOME/work/frappe-bench}"
fi

# ── Docker helpers ──────────────────────────────────
docker_exec() {
    docker compose --project-name "$DOCKER_PROJECT" exec -T backend "$@"
}

docker_console() {
    local site="$1"; shift
    local python_code="$1"
    echo "$python_code" | docker compose --project-name "$DOCKER_PROJECT" \
        exec -T backend bench --site "$site" console 2>&1 \
        | grep -v "^Apps in this namespace:" \
        | grep -v "^frappe, " \
        | grep -v "^In \[" \
        | grep -v "^Do you really want to exit" \
        | grep -v "^$" \
        || true
}

local_console() {
    local site="$1"; shift
    local python_code="$1"
    echo "$python_code" | (cd "$BENCH_PATH" && bench --site "$site" console 2>&1) \
        | grep -v "^Apps in this namespace:" \
        | grep -v "^frappe, " \
        | grep -v "^In \[" \
        | grep -v "^Do you really want to exit" \
        | grep -v "^$" \
        || true
}

# ── Step 1: Deploy translations ────────────────────
step1_deploy() {
    log "Step 1: Deploying translation files..."

    local deploy_args=()
    if [ "$DOCKER_MODE" = true ]; then
        deploy_args+=(--docker --project "$DOCKER_PROJECT")
    else
        deploy_args+=(--bench-path "$BENCH_PATH")
    fi

    "$SCRIPT_DIR/deploy.sh" "${deploy_args[@]}"
}

# ── Step 2: Enable Japanese language ────────────────
step2_enable_japanese() {
    log "Step 2: Enabling Japanese language..."

    local python_code="
import frappe
frappe.connect()

# Enable Language DocType 'ja'
if frappe.db.exists('Language', 'ja'):
    lang = frappe.get_doc('Language', 'ja')
    if not lang.enabled:
        lang.enabled = 1
        lang.save(ignore_permissions=True)
        print('Language ja: enabled')
    else:
        print('Language ja: already enabled')
else:
    print('Language ja: DocType not found (run migrate first)')

# Set System Settings
ss = frappe.get_doc('System Settings')
changed = False
if ss.language != 'ja':
    ss.language = 'ja'
    changed = True
if ss.country != 'Japan':
    ss.country = 'Japan'
    changed = True
if ss.time_zone != 'Asia/Tokyo':
    ss.time_zone = 'Asia/Tokyo'
    changed = True

if changed:
    ss.save(ignore_permissions=True)
    print('System Settings: updated (language=ja, country=Japan, time_zone=Asia/Tokyo)')
else:
    print('System Settings: already configured')

frappe.db.commit()
"

    # Get site list
    local sites=()
    if [ "$SITE" = "all" ]; then
        if [ "$DOCKER_MODE" = true ]; then
            local site_list
            site_list=$(docker_exec ls -d /home/frappe/frappe-bench/sites/*/ 2>/dev/null \
                | xargs -r -n1 basename || true)
            if [ -z "$site_list" ]; then
                log "  No sites found."
                return 0
            fi
            read -ra sites <<< "$site_list"
        else
            while IFS= read -r -d '' dir; do
                sites+=("$(basename "$dir")")
            done < <(find "$BENCH_PATH/sites" -mindepth 1 -maxdepth 1 -type d \
                ! -name "assets" -print0 2>/dev/null || true)
            if [ ${#sites[@]} -eq 0 ]; then
                log "  No sites found."
                return 0
            fi
        fi
    else
        sites=("$SITE")
    fi

    for site in "${sites[@]}"; do
        log "  Configuring site: $site"
        if [ "$DOCKER_MODE" = true ]; then
            docker_console "$site" "$python_code"
        else
            local_console "$site" "$python_code"
        fi
    done

    log "  Japanese language enabled."
}

# ── Step 3: Clear cache ────────────────────────────
step3_clear_cache() {
    log "Step 3: Clearing cache..."

    if [ "$DOCKER_MODE" = true ]; then
        docker_exec bench --site "$SITE" clear-cache
    else
        (cd "$BENCH_PATH" && bench --site "$SITE" clear-cache)
    fi

    log "  Cache cleared."
}

# ── Main ────────────────────────────────────────────
main() {
    log "=========================================="
    log "Japanese Locale Setup"
    log "  Mode:              $([ "$DOCKER_MODE" = true ] && echo "Docker ($DOCKER_PROJECT)" || echo "Local")"
    log "  Bench:             $BENCH_PATH"
    log "  Target site:       $SITE"
    log "  Translations only: $TRANSLATIONS_ONLY"
    log "=========================================="

    step1_deploy

    if [ "$TRANSLATIONS_ONLY" = false ]; then
        step2_enable_japanese
    else
        log "Step 2: Skipped (--translations-only)"
    fi

    step3_clear_cache

    log "=========================================="
    log "Japanese locale setup complete!"
    log "=========================================="
}

main
