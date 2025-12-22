# Photostream
This is a lightweight static photo gallery generator that builds an image grid with per-photo pages. 

The functionality and layout are based on [photo-stream](https://github.com/waschinski/photo-stream).

The layout engine is borrowed from [Tim Van Damme](https://codepen.io/maxvoltar/pen/eYOPdMG), the original creator of [photo-stream](https://github.com/waschinski/photo-stream). 

## What it does
- Scans a folder (recursively) for images and builds a static site that presents photos in a justified grid.
- Generates optimized WebP previews for fast loading and smaller sizes.
- Extracts basic metadata (timestamps, image dimensions) with caching to speed up repeated runs.
- Extracts GPS coordinates from EXIF data and performs reverse geocoding to display location names.
- Creates per-photo detail pages with navigation to adjacent images and location/timestamp overlays.
- Produces an index.html, per-photo pages under view/, and preview images under previews/.
- Uses templates for customizable HTML; supports Jinja2 if available or falls back to simple string templates.
- Includes a thumbnail/gradient color scheme derived from image content for background/accent colors.
- Supports configurable site metadata: custom title, description, and footer messages.

## How it works
- The build.py script is the main engine. It walks the source directory, generates previews, extracts metadata, and writes static pages.
- A lightweight TemplateRenderer renders index.html and photo.html using either Jinja2 or a fallback template system.
- The UI renders a justified grid of images; images are lazy-loaded with a pronounced fade-in effect for a smooth experience.
- Photos open in an overlay viewer with left/right navigation zones and a close button, keeping the grid loaded underneath for seamless navigation.

## Navigating the Gallery (End-User Guide)

### Main Gallery Page

**Browsing Photos:**
- Photos are displayed in a responsive justified grid layout that adapts to your screen size
- Scroll down to view your entire photo collection in reverse chronological order (newest first)
- Images lazy-load as you scroll for optimal performance
- Click any photo to view the full-size version with details

**Month/Year Picker:**
- Located in the upper-right corner of the page (fixed position, always visible)
- Shows the current month/year in viewport as you scroll
- Click to open dropdown and select any month/year to jump directly to that time period
- Months are grouped by year with the most recent dates at the top
- The currently visible month is highlighted in the dropdown

**Site Information:**
- Site title and description appear in the upper-left corner overlay
- Footer links (if configured) appear at the bottom-right corner

### Photo Overlay Viewer

**Navigation:**
- **Left 50% of screen**: Navigate to previous photo (shows `‹` chevron on hover)
- **Right 50% of screen**: Navigate to next photo (shows `›` chevron on hover)
- **Close button**: Click the × button in the top-right corner to return to gallery grid
- **Keyboard**: Press Escape key to close the viewer

**Touch Device Support:**
- Tap left half of screen for previous photo
- Tap right half of screen for next photo
- Chevron indicators briefly flash on touch for feedback
- Swipe gestures supported: swipe left/right to navigate between photos

**Photo Information:**
- Location and timestamp overlay appears at the bottom (if GPS data available)
- Format: "City on Date at Time" or "Date at Time" if no location data
- Full-size image loads progressively while preview displays immediately

**Seamless Navigation:**
- Gallery grid remains loaded in the background
- Closing the viewer returns you to the exact scroll position
- Background grid auto-scrolls to keep current photo in view

## Prerequisites

### Local Development
- Python 3.x
- Optional: Pillow (PIL), pillow_heif for HEIF support, jinja2 (if available)
- Optional: pip requirements in requirements.txt

### Docker Deployment
- Docker and Docker Compose
- No additional dependencies required (all included in container)

## Quick start

### Docker Deployment (Recommended)

1. **Quick start with automatic file watching:**
```bash
# Place your photos in ./originals directory
docker-compose up -d

# View logs
docker-compose logs -f photostream
```

2. **Custom deployment location:**
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

## File layout
- site/index.html – main grid index
- site/view/<slug>.html – per-photo pages
- site/previews/*.webp – generated grid previews
- site/originals/*.webp – converted full-size images
- favicon.svg – favicon
- templates/index.html, templates/photo.html – HTML templates (can customize)

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

## Caching and performance
- A small on-disk cache (.metadata_cache.pkl) stores image metadata, colors, GPS coordinates, location names, and preview hashes to speed up subsequent runs.
- Previews are created with a maximum height (default 400px) to optimize gallery loading speed. Width scales proportionally.
- Lower preview heights significantly reduce file sizes: 400px ≈ 30-50KB per image, vs 1600px ≈ 400-450KB per image.
- LCP (Largest Contentful Paint) optimization: First few images are preloaded with high priority for faster above-the-fold loading.
- Preload tags in HTML head and fetchPriority='high' ensure critical images load first.
- GPS coordinates and geocoded location names are cached to avoid repeated EXIF parsing and API calls.

## Known limitations
- Requires a writable output directory; without permissions, the build may fail.
- If a non-image file is present in the source tree, it will be ignored.

## Contributing
- Feature branches are welcome. Please keep changes focused and include tests or at least a sanity check.

## License
- This project is provided as-is. No warranty.
