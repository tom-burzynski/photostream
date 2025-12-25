# Photostream
This is a lightweight static photo gallery generator that builds an image grid with per-photo pages. 

The functionality and layout are based on [photo-stream](https://github.com/waschinski/photo-stream).

The layout engine is borrowed from [Tim Van Damme](https://codepen.io/maxvoltar/pen/eYOPdMG), the original creator of [photo-stream](https://github.com/waschinski/photo-stream).

![Photostream Screenshot](.github/screenshots/photostream-screenshot-1.png)

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

## Installation

For installation and deployment instructions, see [INSTALLATION.md](INSTALLATION.md).

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
