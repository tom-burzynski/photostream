#!/bin/bash

# Docker entrypoint script for photostream with file watching
set -e

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to build gallery
build_gallery() {
    log "Starting gallery build..."

    # Build command with environment variables (-u for unbuffered output)
    CMD="python3 -u build.py /app/originals \
        --out-dir /app/site \
        --preview-height ${PREVIEW_HEIGHT} \
        --preload-count ${PRELOAD_COUNT} \
        --workers ${WORKERS}"

    # Add optional flags
    [ "${RENAME}" = "true" ] && CMD="${CMD} --rename"
    [ "${GEOCODE}" = "true" ] && CMD="${CMD} --geocode"
    [ "${REGEOCODE}" = "true" ] && CMD="${CMD} --regeocode"

    # Add optional string parameters
    [ -n "${TITLE}" ] && CMD="${CMD} --title \"${TITLE}\""
    [ -n "${DESCRIPTION}" ] && CMD="${CMD} --description \"${DESCRIPTION}\""
    [ -n "${FOOTER}" ] && CMD="${CMD} --footer \"${FOOTER}\""
    [ -n "${LINK1_TITLE}" ] && CMD="${CMD} --link1-title \"${LINK1_TITLE}\""
    [ -n "${LINK1_URL}" ] && CMD="${CMD} --link1-url \"${LINK1_URL}\""
    [ -n "${LINK2_TITLE}" ] && CMD="${CMD} --link2-title \"${LINK2_TITLE}\""
    [ -n "${LINK2_URL}" ] && CMD="${CMD} --link2-url \"${LINK2_URL}\""
    [ -n "${LINK3_TITLE}" ] && CMD="${CMD} --link3-title \"${LINK3_TITLE}\""
    [ -n "${LINK3_URL}" ] && CMD="${CMD} --link3-url \"${LINK3_URL}\""

    eval $CMD
    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log "Gallery build completed successfully"
    else
        log "ERROR: Gallery build failed with exit code $exit_code"
    fi

    return $exit_code
}

# Function to check if originals directory has images
has_images() {
    find /app/originals -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.gif" -o -iname "*.webp" -o -iname "*.tif" -o -iname "*.tiff" -o -iname "*.bmp" -o -iname "*.heic" -o -iname "*.heif" \) -print -quit | grep -q .
}

# Trap function for graceful shutdown
cleanup() {
    log "Received shutdown signal, cleaning up..."
    if [ ! -z "$INOTIFY_PID" ]; then
        kill $INOTIFY_PID 2>/dev/null || true
    fi
    if [ ! -z "$WEB_SERVER_PID" ]; then
        kill $WEB_SERVER_PID 2>/dev/null || true
    fi
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

log "Photostream Docker watcher starting..."
log "Configuration:"
log "  PREVIEW_HEIGHT: ${PREVIEW_HEIGHT}"
log "  PRELOAD_COUNT: ${PRELOAD_COUNT}"
log "  WORKERS: ${WORKERS}"
log "  RENAME: ${RENAME}"
log "  GEOCODE: ${GEOCODE}"
log "  REGEOCODE: ${REGEOCODE}"
log "  TITLE: ${TITLE}"
log "  WATCH_DELAY: ${WATCH_DELAY}"
log "  RUN_ON_STARTUP: ${RUN_ON_STARTUP}"
log "  WEB_SERVER_PORT: ${WEB_SERVER_PORT}"

# Ensure directories exist
mkdir -p /app/originals /app/site

# Start Python web server in background if port is configured
if [ ! -z "${WEB_SERVER_PORT}" ] && [ "${WEB_SERVER_PORT}" != "0" ]; then
    log "Starting Python web server on port ${WEB_SERVER_PORT}..."
    cd /app/site
    python3 -m http.server ${WEB_SERVER_PORT} > /dev/null 2>&1 &
    WEB_SERVER_PID=$!
    cd /app
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
    find /app/originals -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.gif" -o -iname "*.webp" -o -iname "*.tif" -o -iname "*.tiff" -o -iname "*.bmp" -o -iname "*.heic" -o -iname "*.heif" \) -exec stat -c '%n %s %Y' {} \; 2>/dev/null | md5sum | cut -d' ' -f1
}

# Try inotify first (works on Linux), fall back to polling (for macOS)
if command -v inotifywait >/dev/null 2>&1 && inotifywait -t 1 /app/originals >/dev/null 2>&1; then
    # Use inotify to watch for file system events
    log "Using inotify for file watching..."
    inotifywait -m -r -e close_write -e moved_to -e delete /app/originals --format '%w%f %e' 2>/dev/null | while read file event; do
        log "Detected $event for $file"

        # Check if it's an image file
        if [[ "$file" =~ \.(jpg|jpeg|png|gif|webp|tif|tiff|bmp|heic|heif)$ ]]; then
            log "Image file detected, waiting ${WATCH_DELAY} seconds for stability..."
            sleep "${WATCH_DELAY}"

            # Check if we still have images (in case files were deleted)
            if has_images; then
                build_gallery
            else
                log "No images remaining, skipping build"
            fi
        else
            log "Non-image file, ignoring"
        fi
    done &
    INOTIFY_PID=$!
    log "File watcher started (PID: $INOTIFY_PID). Waiting for file changes..."
else
    # Fall back to polling for macOS/environments without inotify
    log "Using polling for file watching (checking every ${WATCH_DELAY} seconds)..."
    LAST_HASH=$(get_dir_hash)

    while true; do
        sleep "${WATCH_DELAY}"
        CURRENT_HASH=$(get_dir_hash)

        if [ "$CURRENT_HASH" != "$LAST_HASH" ]; then
            log "Directory change detected..."
            if has_images; then
                build_gallery
                LAST_HASH=$(get_dir_hash)
            else
                log "No images remaining, skipping build"
                LAST_HASH=""
            fi
        fi
    done &
    INOTIFY_PID=$!
    log "Polling watcher started (PID: $INOTIFY_PID). Checking for changes every ${WATCH_DELAY} seconds..."
fi

# Keep the script running
wait $INOTIFY_PID