# Installation Guide

This guide covers installing and running Photostream locally with Python.

## Prerequisites

- Python 3.x
- pip (Python package installer)
- Optional: Pillow (PIL), pillow_heif for HEIF support, jinja2
- Optional: rclone or rsync for deployment

## Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Configure Your Gallery

Copy the configuration template and customize it:

```bash
cp config_template.ini config.ini
```

Edit `config.ini` with your preferences. The configuration file has three sections:

**[build]** - Build settings:
- `folder` - Source folder containing original images (default: `./originals`)
- `out_dir` - Output directory for generated site (default: `./site`)
- `workers` - Number of worker threads for parallel processing (default: auto-detect CPU cores)
- `preview_height` - Maximum preview image height in pixels (default: 500px, lower = faster loading)
- `preload_count` - Number of images to preload for LCP optimization (default: 20)
- `rename` - Automatically rename images based on EXIF datetime (true/false)
- `geocode` - Enable GPS coordinate extraction and reverse geocoding (true/false, requires internet)
- `regeocode` - Force re-geocoding of all images, ignoring cache (true/false)

**[gallery]** - Site metadata:
- `title` - Site title for browser tab and overlay (default: `[photostream]`)
- `description` - Optional description text under title
- `footer` - Optional footer message at bottom-right (e.g., copyright notice)
- `link1_title`, `link1_url` - First footer link
- `link2_title`, `link2_url` - Second footer link
- `link3_title`, `link3_url` - Third footer link

**[deployment]** - Deployment settings:
- `method` - Deployment method: `rsync`, `rclone`, or leave empty to disable
- `rsync_destination` - rsync destination (format: `user@host:/path` or `host:/path`)
- `rclone_destination` - rclone destination (format: `remote:path`)
- `robocopy_destination` - robocopy destination for Windows (format: `C:\path` or `\\server\share\path`)

### 3. Build Your Gallery

Place your photos in the configured source folder (default: `./originals`), then run:

```bash
# Basic build (uses settings from config.ini)
python3 build.py

# Build with deployment
python3 build.py --deploy

# Override specific config.ini settings via command line
python3 build.py --title "My Gallery" --workers 16

# Use a custom config file
python3 build.py --config my-config.ini
```

The generated gallery will be in your configured output directory (default: `./site`).

### 4. View Your Gallery

Open `site/index.html` in a web browser, or serve it with a local web server:

```bash
# Python built-in server
python3 -m http.server 8080 --directory site

# Access at http://localhost:8080
```

## Command-Line Options

All configuration options can be overridden via command-line arguments:
```bash
# Build with custom settings
python3 build.py ./photos --out-dir ./gallery --workers 8

# Optimized for faster loading (smaller preview images)
python3 build.py --preview-height 400 --preload-count 20

# With GPS location geocoding (requires internet connection)
python3 build.py --geocode

# With custom site metadata and footer links
python3 build.py \
  --title "My Gallery" \
  --description "Photo collection" \
  --footer "© 2025" \
  --link1-title "Mastodon" \
  --link1-url "https://mastodon.social/@user"

# Rename images based on EXIF datetime before processing
python3 build.py --rename

# Deploy after building
python3 build.py --deploy
python3 build.py --deploy-method rclone

# View all options
python3 build.py --help
```

## Deployment

Photostream supports automatic deployment via rsync, rclone, or robocopy (Windows):

### Configure Deployment

Edit `config.ini` and set your deployment method and destination:

```ini
[deployment]
method = rclone
rclone_destination = myremote:path/to/gallery
```

### Deploy Your Gallery

```bash
# Build and deploy using config.ini settings
python3 build.py --deploy

# Override deployment method
python3 build.py --deploy-method rsync
```

### Deployment Methods

**rsync** (Linux/macOS):
```ini
method = rsync
rsync_destination = user@server:/var/www/html/gallery
```

**rclone** (Cross-platform, supports cloud storage):
```ini
method = rclone
rclone_destination = myremote:bucket/gallery
```

**robocopy** (Windows):
```ini
method = robocopy
robocopy_destination = \\server\share\gallery
```

## Customization

### Display Settings
- Gallery row height is controlled by CSS (40vh by default, edit `templates/index.html` to customize)
- Adjust preview image size with `preview_height` to control gallery loading speed (default 500px, lower values = smaller files and faster loading)
- Configure LCP optimization with `preload_count` to control how many images are preloaded for faster above-the-fold loading (default 20)

### Site Metadata
- Customize site title with `title` parameter (default: "[photostream]") - displays in browser tab and top-left corner overlay
- Add description text with `description` parameter - displays under the title in smaller font
- Add footer message with `footer` parameter - displays at bottom-right (e.g., copyright notice)
- Add up to 3 footer links with `link1_title`/`link1_url`, `link2_title`/`link2_url`, `link3_title`/`link3_url` parameters
- Footer links appear below the footer message, separated by pipe characters (|)
- Links open in new tabs with security attributes (target="_blank" rel="noopener noreferrer")

### GPS and Location Features
- Enable GPS coordinate extraction and reverse geocoding with `geocode = true` (requires internet connection)
- Location data is displayed on individual photo pages as "City on Date at Time" format
- Photos without GPS data fall back to "Date at Time" display
- Location names are cached to minimize API calls and improve performance
- Uses Photon API (OpenStreetMap) for reverse geocoding

### Templates and Colors
- Templates can be customized by editing `templates/index.html` and `templates/photo.html`
- If Jinja2 is installed, those templates are used; otherwise a simple string template fallback is used
- The color palette (bg_color, accent_color, text_color) is derived from image content and cached for performance

## File Layout
- `site/index.html` – main grid index
- `site/view/<slug>.html` – per-photo pages
- `site/previews/*.webp` – generated grid previews
- `site/originals/*.webp` – converted full-size images
- `favicon.svg` – favicon
- `templates/index.html`, `templates/photo.html` – HTML templates (can customize)

## Known Limitations
- Requires a writable output directory; without permissions, the build may fail
- If a non-image file is present in the source tree, it will be ignored
