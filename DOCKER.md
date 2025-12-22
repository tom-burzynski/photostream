# Docker Deployment for Photostream

This document explains how to deploy photostream using Docker with automatic file watching and rebuilding.

## Quick Start

1. **Build and run with docker-compose:**
```bash
docker-compose up -d
```

2. **Add photos to your originals folder:**
```bash
# Photos will be automatically processed when added
cp /path/to/photos/* ./originals/
```

3. **View generated site:**
The processed gallery will be available in the `./site` directory.

## Configuration

### Environment Variables

Configure the container behavior using environment variables in `docker-compose.yml`:

#### Gallery Build Settings
- `PREVIEW_HEIGHT=400` - Maximum height for preview images (default: 400)
- `PRELOAD_COUNT=20` - Number of images to preload for LCP optimization (default: 20)
- `WORKERS=4` - Number of worker threads for processing (default: 4)

Note: Gallery row height is controlled by CSS (40vh by default). Edit `templates/index.html` to customize.

#### File Watcher Settings
- `WATCH_DELAY=5` - Seconds to wait after detecting file changes (default: 5)
- `RUN_ON_STARTUP=true` - Build gallery when container starts (default: true)
- `LOG_LEVEL=INFO` - Logging level (default: INFO)

#### Automatic Deployment (Optional)
- `RSYNC_ENABLED=false` - Enable automatic rsync deployment (default: false)
- `RSYNC_DESTINATION=""` - Target for rsync (e.g., "user@server.com:/var/www/gallery")
- `RSYNC_OPTIONS="-avu --progress --delete"` - Rsync command options

### Volume Mappings

The container expects these volumes to be mounted:

- `./originals:/app/originals:ro` - Source photos directory (read-only)
- `./site:/app/site` - Generated gallery output directory
- `./ssh:/app/ssh:ro` - SSH keys for rsync deployment (optional)

## Deployment Examples

### Basic Local Development
```yaml
version: '3.8'
services:
  photostream:
    build: .
    volumes:
      - ./originals:/app/originals:ro
      - ./site:/app/site
    environment:
      - PREVIEW_HEIGHT=400
      - WORKERS=4
```

### Production with Auto-Deploy
```yaml
version: '3.8'
services:
  photostream:
    build: .
    volumes:
      - ./originals:/app/originals:ro
      - ./site:/app/site
      - ./ssh:/app/ssh:ro
    environment:
      - PREVIEW_HEIGHT=350
      - WORKERS=8
      - RSYNC_ENABLED=true
      - RSYNC_DESTINATION=user@myserver.com:/var/www/gallery
```

## SSH Key Setup for Auto-Deploy

If using rsync deployment, place your SSH private key in the `./ssh` directory:

```bash
mkdir -p ssh
cp ~/.ssh/id_rsa ssh/
cp ~/.ssh/known_hosts ssh/
chmod 600 ssh/id_rsa
```

## Building the Image

### Local Build
```bash
docker build -t photostream .
```

### Using Docker Compose
```bash
docker-compose build
```

## Container Management

### View Logs
```bash
docker-compose logs -f photostream
```

### Restart Container
```bash
docker-compose restart photostream
```

### Stop Container
```bash
docker-compose down
```

### Manual Gallery Rebuild
```bash
docker-compose exec photostream python3 build.py /app/originals --out-dir /app/site
```

## File Watching Behavior

The container monitors `/app/originals` for:
- New image files added (`close_write`, `moved_to` events)
- Image files deleted (`delete` event)

**Supported image formats:** JPG, JPEG, PNG, GIF, WebP, TIF, TIFF, BMP, HEIC, HEIF

**Processing flow:**
1. File change detected → Wait for stability (WATCH_DELAY seconds)
2. Build gallery if images are present
3. Deploy via rsync (if enabled)
4. Log results

## Deployment Platforms

This Docker setup works on:

- **Local development** with Docker Desktop
- **VPS/Cloud servers** (DigitalOcean, Linode, AWS EC2)
- **Container platforms** (AWS ECS, Azure Container Instances)
- **Home servers** with Docker support
- **NAS devices** with Docker (Synology, QNAP)

## Troubleshooting

### Container won't start
- Check volume paths exist: `mkdir -p originals site ssh`
- Verify permissions on mounted directories
- Check logs: `docker-compose logs photostream`

### File changes not detected
- Ensure originals volume is mounted correctly
- Check file permissions (container runs as root)
- Verify supported image file extensions

### Rsync deployment fails
- Verify SSH keys are mounted and have correct permissions
- Test SSH connection: `docker-compose exec photostream ssh user@host`
- Check RSYNC_DESTINATION format

### Build failures
- Check available disk space in site volume
- Monitor memory usage with high WORKERS setting
- Verify image files aren't corrupted

## Performance Tuning

- **WORKERS**: Set to number of CPU cores for optimal processing
- **PREVIEW_HEIGHT**: Lower values = smaller files, faster loading (recommended: 300-400px)
- **WATCH_DELAY**: Increase for batch uploads to avoid multiple rebuilds
- **Volume placement**: Use SSD storage for better I/O performance