#!/bin/bash

# Docker entrypoint script for photostream with file watching
set -e

# Image extensions build.py picks up (matched case-insensitively)
IMAGE_EXT_RE='\.(jpg|jpeg|png|gif|webp|tif|tiff|bmp|heic|heif)$'

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# All source images, one per line
find_images() {
    find /app/originals -type f -regextype posix-extended -iregex ".*${IMAGE_EXT_RE}" "$@"
}

# Function to build gallery. Always returns 0: under `set -e` a failed build
# would otherwise kill the watcher (and with it the container).
build_gallery() {
    log "Starting gallery build..."

    # An argument array, not a string passed to eval: values such as TITLE may
    # contain quotes or $(...), which eval would break on or execute.
    local cmd=(python3 -u build.py /app/originals
        --out-dir /app/site
        --cache-dir /app/cache
        --preview-height "${PREVIEW_HEIGHT}"
        --preload-count "${PRELOAD_COUNT}"
        --page-size "${PAGE_SIZE}"
        --workers "${WORKERS}")

    # Add optional flags
    [ "${RENAME}" = "true" ] && cmd+=(--rename)
    [ "${GEOCODE}" = "true" ] && cmd+=(--geocode)
    [ "${REGEOCODE}" = "true" ] && cmd+=(--regeocode)
    [ "${DEPLOY}" = "true" ] && cmd+=(--deploy)
    [ -n "${DEPLOY_METHOD}" ] && cmd+=(--deploy-method "${DEPLOY_METHOD}")

    # Add optional string parameters: TITLE -> --title, LINK1_URL -> --link1-url, ...
    local var
    for var in TITLE DESCRIPTION FOOTER LINK1_TITLE LINK1_URL LINK2_TITLE LINK2_URL LINK3_TITLE LINK3_URL; do
        if [ -n "${!var}" ]; then
            cmd+=("--$(echo "$var" | tr 'A-Z_' 'a-z-')" "${!var}")
        fi
    done

    local exit_code=0
    "${cmd[@]}" || exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log "Gallery build completed successfully"
    else
        log "ERROR: Gallery build failed with exit code $exit_code"
    fi
}

# Function to check if originals directory has images
has_images() {
    find_images -print -quit | grep -q .
}

# Trap function for graceful shutdown
cleanup() {
    log "Received shutdown signal, cleaning up..."
    if [ -n "$WATCHER_PID" ]; then
        kill "$WATCHER_PID" 2>/dev/null || true
    fi
    if [ -n "$WEB_SERVER_PID" ]; then
        kill "$WEB_SERVER_PID" 2>/dev/null || true
    fi
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

log "Photostream Docker watcher starting..."
log "Configuration:"
log "  PREVIEW_HEIGHT: ${PREVIEW_HEIGHT}"
log "  PRELOAD_COUNT: ${PRELOAD_COUNT}"
log "  PAGE_SIZE: ${PAGE_SIZE}"
log "  WORKERS: ${WORKERS}"
log "  RENAME: ${RENAME}"
log "  GEOCODE: ${GEOCODE}"
log "  REGEOCODE: ${REGEOCODE}"
log "  DEPLOY: ${DEPLOY}"
log "  DEPLOY_METHOD: ${DEPLOY_METHOD}"
log "  TITLE: ${TITLE}"
log "  WATCH_DELAY: ${WATCH_DELAY}"
log "  RUN_ON_STARTUP: ${RUN_ON_STARTUP}"
log "  WEB_SERVER_PORT: ${WEB_SERVER_PORT}"

# Ensure directories exist
mkdir -p /app/originals /app/site /app/cache

# Start Python web server in background if port is configured
if [ -n "${WEB_SERVER_PORT}" ] && [ "${WEB_SERVER_PORT}" != "0" ]; then
    log "Starting Python web server on port ${WEB_SERVER_PORT}..."
    python3 -m http.server "${WEB_SERVER_PORT}" --directory /app/site > /dev/null 2>&1 &
    WEB_SERVER_PID=$!
    log "Web server started (PID: $WEB_SERVER_PID) - Gallery available at http://localhost:${WEB_SERVER_PORT}"
fi

# Run initial build if requested and images exist
if [ "${RUN_ON_STARTUP}" = "true" ]; then
    if has_images; then
        log "Found images in originals directory, running initial build..."
        build_gallery
    else
        log "No images found in originals directory, skipping initial build"
    fi
fi

# Start file watching
log "Starting file watcher on /app/originals..."

# Function to get hash of directory contents
get_dir_hash() {
    find_images -exec stat -c '%n %s %Y' {} + 2>/dev/null | sort | md5sum | cut -d' ' -f1
}

# Poll rather than use inotify: inotify never sees changes made on the host
# side of a Docker Desktop / Colima bind mount on macOS.
log "Polling for changes every ${WATCH_DELAY} seconds..."
LAST_HASH=$(get_dir_hash)

while true; do
    sleep "${WATCH_DELAY}"
    CURRENT_HASH=$(get_dir_hash)
    [ "$CURRENT_HASH" = "$LAST_HASH" ] && continue

    log "Directory change detected, waiting until it settles..."
    # Debounce: wait for one full WATCH_DELAY with no further change, so
    # copying in a batch of photos triggers one build, not several partial ones.
    while sleep "${WATCH_DELAY}"; NEXT_HASH=$(get_dir_hash); [ "$NEXT_HASH" != "$CURRENT_HASH" ]; do
        CURRENT_HASH=$NEXT_HASH
    done

    if has_images; then
        build_gallery
    else
        log "No images remaining, skipping build"
    fi
    LAST_HASH=$(get_dir_hash)
done &
WATCHER_PID=$!
log "Watcher started (PID: $WATCHER_PID)."

# Keep the script running
wait "$WATCHER_PID"
