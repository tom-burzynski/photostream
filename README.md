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
- Produces an index.html, per-photo pages under view/, preview images under previews/, and paginated JSON data for infinite scroll.
- Uses templates for customizable HTML; supports Jinja2 if available or falls back to simple string templates.
- Includes a thumbnail/gradient color scheme derived from image content for background/accent colors.
- Supports configurable site metadata: custom title, description, and footer messages.
- Dynamically loads photos as you scroll, reducing initial page load time for large galleries.

## How it works
- The build.py script is the main engine. It walks the source directory, generates previews, extracts metadata, and writes static pages.
- A lightweight TemplateRenderer renders index.html and photo.html.
- The UI renders a justified grid of images; images are lazy-loaded with a pronounced fade-in effect for a smooth experience.
- Photos open in an overlay viewer with left/right navigation zones and a close button, keeping the grid loaded underneath for seamless navigation.
- Photos are split into pages (default 30 per page) with JSON files generated for each page. The initial page loads inline for fast rendering, and additional pages load automatically via IntersectionObserver as you scroll within 800px of the bottom.

## Navigating the Gallery (End-User Guide)

### Main Gallery Page

**Browsing Photos:**
- Photos are displayed in a responsive justified grid layout that adapts to your screen size
- Scroll down to view your entire photo collection in reverse chronological order (newest first)
- Images lazy-load as you scroll for optimal performance with infinite scroll pagination
- Additional photos load automatically as you approach the bottom of the page (no pagination buttons needed)
- Click any photo to view the full-size version with details

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
- Previews are created with a maximum height (default 500px) to optimize gallery loading speed. Width scales proportionally.
- Lower preview heights significantly reduce file sizes: 500px ≈ 40-50KB per image, vs 1600px ≈ 400-450KB per image.
- LCP (Largest Contentful Paint) optimization: First few images are preloaded with high priority for faster above-the-fold loading.
- Preload tags in HTML head and fetchPriority='high' ensure critical images load first.
- GPS coordinates and geocoded location names are cached to avoid repeated EXIF parsing and API calls.
- Only the first page of photos (default 30) loads in the initial HTML, drastically reducing initial page weight. For a 468-photo gallery: initial load is ~14KB of JSON vs ~100KB+ if all photos were inline.
- Additional pages load on-demand as paginated JSON files (~14KB each), triggered automatically when scrolling within 800px of the bottom.
- Page size is configurable via `page_size` parameter (default: 30). Lower values = faster initial load, more frequent dynamic loading.

## Known limitations
- Requires a writable output directory; without permissions, the build may fail.
- Non-image files present in the source tree are ignored.

## License
- This project is provided as-is. No warranty.
