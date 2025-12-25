# GitHub Actions Workflows

This directory contains CI/CD workflows for the Photostream project.

## Workflows

### 🐳 Docker Build and Push (`docker-build.yml`)

Automatically builds and publishes Docker images to GitHub Container Registry.

**Triggers:**
- New version tags (`v*`) - **Only way to trigger automatic builds**
- Manual workflow dispatch (via Actions tab)

**Platforms:**
- `linux/amd64` (Intel/AMD 64-bit)
- `linux/arm64` (ARM 64-bit, including Apple Silicon)

**Image Tags:**
- `latest` - Latest versioned release
- `v1.2.3` - Semantic version tags
- `v1.2` - Major.minor version
- `v1` - Major version only

**Registry:** `ghcr.io/[owner]/photostream`

**Usage:**
```bash
# Pull latest image
docker pull ghcr.io/[owner]/photostream:latest

# Pull specific version
docker pull ghcr.io/[owner]/photostream:v1.0.0

# Run the image
docker run -d \
  -p 8080:8080 \
  -v ./originals:/app/originals \
  -v ./site:/app/site \
  -e GEOCODE=true \
  ghcr.io/[owner]/photostream:latest
```

### ✅ Test (`test.yml`)

Runs automated tests on all pull requests and pushes.

**Test Suite:**
1. **Python Syntax Check** - Validates `build.py` syntax
2. **Dependency Installation** - Tests pip requirements
3. **Docker Build** - Ensures Dockerfile builds successfully
4. **Container Startup** - Verifies container runs without errors
5. **ShellCheck** - Lints bash scripts for common issues

**Triggers:**
- Push to `main` branch
- Pull requests to `main` branch

## Setting Up CI/CD

### Prerequisites

1. **Enable GitHub Actions** in repository settings
2. **Enable GitHub Packages** (Container Registry)
3. **Set repository visibility** appropriately for image access

### Permissions

The workflows use `GITHUB_TOKEN` with these permissions:
- `contents: read` - Checkout repository
- `packages: write` - Push to GitHub Container Registry

These are automatically provided by GitHub Actions.

### Creating Releases

To create a new release and trigger image builds:

```bash
# Tag a new version
git tag -a v1.0.0 -m "Release version 1.0.0"

# Push tag to GitHub
git push origin v1.0.0
```

This will trigger the workflow and create:
- `ghcr.io/[owner]/photostream:latest`
- `ghcr.io/[owner]/photostream:v1.0.0`
- `ghcr.io/[owner]/photostream:v1.0`
- `ghcr.io/[owner]/photostream:v1`

### Using GitHub Container Registry Images

**Public Access:**
```bash
# No authentication needed for public repositories
docker pull ghcr.io/[owner]/photostream:latest
```

**Private Access:**
```bash
# Create a personal access token with read:packages scope
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull the image
docker pull ghcr.io/[owner]/photostream:latest
```

### Docker Compose with GitHub Registry

Update your `docker-compose.yml`:

```yaml
services:
  photostream:
    image: ghcr.io/[owner]/photostream:latest
    # ... rest of configuration
```

Then run:
```bash
docker-compose pull  # Pull latest image
docker-compose up -d # Start services
```

## Manual Workflow Dispatch

You can manually trigger the Docker build workflow:

1. Go to **Actions** tab in GitHub
2. Select **Build and Push Docker Image**
3. Click **Run workflow**
4. Choose branch and run

## Monitoring Builds

- **Actions Tab**: View all workflow runs
- **Packages**: See published container images
- **Build Summary**: Each successful build includes a summary with pull commands

## Troubleshooting

**Build fails on multi-platform:**
- Check if base image supports both amd64 and arm64
- Verify QEMU is properly set up (handled by `setup-buildx-action`)

**Cannot push to registry:**
- Verify `packages: write` permission is enabled
- Check repository settings allow GitHub Actions

**Tests fail:**
- Review test logs in Actions tab
- Run tests locally: `python3 -m py_compile build.py`
- Check ShellCheck output: `shellcheck docker-watcher.sh`
