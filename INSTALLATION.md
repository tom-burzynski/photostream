# Installation Guide

This guide covers installing and deploying Photostream using Docker or local Python.

## Prerequisites

### Docker Deployment
- Docker and Docker Compose
- No additional dependencies required (all included in container)

### Local Development
- Python 3.x
- Optional: Pillow (PIL), pillow_heif for HEIF support, jinja2
- Optional: pip requirements in requirements.txt

## Quick Start

### Docker Deployment (Recommended)

**Configuration:**

Before deploying with Docker Compose, you can customize the gallery settings by creating a `.env` file:

```bash
# Copy the template and customize your settings
cp .env_template .env
# Edit .env with your preferences
```

The `.env` file allows you to configure:
- Site metadata (title, description, footer, links)
- Image processing options (preview height, preload count, workers)
- Feature flags (automatic renaming, geocoding)
- Docker watcher settings (delay, startup behavior)
- Web server port

If you don't create a `.env` file, Docker Compose will use the default values from the template.

**Option 1: Use pre-built image from GitHub Container Registry**
```bash
# Pull the latest image
docker pull ghcr.io/tom-burzynski/photostream:latest

# Run with your photos
docker run -d \
  -p 8080:8080 \
  -v ./originals:/app/originals \
  -v ./site:/app/site \
  -e GEOCODE=true \
  -e RENAME=true \
  ghcr.io/tom-burzynski/photostream:latest

# View gallery at http://localhost:8080
```

**Option 2: Build locally with Docker Compose**
```bash
# Place your photos in ./originals directory
docker-compose up -d

# View logs
docker-compose logs -f photostream

# Access gallery at http://localhost:8080
```

**Custom deployment location:**
```bash
# Edit docker-compose.yml to mount your target directory:
# - /var/www/html/gallery:/app/site    # Web server
# - /path/to/your/site:/app/site       # Custom location

docker-compose up -d
```

The Docker setup automatically watches for file changes and rebuilds the gallery when photos are added, modified, or removed.

### Local Development

1. **Configure your build:**

**Linux/macOS:**
```bash
# Copy the template and customize your settings
cp config_variables_template.sh config_variables.sh
# Edit config_variables.sh with your preferences
```

**Windows:**
```cmd
# Copy the template and customize your settings
copy config_variables_template.bat config_variables.bat
# Edit config_variables.bat with your preferences
```

The config file allows you to set:
- Source folder and output directory paths
- Site metadata (title, description, footer, links)
- Image processing options (preview height, preload count, workers)
- Deployment method (rsync, rclone, or robocopy on Windows)
- Deployment destinations

2. **Build gallery using the automated script:**

**Linux/macOS:**
```bash
bash build.sh
```

**Windows:**
```cmd
build.bat
```

The build scripts will:
- Create a virtual environment (if it doesn't exist)
- Install dependencies
- Build the gallery using your configured settings
- Deploy to your configured destination (if set)

3. **Or build gallery manually:**
```bash
# Basic build
python3 build.py ./originals --out-dir ./site --workers 4

# Optimized for faster loading (smaller preview images)
python3 build.py ./originals --out-dir ./site --preview-height 400 --workers 4

# With LCP optimization for fastest initial page loading
python3 build.py ./originals --out-dir ./site --preview-height 400 --preload-count 20 --workers 4

# With GPS location geocoding (requires internet connection)
python3 build.py ./originals --out-dir ./site --preview-height 400 --geocode --workers 4

# With custom site metadata and footer links
python3 build.py ./originals --out-dir ./site --title "My Gallery" --description "Photo collection" --footer "© 2025" --link1-title "Mastodon" --link1-url "https://mastodon.social/@user" --link2-title "Twitter" --link2-url "https://twitter.com/user" --workers 4
```

## Docker Configuration

The Docker setup supports configuration via environment variables in `docker-compose.yml`:

```yaml
environment:
  - PREVIEW_HEIGHT=400      # Max preview image height
  - PRELOAD_COUNT=20        # Number of images to preload for LCP
  - WORKERS=4               # Number of worker threads
  - WATCH_DELAY=5           # Seconds to wait after file changes
  - RUN_ON_STARTUP=true     # Build gallery on container start
  - GEOCODE=false           # Enable GPS geocoding (requires internet)
  - TITLE=[photostream]     # Site title for browser tab and overlay
  - DESCRIPTION=            # Optional description text under title
  - FOOTER=                 # Optional footer message (bottom-right)
  - LINK1_TITLE=            # Optional first footer link title
  - LINK1_URL=              # Optional first footer link URL
  - LINK2_TITLE=            # Optional second footer link title
  - LINK2_URL=              # Optional second footer link URL
  - LINK3_TITLE=            # Optional third footer link title
  - LINK3_URL=              # Optional third footer link URL
```

### Volume Mounting Examples

**Local development:**
```yaml
volumes:
  - ./originals:/app/originals:ro
  - ./site:/app/site
```

**Web server deployment:**
```yaml
volumes:
  - ./originals:/app/originals:ro
  - /var/www/html/gallery:/app/site
```

**Custom location:**
```yaml
volumes:
  - ./originals:/app/originals:ro
  - /path/to/your/deployment:/app/site
```

## Local Customization

### Display Settings
- Gallery row height is controlled by CSS (40vh by default, edit `templates/index.html` to customize)
- Adjust preview image size with --preview-height to control gallery loading speed (default 400px, lower values = smaller files and faster loading)
- Configure LCP optimization with --preload-count to control how many images are preloaded for faster above-the-fold loading (default 20)

### Site Metadata
- Customize site title with --title parameter (default: "[photostream]") - displays in browser tab and top-left corner overlay.
- Add description text with --description parameter - displays under the title in smaller font.
- Add footer message with --footer parameter - displays at bottom-right (e.g., copyright notice).
- Add up to 3 footer links with --link1-title/--link1-url, --link2-title/--link2-url, --link3-title/--link3-url parameters.
- Footer links appear below the footer message, separated by pipe characters (|).
- Links open in new tabs with security attributes (target="_blank" rel="noopener noreferrer").

### GPS and Location Features
- Enable GPS coordinate extraction and reverse geocoding with --geocode flag (requires internet connection).
- Location data is displayed on individual photo pages as "City on Date at Time" format.
- Photos without GPS data fall back to "Date at Time" display.
- Location names are cached to minimize API calls and improve performance.
- Uses Photon API (OpenStreetMap) for reverse geocoding.

### Templates and Colors
- Templates can be customized by editing templates/index.html and templates/photo.html. If Jinja2 is installed, those templates are used; otherwise a simple string template fallback is used.
- The color palette (bg_color, accent_color, text_color) is derived from image content and cached for performance.

## File Layout
- site/index.html – main grid index
- site/view/<slug>.html – per-photo pages
- site/previews/*.webp – generated grid previews
- site/originals/*.webp – converted full-size images
- favicon.svg – favicon
- templates/index.html, templates/photo.html – HTML templates (can customize)

## Known Limitations
- Requires a writable output directory; without permissions, the build may fail.
- If a non-image file is present in the source tree, it will be ignored.
