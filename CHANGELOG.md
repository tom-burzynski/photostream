# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-12-20

Initial public release of photostream - a lightweight static photo gallery generator.

### Fixed
- Footer separator logic now correctly handles single link configuration (prevents double pipe separators)
- Geocoding log messages now suppressed for cached locations (reduces console noise)

### Added - Configuration File System
- External configuration files for build scripts (config_variables.sh and config_variables.bat)
- Template configuration files (config_variables_template.sh and config_variables_template.bat)
- Centralized configuration for all build parameters and deployment settings
- Support for multiple deployment methods: rsync, rclone, and robocopy (Windows)
- DEPLOYMENT_METHOD variable to switch between deployment tools
- Conditional deployment logic based on configured method
- Personal config files kept separate from version control
- Template files included in prod repository for user customization
- Detailed comments for all configuration variables
- Virtual environment creation only when needed (avoids recreation on each build)

### Changed - Build Scripts
- build.sh and build.bat now source external configuration files
- Removed hardcoded configuration variables from build scripts
- Improved deployment flexibility with conditional method selection
- Better error messages when deployment destinations not configured
- Updated documentation to reflect new configuration workflow

### Added - Footer Links
- Support for up to 3 customizable footer links (social media, external sites, etc.)
- Links displayed below footer message at bottom-right corner
- Pipe character (|) separation between links for clean visual presentation
- Command-line parameters: `--link1-title/url`, `--link2-title/url`, `--link3-title/url`
- Links open in new tabs with security attributes (`target="_blank" rel="noopener noreferrer"`)
- Hover effect with opacity transition for visual feedback
- Mobile-responsive positioning with reduced spacing
- Minimal vertical gap (1.5rem) between footer message and links
- Only displays when both title and URL are provided for each link
- Environment variable support in build.sh: `LINK{1,2,3}_{TITLE,URL}`

### Added - GPS Location and Geocoding
- GPS coordinate extraction from EXIF data with caching infrastructure
- Reverse geocoding using Photon API to convert coordinates to location names
- Location and timestamp overlay on individual photo pages
- Display format: "City on Date at Time" when GPS data available
- Fallback to "Date at Time" for photos without GPS data
- Configurable geocoding via `--geocode` flag (default disabled, requires internet)
- Persistent location caching to minimize API calls
- Text shadow styling for readability over photo backgrounds
- Mobile-responsive font sizing for photo information overlay

### Added - Configurable Site Metadata
- Configurable site title via `--title` parameter (default: "[photostream]")
- Configurable site description via `--description` parameter (displays under title)
- Configurable footer message via `--footer` parameter (bottom-right corner)
- Floating site title overlay on grid page (top-left corner)
- Semi-transparent text overlays with shadow for readability
- Mobile-responsive sizing for all text overlays
- Environment variable support in build.sh for easy customization

### Changed - UI Layout
- Moved site title from top-right to top-left corner for better visual balance
- Month picker remains in top-right corner
- Footer positioned at bottom-right corner when enabled
- All overlays use pointer-events: none for non-intrusive display
- Improved multi-line command formatting in build.sh for readability

### Changed - Visual Assets
- Updated favicon.svg with refined styling

### Added - Progressive Image Loading
- Progressive loading for individual photo pages to eliminate jarring full-size image pop-in
- Preview images display instantly (already cached from grid view) while full-size versions load
- Seamless low-resolution to high-resolution transition without black flash
- Automatic image source swapping when full-size image completes loading
- Respects user's reduced motion preferences for transition duration
- Works seamlessly with View Transitions API slide animations

### Added - Enhanced Photo Navigation
- Full-viewport navigation overlay system for individual photo pages
- Visual navigation indicators: chevron symbols for previous/next navigation
- Grid symbol indicator for returning to main gallery
- 30/40/30 viewport division for intuitive navigation zones
- Hover-activated visual cues with smooth fade transitions
- Touch device support with active state feedback
- Accessibility improvements with proper ARIA labels and keyboard support
- Motion preference support for reduced animation when requested

### Added - Docker Deployment Support
- Complete Docker containerization with file watching and automatic rebuilds
- Docker Compose configuration for easy deployment setup
- File system monitoring using `inotify` for automatic gallery rebuilds on image changes
- Direct volume mounting for seamless deployment to web servers and custom locations
- Configurable build parameters via environment variables in Docker
- Health checks for container monitoring
- Comprehensive Docker documentation (DOCKER.md)

### Changed - Docker Configuration
- Simplified Docker deployment model using direct volume mounting instead of rsync
- Removed SSH and rsync dependencies from Docker container for lighter footprint
- Updated docker-compose.yml with volume mounting examples for different deployment scenarios
- Environment-based configuration for all build parameters in Docker
- Separated local rsync deployment (build.sh) from Docker volume mounting approach

### Added - Performance Optimizations
- Configurable preview image height via `--preview-height` command-line argument
- LCP (Largest Contentful Paint) optimization with `--preload-count` command-line argument
- Performance optimization: Default preview height reduced from 1600px to 400px for faster gallery loading
- Height-based scaling instead of longest-side scaling for more consistent preview sizes
- Preload tags in HTML head for critical above-the-fold images
- High priority fetch for first few images to improve perceived loading speed

### Changed - Performance Updates
- Preview images now scale based on height (400px default) with proportional width
- Build script updated to use optimized 400px preview height and LCP optimization by default
- First few images now use `fetchPriority='high'` and `loading='eager'` for faster above-the-fold loading
- Updated documentation in README.md and CLAUDE.md with new performance optimization options

### Performance Improvements
- ~85-90% reduction in preview file sizes (400px ≈ 30-50KB vs 1600px ≈ 400-450KB per image)
- Significantly improved gallery page load times
- Faster LCP (Largest Contentful Paint) through preloading of critical above-the-fold images
- Improved perceived loading speed with high-priority first images
- Containerized deployment eliminates network transfer overhead for volume-mounted deployments
