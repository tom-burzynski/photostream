#!/usr/bin/env bash

# Source configuration variables
source config_variables.sh

# Setup environment
echo "Setup environment..."
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt

# Build command with all parameters
echo "Regenerate site..."
BUILD_CMD="python3 build.py \"$SOURCE_FOLDER\" \
  --out-dir \"$OUTPUT_DIR\" \
  --title \"$TITLE\" \
  --preview-height $PREVIEW_HEIGHT \
  --preload-count $PRELOAD_COUNT \
  --workers $WORKERS"

# Add optional description if specified
if [ -n "$DESCRIPTION" ]; then
  BUILD_CMD="$BUILD_CMD --description \"$DESCRIPTION\""
fi

# Add optional footer if specified
if [ -n "$FOOTER" ]; then
  BUILD_CMD="$BUILD_CMD --footer \"$FOOTER\""
fi

# Add optional footer links if specified
if [ -n "$LINK1_TITLE" ] && [ -n "$LINK1_URL" ]; then
  BUILD_CMD="$BUILD_CMD --link1-title \"$LINK1_TITLE\" --link1-url \"$LINK1_URL\""
fi

if [ -n "$LINK2_TITLE" ] && [ -n "$LINK2_URL" ]; then
  BUILD_CMD="$BUILD_CMD --link2-title \"$LINK2_TITLE\" --link2-url \"$LINK2_URL\""
fi

if [ -n "$LINK3_TITLE" ] && [ -n "$LINK3_URL" ]; then
  BUILD_CMD="$BUILD_CMD --link3-title \"$LINK3_TITLE\" --link3-url \"$LINK3_URL\""
fi

# Add optional template directory if specified
if [ -n "$TEMPLATE_DIR" ]; then
  BUILD_CMD="$BUILD_CMD --template-dir \"$TEMPLATE_DIR\""
fi

# Add rename flag if enabled
if [ "$RENAME_IMAGES" = true ]; then
  BUILD_CMD="$BUILD_CMD --rename"
fi

# Add geocode flag if enabled
if [ "$GEOCODE" = true ]; then
  BUILD_CMD="$BUILD_CMD --geocode"
fi

# Add regeocode flag if enabled
if [ "$REGEOCODE" = true ]; then
  BUILD_CMD="$BUILD_CMD --regeocode"
fi

# Execute build
eval $BUILD_CMD

# Sync to remote server
echo "Syncing site..."
if [ "$DEPLOYMENT_METHOD" = "rsync" ]; then
  rsync -avu -q --delete "$OUTPUT_DIR"/* "$RSYNC_DESTINATION"
elif [ "$DEPLOYMENT_METHOD" = "rclone" ]; then
  rclone sync --verbose $OUTPUT_DIR $RCLONE_DESTINATION
else
  echo "No deployment method specified or invalid method: $DEPLOYMENT_METHOD"
fi
