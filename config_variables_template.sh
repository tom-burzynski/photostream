#!/usr/bin/env bash

# Configuration variables

# Path to source folder containing original images
SOURCE_FOLDER="./originals"
# Path to output directory for generated site
OUTPUT_DIR="./site"
# Site title displayed in browser tab and top-left corner overlay
TITLE=""
# Optional description text under the title
DESCRIPTION=""
# Optional footer text at bottom-right (e.g., copyright notice)
FOOTER=""
# Optional first footer link title (e.g., "Mastodon")
LINK1_TITLE=""
# Optional first footer link URL
LINK1_URL=""
# Optional second footer link title (e.g., "Twitter")
LINK2_TITLE=""
# Optional second footer link URL
LINK2_URL=""
# Optional third footer link title (e.g., "Instagram")
LINK3_TITLE=""
# Optional third footer link URL
LINK3_URL=""
# Maximum preview image height in pixels (lower = smaller files, faster loading)
PREVIEW_HEIGHT="500"
# Number of images to preload for LCP optimization
PRELOAD_COUNT="20"
# Number of worker threads for parallel image processing
WORKERS="2"
# Path to custom template directory (empty = use default ./templates/)
TEMPLATE_DIR=""
# Enable automatic image renaming based on EXIF datetime (true/false)
RENAME_IMAGES=""
# Enable reverse geocoding for GPS coordinates (requires internet connection, true/false)
GEOCODE=""

# Deployment configuration
# Deployment method: "rsync" or "rclone"
DEPLOYMENT_METHOD=""
# Rsync destination for deployment (format: user@host:/path or host:/path)
RSYNC_DESTINATION=""
# Rclone destination for deployment (format: remote:path)
RCLONE_DESTINATION=""
