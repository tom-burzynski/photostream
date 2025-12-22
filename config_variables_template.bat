@echo off
REM Windows configuration variables

REM Path to source folder containing original images
set SOURCE_FOLDER=.\originals
REM Path to output directory for generated site
set OUTPUT_DIR=.\site
REM Site title displayed in browser tab and top-left corner overlay
set TITLE=
REM Optional description text under the title
set DESCRIPTION=
REM Optional footer text at bottom-right (e.g., copyright notice)
set FOOTER=
REM Optional first footer link title (e.g., "Mastodon")
set LINK1_TITLE=
REM Optional first footer link URL
set LINK1_URL=
REM Optional second footer link title (e.g., "Twitter")
set LINK2_TITLE=
REM Optional second footer link URL
set LINK2_URL=
REM Optional third footer link title (e.g., "Instagram")
set LINK3_TITLE=
REM Optional third footer link URL
set LINK3_URL=
REM Maximum preview image height in pixels (lower = smaller files, faster loading)
set PREVIEW_HEIGHT=500
REM Number of images to preload for LCP optimization
set PRELOAD_COUNT=20
REM Number of worker threads for parallel image processing
set WORKERS=2
REM Path to custom template directory (empty = use default .\templates\)
set TEMPLATE_DIR=
REM Enable automatic image renaming based on EXIF datetime (true/false)
set RENAME_IMAGES=
REM Enable reverse geocoding for GPS coordinates (requires internet connection, true/false)
set GEOCODE=

REM Deployment configuration
REM Deployment method: "robocopy", "rsync", or "rclone"
set DEPLOYMENT_METHOD=
REM Robocopy destination for deployment (Windows paths: C:\path or \\server\share\path)
set ROBOCOPY_DESTINATION=
REM Rsync destination for deployment (requires WSL, cwRsync, or Git Bash)
set RSYNC_DESTINATION=
REM Rclone destination for deployment (format: remote:path)
set RCLONE_DESTINATION=
