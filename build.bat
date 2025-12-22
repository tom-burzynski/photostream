@echo off
REM Windows batch script for building photostream gallery
REM Equivalent to build.sh for Windows environments

REM Source configuration variables
call config_variables.bat

REM Setup environment
echo Setup environment...
if not exist ".venv" (
  echo Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt

REM Build command with all parameters
echo Regenerate site...
set BUILD_CMD=python build.py "%SOURCE_FOLDER%" --out-dir "%OUTPUT_DIR%" --title "%TITLE%" --preview-height %PREVIEW_HEIGHT% --preload-count %PRELOAD_COUNT% --workers %WORKERS%

REM Add optional description if specified
if not "%DESCRIPTION%"=="" (
    set BUILD_CMD=%BUILD_CMD% --description "%DESCRIPTION%"
)

REM Add optional footer if specified
if not "%FOOTER%"=="" (
    set BUILD_CMD=%BUILD_CMD% --footer "%FOOTER%"
)

REM Add optional footer links if specified
if not "%LINK1_TITLE%"=="" if not "%LINK1_URL%"=="" (
    set BUILD_CMD=%BUILD_CMD% --link1-title "%LINK1_TITLE%" --link1-url "%LINK1_URL%"
)

if not "%LINK2_TITLE%"=="" if not "%LINK2_URL%"=="" (
    set BUILD_CMD=%BUILD_CMD% --link2-title "%LINK2_TITLE%" --link2-url "%LINK2_URL%"
)

if not "%LINK3_TITLE%"=="" if not "%LINK3_URL%"=="" (
    set BUILD_CMD=%BUILD_CMD% --link3-title "%LINK3_TITLE%" --link3-url "%LINK3_URL%"
)

REM Add optional template directory if specified
if not "%TEMPLATE_DIR%"=="" (
    set BUILD_CMD=%BUILD_CMD% --template-dir "%TEMPLATE_DIR%"
)

REM Add rename flag if enabled
if /i "%RENAME_IMAGES%"=="true" (
    set BUILD_CMD=%BUILD_CMD% --rename
)

REM Add geocode flag if enabled
if /i "%GEOCODE%"=="true" (
    set BUILD_CMD=%BUILD_CMD% --geocode
)

REM Add regeocode flag if enabled
if /i "%REGEOCODE%"=="true" (
    set BUILD_CMD=%BUILD_CMD% --regeocode
)

REM Execute build
echo Running: %BUILD_CMD%
%BUILD_CMD%

REM Sync to remote server
echo Syncing site...
if /i "%DEPLOYMENT_METHOD%"=="robocopy" (
    if not "%ROBOCOPY_DESTINATION%"=="" (
        robocopy "%OUTPUT_DIR%" "%ROBOCOPY_DESTINATION%" /MIR /R:3 /W:5 /MT:8
    ) else (
        echo ROBOCOPY_DESTINATION not configured
    )
) else if /i "%DEPLOYMENT_METHOD%"=="rsync" (
    if not "%RSYNC_DESTINATION%"=="" (
        rsync -avu --delete "%OUTPUT_DIR%"/* "%RSYNC_DESTINATION%"
    ) else (
        echo RSYNC_DESTINATION not configured
    )
) else if /i "%DEPLOYMENT_METHOD%"=="rclone" (
    if not "%RCLONE_DESTINATION%"=="" (
        rclone sync --verbose "%OUTPUT_DIR%" "%RCLONE_DESTINATION%"
    ) else (
        echo RCLONE_DESTINATION not configured
    )
) else (
    echo No deployment method specified or invalid method: %DEPLOYMENT_METHOD%
)

echo Done!
pause
