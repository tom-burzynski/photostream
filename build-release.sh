#!/bin/bash
# build-release.sh
# Interactive script to create and push a new release

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    print_error "Not in a git repository"
    exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    print_warning "You have uncommitted changes:"
    git status --short
    echo ""
    read -p "Do you want to continue anyway? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Aborting release"
        exit 1
    fi
fi

# Get current branch
CURRENT_BRANCH=$(git branch --show-current)
print_info "Current branch: $CURRENT_BRANCH"

# Get last tag if it exists
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")
print_info "Last tag: $LAST_TAG"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "              Photostream Release Builder"
echo "════════════════════════════════════════════════════════════"
echo ""

# Prompt for version number
while true; do
    echo -e "${BLUE}Enter version number (e.g., 1.0.0):${NC}"
    read -r VERSION

    # Validate version format (basic semver)
    if [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        TAG="v$VERSION"
        break
    else
        print_error "Invalid version format. Please use semantic versioning (e.g., 1.0.0)"
    fi
done

# Check if tag already exists
if git rev-parse "$TAG" >/dev/null 2>&1; then
    print_error "Tag $TAG already exists"
    exit 1
fi

echo ""
print_info "Tag to create: $TAG"

# Prompt for release message
echo ""
echo -e "${BLUE}Enter release message (optional, press Enter to skip):${NC}"
read -r RELEASE_MESSAGE

if [ -z "$RELEASE_MESSAGE" ]; then
    RELEASE_MESSAGE="Release $VERSION"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "              Release Summary"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Version:  $VERSION"
echo "Tag:      $TAG"
echo "Branch:   $CURRENT_BRANCH"
echo "Message:  $RELEASE_MESSAGE"
echo ""

# Confirm release
read -p "Create and push this release? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_info "Release cancelled"
    exit 0
fi

echo ""
print_info "Creating release..."

# Create annotated tag
if git tag -a "$TAG" -m "$RELEASE_MESSAGE"; then
    print_success "Tag $TAG created locally"
else
    print_error "Failed to create tag"
    exit 1
fi

# Push commits to origin
print_info "Pushing commits to origin..."
if git push origin "$CURRENT_BRANCH"; then
    print_success "Commits pushed to origin/$CURRENT_BRANCH"
else
    print_error "Failed to push commits"
    print_warning "You may need to delete the local tag: git tag -d $TAG"
    exit 1
fi

# Push tag to origin
print_info "Pushing tag to origin..."
if git push origin "$TAG"; then
    print_success "Tag $TAG pushed to origin"
else
    print_error "Failed to push tag"
    print_warning "You may need to delete the local tag: git tag -d $TAG"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════"
print_success "Release $VERSION created successfully!"
echo "════════════════════════════════════════════════════════════"
echo ""
print_info "GitHub Actions will now:"
echo "  1. Run tests"
echo "  2. Build Docker images for linux/amd64 and linux/arm64"
echo "  3. Push images to GitHub Container Registry"
echo "  4. Create GitHub release with changelog"
echo ""
print_info "View progress at:"
echo "  https://github.com/$(git config --get remote.origin.url | sed -E 's/.*github\.com[:/](.*)\.git/\1/')/actions"
echo ""
print_info "Once complete, the image will be available at:"
echo "  ghcr.io/$(git config --get remote.origin.url | sed -E 's/.*github\.com[:/](.*)\.git/\1/'):$TAG"
echo "  ghcr.io/$(git config --get remote.origin.url | sed -E 's/.*github\.com[:/](.*)\.git/\1/'):latest"
echo ""
print_success "Done!"
