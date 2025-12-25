#!/usr/bin/env bash

# Configuration variables for use in external scripts
# These variables are exported for consumption by build.sh and other scripts

# Path to source folder containing original images
export SOURCE_FOLDER="./originals"
# Path to output directory for generated site
export OUTPUT_DIR="./site"
# Site title displayed in browser tab and top-left corner overlay
export TITLE=""
# Optional description text under the title
export DESCRIPTION=""
# Optional footer text at bottom-right (e.g., copyright notice)
export FOOTER=""
# Optional first footer link title (e.g., "Mastodon")
export LINK1_TITLE=""
# Optional first footer link URL
export LINK1_URL=""
# Optional second footer link title (e.g., "Twitter")
export LINK2_TITLE=""
# Optional second footer link URL
export LINK2_URL=""
# Optional third footer link title (e.g., "Instagram")
export LINK3_TITLE=""
# Optional third footer link URL
export LINK3_URL=""
# Maximum preview image height in pixels (lower = smaller files, faster loading)
export PREVIEW_HEIGHT="500"
# Number of images to preload for LCP optimization
export PRELOAD_COUNT="20"
# Number of worker threads for parallel image processing
export WORKERS="2"
# Path to custom template directory (empty = use default ./templates/)
export TEMPLATE_DIR=""
# Enable automatic image renaming based on EXIF datetime (true/false)
export RENAME_IMAGES=""
# Enable reverse geocoding for GPS coordinates (requires internet connection, true/false)
export GEOCODE=""

# Deployment configuration
# Deployment method: "rsync" or "rclone"
export DEPLOYMENT_METHOD=""
# Rsync destination for deployment (format: user@host:/path or host:/path)
export RSYNC_DESTINATION=""
# Rclone destination for deployment (format: remote:path)
export RCLONE_DESTINATION=""
