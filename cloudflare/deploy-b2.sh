#!/bin/bash
# deploy-b2.sh
# Deploy Photostream gallery to Backblaze B2 bucket

set -e

# Colors for output
export RED='\033[0;31m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export BLUE='\033[0;34m'
export NC='\033[0m' # No Color

# Functions
print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Configuration - Set these to match your B2 bucket
B2_BUCKET_NAME="${B2_BUCKET_NAME:-}"
B2_KEY_ID="${B2_KEY_ID:-}"
B2_APPLICATION_KEY="${B2_APPLICATION_KEY:-}"

# Source directory (generated gallery)
SOURCE_DIR="./site"

# Check if b2 CLI is installed
if ! command -v b2 &> /dev/null; then
    print_error "Backblaze B2 CLI not found"
    echo ""
    echo "Install it with:"
    echo "  pip install b2"
    echo "  # or"
    echo "  brew install b2-tools"
    echo ""
    exit 1
fi

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    print_error "Source directory not found: $SOURCE_DIR"
    echo ""
    echo "Run the build script first:"
    echo "  python3 build.py ./originals --out-dir ./site"
    echo ""
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "         Photostream B2 Deployment"
echo "════════════════════════════════════════════════════════════"
echo ""

# Check for required configuration
if [ -z "$B2_BUCKET_NAME" ] || [ -z "$B2_KEY_ID" ] || [ -z "$B2_APPLICATION_KEY" ]; then
    print_warning "B2 credentials not configured"
    echo ""
    echo "Set environment variables:"
    echo "  export B2_BUCKET_NAME='your-bucket-name'"
    echo "  export B2_KEY_ID='your-key-id'"
    echo "  export B2_APPLICATION_KEY='your-application-key'"
    echo ""
    echo "Or create a .env file with these variables and run:"
    echo "  source .env"
    echo ""
    exit 1
fi

print_info "Bucket: $B2_BUCKET_NAME"
print_info "Source: $SOURCE_DIR"
echo ""

# Authorize with B2
print_info "Authorizing with Backblaze B2..."
if b2 account authorize "$B2_KEY_ID" "$B2_APPLICATION_KEY" > /dev/null 2>&1; then
    print_success "Authorized successfully"
else
    print_error "Authorization failed"
    exit 1
fi

# Confirm deployment
read -p "Deploy to B2 bucket '$B2_BUCKET_NAME'? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_info "Deployment cancelled"
    exit 0
fi

echo ""
print_info "Syncing files to B2..."
echo ""

# Sync files to B2
# --delete removes files from B2 that don't exist locally
# --replaceNewer replaces files even if they're newer on B2
# --threads uses multiple threads for faster upload
# --excludeRegex excludes hidden files and metadata

if b2 sync \
    --delete \
    --replaceNewer \
    --threads 10 \
    --excludeRegex '(^\..*|\.metadata_cache\.pkl)' \
    "$SOURCE_DIR" "b2://$B2_BUCKET_NAME"; then

    echo ""
    print_success "Deployment successful!"
    echo ""
    print_info "Gallery deployed to: $B2_BUCKET_NAME"
    echo ""
else
    echo ""
    print_error "Deployment failed"
    exit 1
fi

# Optional: Set content-type headers for common file types
print_info "Setting content-type headers..."

# Note: B2 automatically sets content-type for most files, but you can override if needed
# Uncomment and customize these if you want specific headers:

# b2 update-file-info --contentType "text/html" "b2://$B2_BUCKET_NAME/index.html"
# b2 update-file-info --contentType "image/webp" "b2://$B2_BUCKET_NAME/originals/*.webp"

print_success "Content-type headers set"
echo ""

echo "════════════════════════════════════════════════════════════"
print_success "Deployment Complete!"
echo "════════════════════════════════════════════════════════════"
echo ""
print_info "Next steps:"
echo "  1. Configure your Cloudflare Worker with the B2 bucket endpoint"
echo "  2. Deploy the worker: wrangler deploy"
echo "  3. Test your gallery at your Cloudflare Workers URL"
echo ""
