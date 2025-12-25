#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import re
import unicodedata
import html
import os
import sys
import shutil
import hashlib
import pickle
import time
import urllib.request
import urllib.parse
from pathlib import Path
from PIL import Image, ExifTags, ImageOps
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List, Tuple, Any
from functools import lru_cache
try:
    from jinja2 import Environment, DictLoader, select_autoescape
    _HAS_JINJA2 = True
except Exception:
    from string import Template as _StrTemplate
    _HAS_JINJA2 = False

# Optional HEIC/HEIF (iPhone) support
try:
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()
except Exception:
    pass

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".tif", ".tiff", ".bmp", ".heic", ".heif"
}
EXIF_TAGS = {v: k for k, v in ExifTags.TAGS.items()}
PREF_DT_TAGS = [
    EXIF_TAGS.get("DateTimeOriginal"),
    EXIF_TAGS.get("DateTimeDigitized"),
    EXIF_TAGS.get("DateTime"),
]

# Default max height for grid preview images (in pixels) - width will be proportional
DEFAULT_PREVIEW_HEIGHT = 400

# WebP conversion quality settings
WEBP_QUALITY = 90  # 0-100, higher is better quality but larger file size
WEBP_METHOD = 6    # 0-6, higher is slower but better compression

# Color extraction settings
COLOR_BG_FACTOR = 0.3      # Multiplier for background darkness (30% of average)
COLOR_ACCENT_FACTOR = 0.6  # Multiplier for accent color brightness (60% of average)
COLOR_BRIGHTNESS_THRESHOLD = 128  # Threshold for choosing light/dark text

# Geocoding settings
GEOCODE_TIMEOUT = 5  # Timeout in seconds for geocoding API requests
GEOCODE_USER_AGENT = 'photostream/1.0'

class MetadataCache:
    """Persistent cache for image metadata to avoid repeated operations."""
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_file = cache_dir / ".metadata_cache.pkl"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache = self._load_cache()
        self._dirty = False
    
    def _load_cache(self) -> Dict[str, Any]:
        """Load cache from disk or create empty cache."""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'rb') as f:
                    return pickle.load(f)
        except Exception:
            pass
        return {}
    
    def save_cache(self) -> None:
        """Save cache to disk if dirty."""
        if self._dirty:
            try:
                with open(self.cache_file, 'wb') as f:
                    pickle.dump(self._cache, f)
                self._dirty = False
            except Exception:
                pass
    
    def _get_cache_key(self, image_path: Path) -> str:
        """Generate cache key based on filename, size, and modification time (path-independent)."""
        try:
            stat = image_path.stat()
            # Use only filename (not full path) to make cache portable between environments
            return f"{image_path.name}:{stat.st_size}:{stat.st_mtime}"
        except Exception:
            return str(image_path.name)
    
    def get_datetime(self, image_path: Path) -> Optional[dt.datetime]:
        """Get cached datetime or None if not cached/invalid."""
        key = f"datetime:{self._get_cache_key(image_path)}"
        return self._cache.get(key)
    
    def set_datetime(self, image_path: Path, datetime_val: dt.datetime) -> None:
        """Cache datetime value."""
        key = f"datetime:{self._get_cache_key(image_path)}"
        self._cache[key] = datetime_val
        self._dirty = True
    
    def get_dimensions(self, image_path: Path) -> Optional[Tuple[int, int]]:
        """Get cached dimensions or None if not cached/invalid."""
        key = f"dimensions:{self._get_cache_key(image_path)}"
        return self._cache.get(key)
    
    def set_dimensions(self, image_path: Path, dimensions: Tuple[int, int]) -> None:
        """Cache dimensions value."""
        key = f"dimensions:{self._get_cache_key(image_path)}"
        self._cache[key] = dimensions
        self._dirty = True
    
    def get_preview_hash(self, image_path: Path) -> Optional[str]:
        """Get cached preview hash or None if not cached/invalid."""
        key = f"preview_hash:{self._get_cache_key(image_path)}"
        return self._cache.get(key)
    
    def set_preview_hash(self, image_path: Path, hash_val: str) -> None:
        """Cache preview hash value."""
        key = f"preview_hash:{self._get_cache_key(image_path)}"
        self._cache[key] = hash_val
        self._dirty = True
    
    def get_colors(self, image_path: Path) -> Optional[Dict[str, str]]:
        """Get cached color data or None if not cached/invalid."""
        key = f"colors:{self._get_cache_key(image_path)}"
        return self._cache.get(key)
    
    def set_colors(self, image_path: Path, colors: Dict[str, str]) -> None:
        """Cache color data."""
        key = f"colors:{self._get_cache_key(image_path)}"
        self._cache[key] = colors
        self._dirty = True

    def get_gps(self, image_path: Path) -> Optional[Tuple[float, float]]:
        """Get cached GPS coordinates or None if not cached/invalid."""
        key = f"gps:{self._get_cache_key(image_path)}"
        return self._cache.get(key)

    def set_gps(self, image_path: Path, gps: Optional[Tuple[float, float]]) -> None:
        """Cache GPS coordinates."""
        key = f"gps:{self._get_cache_key(image_path)}"
        self._cache[key] = gps
        self._dirty = True

    def get_location(self, image_path: Path) -> Optional[Dict[str, str]]:
        """Get cached location data or None if not cached/invalid."""
        key = f"location:{self._get_cache_key(image_path)}"
        return self._cache.get(key)

    def set_location(self, image_path: Path, location: Optional[Dict[str, str]]) -> None:
        """Cache location data (city, country, etc)."""
        key = f"location:{self._get_cache_key(image_path)}"
        self._cache[key] = location
        self._dirty = True

    def cleanup_stale_entries(self, valid_paths: List[Path]) -> None:
        """Remove cache entries for files that no longer exist."""
        valid_keys = set()
        for path in valid_paths:
            cache_key = self._get_cache_key(path)
            valid_keys.add(f"datetime:{cache_key}")
            valid_keys.add(f"dimensions:{cache_key}")
            valid_keys.add(f"preview_hash:{cache_key}")
            valid_keys.add(f"colors:{cache_key}")
            valid_keys.add(f"gps:{cache_key}")
            valid_keys.add(f"location:{cache_key}")
        
        stale_keys = [key for key in self._cache.keys() if key not in valid_keys]
        if stale_keys:
            for key in stale_keys:
                del self._cache[key]
            self._dirty = True


class ImageMetadata:
    """Handles image metadata extraction and datetime parsing with caching."""
    
    def __init__(self, cache: Optional[MetadataCache] = None):
        self.cache = cache
    
    @staticmethod
    @lru_cache(maxsize=1000)
    def slugify(text: str) -> str:
        """Convert text to URL-safe slug (cached)."""
        s = unicodedata.normalize("NFKD", text)
        s = s.encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-._")
        return s or "photo"
    
    @staticmethod
    def find_images(root: Path) -> List[Path]:
        """Find all image files recursively."""
        return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]

    def rename_by_datetime(self, image_path: Path) -> Optional[Path]:
        """
        Rename image file based on EXIF datetime.
        Format: YYYY-MM-DD-HH-MM-SS.ext
        Returns new path if renamed, None if skipped or failed.
        """
        try:
            # Extract datetime from EXIF
            datetime_val = self.extract_datetime(image_path)

            # Generate new filename
            new_name = datetime_val.strftime("%Y-%m-%d-%H-%M-%S") + image_path.suffix.lower()
            new_path = image_path.parent / new_name

            # Skip if already has correct name
            if image_path == new_path:
                return None

            # Handle name collision
            if new_path.exists():
                # Add counter suffix
                counter = 1
                while new_path.exists():
                    new_name = datetime_val.strftime("%Y-%m-%d-%H-%M-%S") + f"-{counter}" + image_path.suffix.lower()
                    new_path = image_path.parent / new_name
                    counter += 1

            # Rename the file
            image_path.rename(new_path)
            return new_path

        except Exception as e:
            print(f"Warning: Could not rename {image_path.name}: {e}", file=sys.stderr)
            return None
    
    def extract_datetime(self, image_path: Path) -> dt.datetime:
        """Prefer EXIF DateTimeOriginal; fall back to file mtime (cached)."""
        # Check cache first
        if self.cache:
            cached = self.cache.get_datetime(image_path)
            if cached is not None:
                return cached
        
        # Extract datetime
        datetime_val = self._extract_datetime_uncached(image_path)
        
        # Cache the result
        if self.cache:
            self.cache.set_datetime(image_path, datetime_val)
        
        return datetime_val
    
    def _extract_datetime_uncached(self, image_path: Path) -> dt.datetime:
        """Extract datetime without caching."""
        try:
            with Image.open(image_path) as im:
                exif = im.getexif()
                if exif:
                    for tag in PREF_DT_TAGS:
                        if not tag:
                            continue
                        val = exif.get(tag)
                        if not val:
                            continue
                        s = str(val).replace("\x00", "").split(".")[0]
                        # "YYYY:MM:DD HH:MM:SS" -> "YYYY-MM-DD HH:MM:SS"
                        if len(s) >= 10 and s[4] == ":" and s[7] == ":":
                            s = f"{s[:4]}-{s[5:7]}-{s[8:10]}{s[10:]}"
                        try:
                            return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            try:
                                return dt.datetime.strptime(s[:10], "%Y-%m-%d")
                            except Exception:
                                continue
        except Exception:
            pass
        return dt.datetime.fromtimestamp(image_path.stat().st_mtime)
    
    def extract_gps(self, image_path: Path) -> Optional[Tuple[float, float]]:
        """Extract GPS coordinates from EXIF data (latitude, longitude) (cached)."""
        # Check cache first
        if self.cache:
            cached = self.cache.get_gps(image_path)
            if cached is not None:
                return cached

        # Extract GPS
        gps_coords = self._extract_gps_uncached(image_path)

        # Cache the result
        if self.cache:
            self.cache.set_gps(image_path, gps_coords)

        return gps_coords

    def _extract_gps_uncached(self, image_path: Path) -> Optional[Tuple[float, float]]:
        """Extract GPS coordinates without caching."""
        try:
            with Image.open(image_path) as im:
                exif = im.getexif()
                if not exif:
                    return None

                # GPS info is stored in tag 34853 (GPSInfo)
                gps_info = exif.get_ifd(0x8825)
                if not gps_info:
                    return None

                # Extract GPS coordinates
                # GPSLatitude = 2, GPSLatitudeRef = 1
                # GPSLongitude = 4, GPSLongitudeRef = 3
                lat_data = gps_info.get(2)
                lat_ref = gps_info.get(1)
                lon_data = gps_info.get(4)
                lon_ref = gps_info.get(3)

                if not all([lat_data, lat_ref, lon_data, lon_ref]):
                    return None

                # Convert to decimal degrees
                def to_decimal(coords, ref):
                    degrees = float(coords[0])
                    minutes = float(coords[1]) if len(coords) > 1 else 0.0
                    seconds = float(coords[2]) if len(coords) > 2 else 0.0
                    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
                    if ref in ['S', 'W']:
                        decimal = -decimal
                    return decimal

                latitude = to_decimal(lat_data, lat_ref)
                longitude = to_decimal(lon_data, lon_ref)

                return (latitude, longitude)
        except Exception as e:
            # Silently fail - GPS data is optional
            return None
        return None

    def get_image_dimensions(self, image_path: Path) -> Tuple[int, int]:
        """Extract image dimensions without loading the full image (cached)."""
        # Check cache first
        if self.cache:
            cached = self.cache.get_dimensions(image_path)
            if cached is not None:
                return cached
        
        # Extract dimensions
        dimensions = self._get_dimensions_uncached(image_path)
        
        # Cache the result
        if self.cache:
            self.cache.set_dimensions(image_path, dimensions)
        
        return dimensions
    
    def _get_dimensions_uncached(self, image_path: Path) -> Tuple[int, int]:
        """Extract dimensions without caching."""
        try:
            with Image.open(image_path) as im:
                return im.size
        except Exception:
            return (1, 1)

def geocode_coordinates(lat: float, lon: float, timeout: int = GEOCODE_TIMEOUT) -> Optional[Dict[str, str]]:
    """
    Reverse geocode GPS coordinates to city/country using Nominatim API with Photon fallback.
    Returns dict with 'city' and 'country' keys, or None if geocoding fails.
    """
    # Try Nominatim first
    try:
        params = urllib.parse.urlencode({'format': 'json', 'lat': lat, 'lon': lon})
        url = f"https://nominatim.openstreetmap.org/reverse?{params}"

        req = urllib.request.Request(url, headers={'User-Agent': GEOCODE_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))

            # Extract location from address field
            if data.get('address'):
                address = data['address']

                # Try to get city (prefer 'city', fall back to 'town', 'village', 'county', or 'state')
                city = (address.get('city') or address.get('town') or
                       address.get('village') or address.get('county') or address.get('state'))
                country = address.get('country')

                if city or country:
                    return {
                        'city': city or 'Unknown',
                        'country': country or 'Unknown'
                    }
    except Exception:
        pass  # Fall through to Photon fallback

    # Fallback to Photon if Nominatim fails
    try:
        params = urllib.parse.urlencode({'lat': lat, 'lon': lon})
        url = f"https://photon.komoot.io/reverse?{params}"

        req = urllib.request.Request(url, headers={'User-Agent': GEOCODE_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))

            # Extract location from first feature
            if data.get('features') and len(data['features']) > 0:
                props = data['features'][0].get('properties', {})

                # Try to get city (prefer 'city', fall back to 'name', 'county', or 'state')
                city = props.get('city') or props.get('name') or props.get('county') or props.get('state')
                country = props.get('country')

                if city or country:
                    return {
                        'city': city or 'Unknown',
                        'country': country or 'Unknown'
                    }

        return None
    except Exception:
        # Silently fail - geocoding is optional
        return None


@dataclass(frozen=True)
class Config:
    source_dir: Path
    out_dir: Path
    max_preview_height: int = DEFAULT_PREVIEW_HEIGHT
    preload_count: int = 20
    workers: int = 4
    geocode: bool = False
    regeocode: bool = False
    title: str = "[photostream]"
    description: str = ""
    footer: str = ""
    link1_title: str = ""
    link1_url: str = ""
    link2_title: str = ""
    link2_url: str = ""
    link3_title: str = ""
    link3_url: str = ""

    def __post_init__(self):
        if not self.source_dir.exists():
            raise ValueError(f"Source directory does not exist: {self.source_dir}")
        if self.max_preview_height <= 0:
            raise ValueError(f"Max preview height must be positive: {self.max_preview_height}")
        if self.workers <= 0:
            object.__setattr__(self, 'workers', os.cpu_count() or 4)
        if self.regeocode and not self.geocode:
            raise ValueError("--regeocode requires --geocode to be enabled")

# Path policy: everything relative to cfg.out_dir

class PreviewGenerator:
    """Handles image preview generation and processing with content-based caching."""
    
    def __init__(self, config: Config, cache: Optional[MetadataCache] = None):
        self.config = config
        self.cache = cache
    
    @staticmethod
    def rel_to_out(path: Path, out_dir: Path) -> str:
        """Convert path to relative path from output directory."""
        try:
            return path.relative_to(out_dir).as_posix()
        except Exception:
            return Path(os.path.relpath(path, start=out_dir)).as_posix()
    
    @staticmethod
    def stable_slug_for(image_path: Path, root: Path) -> str:
        """Return a stable per-file page slug of the form "{stem}-{hash8}.html".
        The hash is derived from the file's path relative to the source root, so it
        remains consistent across runs and avoids sequential prefixes.
        """
        try:
            rel = image_path.relative_to(root)
        except Exception:
            rel = Path(image_path.name)
        stem = ImageMetadata.slugify(image_path.stem)
        h = hashlib.sha1(str(rel).encode("utf-8")).hexdigest()[:8]
        return f"{stem}-{h}.html"
    
    @staticmethod
    def strip_all_metadata(im: Image.Image) -> Image.Image:
        """Return a copy of the image with EXIF/GPS/IPTC/XMP/ICC removed.
        This avoids leaking identifying information in saved outputs.
        """
        im2 = im.copy()
        # Common metadata keys Pillow may carry around in `info`
        for k in ("exif", "icc_profile", "XMP", "xml", "iptc", "photoshop", "APP1", "APP13"):
            try:
                im2.info.pop(k, None)
            except Exception:
                pass
        return im2
    
    @staticmethod
    def extract_colors(im: Image.Image) -> Dict[str, str]:
        """Extract dominant colors from image for background and accent colors.
        Returns dict with 'bg_color', 'accent_color', and 'text_color'.
        """
        try:
            # Convert to RGB if needed
            if im.mode != "RGB":
                im = im.convert("RGB")
            
            # Resize to small image for faster processing
            thumb = im.copy()
            thumb.thumbnail((100, 100), Image.LANCZOS)
            
            # Simple sampling approach: get pixels from center region
            w, h = thumb.size
            center_x, center_y = w // 2, h // 2
            sample_size = min(w, h) // 4  # Sample from center quarter
            
            # Extract color samples from center region
            colors = []
            for x in range(max(0, center_x - sample_size), min(w, center_x + sample_size), 3):
                for y in range(max(0, center_y - sample_size), min(h, center_y + sample_size), 3):
                    r, g, b = thumb.getpixel((x, y))
                    colors.append((r, g, b))
            
            if not colors:
                return {"bg_color": "#000000", "accent_color": "#333333", "text_color": "#ffffff"}
            
            # Find average color for background
            avg_r = sum(c[0] for c in colors) // len(colors)
            avg_g = sum(c[1] for c in colors) // len(colors)
            avg_b = sum(c[2] for c in colors) // len(colors)
            
            # Create darker background variant
            bg_r = max(0, int(avg_r * COLOR_BG_FACTOR))
            bg_g = max(0, int(avg_g * COLOR_BG_FACTOR))
            bg_b = max(0, int(avg_b * COLOR_BG_FACTOR))

            # Create accent color (slightly lighter)
            accent_r = min(255, int(avg_r * COLOR_ACCENT_FACTOR))
            accent_g = min(255, int(avg_g * COLOR_ACCENT_FACTOR))
            accent_b = min(255, int(avg_b * COLOR_ACCENT_FACTOR))

            # Determine text color based on background brightness
            brightness = (bg_r * 299 + bg_g * 587 + bg_b * 114) / 1000
            text_color = "#ffffff" if brightness < COLOR_BRIGHTNESS_THRESHOLD else "#000000"
            
            return {
                "bg_color": f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}",
                "accent_color": f"#{accent_r:02x}{accent_g:02x}{accent_b:02x}",
                "text_color": text_color
            }
            
        except Exception:
            # Fallback colors
            return {"bg_color": "#000000", "accent_color": "#333333", "text_color": "#ffffff"}
    
    def _get_content_hash(self, src: Path) -> str:
        """Generate content-based hash for cache invalidation."""
        try:
            # Use file size, mtime, and first 1KB for fast hashing
            stat = src.stat()
            hasher = hashlib.sha256()
            hasher.update(f"{src}:{stat.st_size}:{stat.st_mtime}".encode())
            
            # Add some file content for better cache invalidation
            with open(src, 'rb') as f:
                hasher.update(f.read(1024))
            
            return hasher.hexdigest()[:16]
        except Exception:
            return str(abs(hash(src)) & 0xffffffff)
    
    def generate_preview(self, src: Path, previews_dir: Path, image_metadata: Optional[ImageMetadata] = None) -> Tuple[Path, int, int, Dict[str, str]]:
        """Create or reuse a WebP preview for `src` under `previews_dir`.
        Returns (preview_path, width, height, colors) with colors dict containing bg_color, accent_color, text_color.
        """
        # Get original dimensions (potentially cached)
        if image_metadata:
            w, h = image_metadata.get_image_dimensions(src)
        else:
            w, h = (1, 1)
            try:
                with Image.open(src) as im:
                    w, h = im.size
            except Exception:
                pass
        
        # Use content-based hash for better cache invalidation
        content_hash = self._get_content_hash(src)

        # Determine output path with content hash (no height in filename to keep it simple)
        base = f"{ImageMetadata.slugify(src.stem)}-{content_hash}"
        out = previews_dir / f"{base}.webp"

        # Check cache - only regenerate if source changed (content_hash differs)
        if self.cache:
            cached_hash = self.cache.get_preview_hash(src)
            cached_colors = self.cache.get_colors(src)
            if cached_hash == content_hash and cached_colors and out.exists():
                # Cache hit and file exists - reuse it
                return (out, w, h, cached_colors)
        
        # Generate preview and extract colors
        colors = {"bg_color": "#000000", "accent_color": "#333333", "text_color": "#ffffff"}
        try:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                
                # Extract colors from original image before resizing
                colors = self.extract_colors(im)
                
                pw, ph = im.size
                # Scale based on height for consistent gallery loading
                scale = min(1.0, self.config.max_preview_height / float(ph)) if self.config.max_preview_height > 0 else 1.0
                new_w = max(1, int(round(pw * scale)))
                new_h = max(1, int(round(ph * scale)))
                if (new_w, new_h) != (pw, ph):
                    im = im.resize((new_w, new_h), Image.LANCZOS)
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                # Strip all metadata to avoid leaking EXIF/GPS/etc in previews
                im = self.strip_all_metadata(im)
                out.parent.mkdir(parents=True, exist_ok=True)
                im.save(out, format="WEBP", quality=80, optimize=True, method=6)

                # Cache the hash and colors
                if self.cache:
                    self.cache.set_preview_hash(src, content_hash)
                    self.cache.set_colors(src, colors)
                    
        except Exception:
            # Fall back to original path if anything goes wrong
            return (src, w, h, colors)
        return (out, w, h, colors)
    
    def convert_to_webp(self, src: Path, dst: Path) -> bool:
        """Convert image to WebP format with metadata stripped."""
        try:
            needs = (not dst.exists()) or (dst.stat().st_mtime < src.stat().st_mtime)
        except Exception:
            needs = True
        
        if needs:
            try:
                with Image.open(src) as im:
                    im = ImageOps.exif_transpose(im)
                    if im.mode not in ("RGB", "L"):
                        im = im.convert("RGB")
                    # Strip all metadata so the WebP contains no identifying data
                    im = self.strip_all_metadata(im)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    im.save(dst, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
                return True
            except Exception:
                # If conversion fails, do not leak the original with metadata
                return False
        return True

    def copy_favicon(self, out_dir: Path) -> None:
        """Copy favicon.svg (sibling to this script) into the site output folder.
        If the source doesn't exist, do nothing silently.
        """
        try:
            script_dir = Path(__file__).resolve().parent
        except Exception:
            script_dir = Path.cwd()
        src = script_dir / "favicon.svg"
        if not src.exists():
            return
        dst = out_dir / "favicon.svg"
        try:
            if (not dst.exists()) or (dst.stat().st_mtime < src.stat().st_mtime):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except Exception:
            # Non-fatal if copy fails
            pass



@dataclass
class IndexPageContext:
    """Context data for rendering the index page."""
    photos_json: str
    month_data: str = "[]"
    preload_images: List[Dict[str, Any]] = None
    preload_count: int = 20
    photos: List[Dict[str, Any]] = None
    title: str = "[photostream]"
    description: str = ""
    footer: str = ""
    link1_title: str = ""
    link1_url: str = ""
    link2_title: str = ""
    link2_url: str = ""
    link3_title: str = ""
    link3_url: str = ""


class TemplateRenderer:
    """Handles HTML template rendering with Jinja2 or string templates as fallback."""

    def __init__(self, template_dir: Optional[Path] = None):
        self.has_jinja2 = _HAS_JINJA2
        self.template_dir = template_dir or self._get_default_template_dir()
        self.templates = self._load_templates()

        if self.has_jinja2:
            self._env = Environment(
                loader=DictLoader(self.templates),
                autoescape=select_autoescape(['html'])
            )
    
    def _get_default_template_dir(self) -> Path:
        """Get default template directory relative to script location."""
        try:
            script_dir = Path(__file__).resolve().parent
            return script_dir / "templates"
        except Exception:
            return Path.cwd() / "templates"
    
    
    def _load_templates(self) -> Dict[str, str]:
        """Load templates from external files."""
        templates = {}
        
        # Load index template
        index_path = self.template_dir / 'index.html'
        if not index_path.exists():
            raise FileNotFoundError(f"Template not found: {index_path}")
        templates['index.html'] = index_path.read_text(encoding='utf-8')
        
        # Load photo template
        photo_path = self.template_dir / 'photo.html'
        if not photo_path.exists():
            raise FileNotFoundError(f"Template not found: {photo_path}")
        templates['photo.html'] = photo_path.read_text(encoding='utf-8')
        
        return templates
    
    def render_index(self, ctx: IndexPageContext) -> str:
        """Render the main index page with photo grid."""
        if self.has_jinja2:
            return self._env.get_template('index.html').render(
                photos_json=ctx.photos_json,
                photos=ctx.photos or [],
                preload_images=ctx.preload_images or [],
                preload_count=ctx.preload_count,
                month_data=ctx.month_data,
                title=ctx.title,
                description=ctx.description,
                footer=ctx.footer,
                link1_title=ctx.link1_title,
                link1_url=ctx.link1_url,
                link2_title=ctx.link2_title,
                link2_url=ctx.link2_url,
                link3_title=ctx.link3_title,
                link3_url=ctx.link3_url
            )
        else:
            # DEPRECATED FALLBACK: Basic string.Template renderer (no Jinja2)
            # WARNING: This fallback has significant limitations:
            #   - No auto-escaping (potential XSS if user content is malicious)
            #   - No preload optimization support
            #   - No conditional logic or loops
            #   - Fragile template string replacement
            # RECOMMENDATION: Install Jinja2 (pip install jinja2) for full functionality
            template_content = self.templates.get('index.html', '')
            # Remove Jinja2-specific syntax for string template
            template_content = (template_content
                .replace('{% if preload_images %}{% for img in preload_images %}<link rel="preload" as="image" href="{{ img.src }}" fetchpriority="high">\n{% endfor %}{% endif %}', '')
                .replace('{{ photos_json | safe }}', '$photos_json')
                .replace('{{ preload_count | default(20) }}', '$preload_count')
                .replace('{{ month_data | safe }}', '$month_data')
                .replace('{{ title }}', '$title')
                .replace('{{ description }}', '$description')
                .replace('{{ footer }}', '$footer')
                .replace('{{ link1_title }}', '$link1_title')
                .replace('{{ link1_url }}', '$link1_url')
                .replace('{{ link2_title }}', '$link2_title')
                .replace('{{ link2_url }}', '$link2_url')
                .replace('{{ link3_title }}', '$link3_title')
                .replace('{{ link3_url }}', '$link3_url')
            )
            t = _StrTemplate(template_content)
            return t.substitute(
                photos_json=ctx.photos_json,
                preload_count=ctx.preload_count,
                month_data=ctx.month_data,
                title=ctx.title,
                description=ctx.description,
                footer=ctx.footer,
                link1_title=ctx.link1_title,
                link1_url=ctx.link1_url,
                link2_title=ctx.link2_title,
                link2_url=ctx.link2_url,
                link3_title=ctx.link3_title,
                link3_url=ctx.link3_url
            )
    
    def render_photo(self, **ctx) -> str:
        """Render individual photo page."""
        if self.has_jinja2:
            return self._env.get_template('photo.html').render(**ctx)
        else:
            mapping = {
                'title': ctx.get('title', ''),
                'prev_page': ctx.get('prev_page', ''),
                'next_page': ctx.get('next_page', ''),
                'prev_id': ctx.get('prev_id', ''),
                'next_id': ctx.get('next_id', ''),
                'anchor_id': ctx.get('anchor_id', ''),
                'img_src': ctx.get('img_src', ''),
                'preview_src': ctx.get('preview_src', ''),
                'img_width': ctx.get('img_width', ''),
                'img_height': ctx.get('img_height', ''),
                'alt': ctx.get('alt', ''),
                'bg_color': ctx.get('bg_color', '#000000'),
                'accent_color': ctx.get('accent_color', '#333333'),
                'text_color': ctx.get('text_color', '#ffffff'),
            }
            t = _StrTemplate(
                PHOTO_TMPL
                .replace('{{ title }}', '$title')
                .replace('{{ prev_page }}', '$prev_page')
                .replace('{{ next_page }}', '$next_page')
                .replace('{{ prev_id }}', '$prev_id')
                .replace('{{ next_id }}', '$next_id')
                .replace('{{ anchor_id }}', '$anchor_id')
                .replace('{{ img_src }}', '$img_src')
                .replace('{{ preview_src }}', '$preview_src')
                .replace('{{ img_width }}', '$img_width')
                .replace('{{ img_height }}', '$img_height')
                .replace('{{ alt }}', '$alt')
                .replace('{{ bg_color }}', '$bg_color')
                .replace('{{ accent_color }}', '$accent_color')
                .replace('{{ text_color }}', '$text_color')
            )
            return t.substitute(**mapping)


class PhotoProcessor:
    """Main class for processing photos and generating the gallery with caching."""
    
    def __init__(self, config: Config, template_dir: Optional[Path] = None):
        self.config = config
        self.cache = MetadataCache(config.out_dir)
        self.image_metadata = ImageMetadata(self.cache)
        self.preview_generator = PreviewGenerator(config, self.cache)
        self.template_renderer = TemplateRenderer(template_dir)
    
    @staticmethod
    def _progress(i: int, n: int, label: str = "") -> None:
        """Display a progress bar."""
        if n <= 0:
            return
        width = 30
        filled = int(width * (i / n))
        bar = "#" * filled + "-" * (width - filled)
        end = "\n" if i >= n else ""
        print(f"\r{label} [{bar}] {i}/{n}", end=end, flush=True)
    
    @staticmethod
    def _format_photo_title(photo_datetime: dt.datetime) -> str:
        """Format photo datetime as '[July 8, 2025 at 12:28pm]'."""
        # Format the date part: "July 8, 2025"
        month = photo_datetime.strftime("%B")
        day = photo_datetime.day
        year = photo_datetime.year
        
        # Format the time part: "12:28pm"
        hour = photo_datetime.hour
        minute = photo_datetime.minute
        ampm = "am" if hour < 12 else "pm"
        if hour == 0:
            display_hour = 12
        elif hour > 12:
            display_hour = hour - 12
        else:
            display_hour = hour
            
        formatted_datetime = f"{month} {day}, {year} at {display_hour}:{minute:02d}{ampm}"
        return f"[{formatted_datetime}]"

    def _generate_month_data(self, meta: List[Dict[str, Any]], datetime_lookup: Dict[Path, dt.datetime]) -> List[Dict[str, Any]]:
        """Generate month/year data for the date picker.
        Returns list of months with first photo ID for scrolling, grouped by year.
        Format: [{"year": 2025, "month": 1, "label": "January 2025", "photo_id": "ph-000001"}, ...]
        """
        month_map = {}  # (year, month) -> first photo id

        for photo in meta:
            original_path = Path(photo["original_path"])
            photo_datetime = datetime_lookup.get(original_path)
            if photo_datetime:
                key = (photo_datetime.year, photo_datetime.month)
                if key not in month_map:
                    month_map[key] = photo["id"]

        # Convert to sorted list (newest first, matching photo order)
        month_list = []
        for (year, month), photo_id in sorted(month_map.items(), reverse=True):
            month_name = dt.datetime(year, month, 1).strftime("%B")
            month_list.append({
                "year": year,
                "month": month,
                "label": f"{month_name} {year}",
                "photo_id": photo_id
            })

        return month_list

    def _process_one_image(self, idx: int, image_path: Path, originals_dir: Path, previews_dir: Path, photo_datetime: dt.datetime) -> Optional[Dict[str, Any]]:
        """Process a single image: convert to WebP, generate preview, extract metadata."""
        try:
            # Determine relative structure under source
            try:
                rel_under_src = image_path.relative_to(self.config.source_dir)
            except Exception:
                rel_under_src = Path(image_path.name)

            # Convert full-size to WebP inside originals/
            dst_full = (originals_dir / rel_under_src).with_suffix(".webp")
            if not self.preview_generator.convert_to_webp(image_path, dst_full):
                return None

            rel_src_full = PreviewGenerator.rel_to_out(dst_full, self.config.out_dir)

            # Generate / reuse preview (WebP) and get original dimensions + colors
            preview_path, w_meta, h_meta, colors = self.preview_generator.generate_preview(
                image_path, previews_dir, self.image_metadata
            )
            rel_src_preview = PreviewGenerator.rel_to_out(preview_path, self.config.out_dir)

            # Use original image dimensions if available
            w = int(w_meta) if isinstance(w_meta, int) and w_meta > 0 else 1
            h = int(h_meta) if isinstance(h_meta, int) and h_meta > 0 else 1

            # Generate timestamp-based ID (YYYYMMDDHHMMSS)
            pid = f"ph-{photo_datetime.strftime('%Y%m%d%H%M%S')}"
            slug = PreviewGenerator.stable_slug_for(image_path, self.config.source_dir)
            page_rel = f"./view/{slug}"

            return {
                "src": rel_src_preview,
                "full": rel_src_full,
                "w": w,
                "h": h,
                "name": image_path.name,
                "id": pid,
                "page": page_rel,
                "slug": slug,
                "bg_color": colors.get("bg_color", "#000000"),
                "accent_color": colors.get("accent_color", "#333333"),
                "text_color": colors.get("text_color", "#ffffff"),
                "original_path": str(image_path),  # Store original path for datetime lookup
            }
        except Exception:
            # Skip this image to avoid referencing originals that may contain metadata
            return None

    def _geocode_images(self, meta: List[Dict[str, Any]]) -> None:
        """Extract GPS coordinates and geocode to city names for all images."""
        geocoded_count = 0
        total = len(meta)

        for idx, m in enumerate(meta, 1):
            original_path = Path(m["original_path"])

            # Check cache first
            location = self.cache.get_location(original_path)

            # If regeocode flag is set, retry only failed geocoding attempts (empty dicts with GPS data)
            should_retry = False
            if self.config.regeocode and location is not None and not location:
                # Empty location dict - check if image has GPS data to retry
                gps = self.image_metadata.extract_gps(original_path)
                should_retry = gps is not None

            if location is not None and not should_retry:
                m["location"] = location
                if location:  # Not None and not empty dict
                    geocoded_count += 1
                # Skip printing for cached entries
                continue

            # Extract GPS coordinates
            gps = self.image_metadata.extract_gps(original_path)
            if gps:
                lat, lon = gps
                retry_msg = " (retrying)" if should_retry else ""
                print(f"  [{idx}/{total}] {original_path.name}: Geocoding {lat:.4f}, {lon:.4f}{retry_msg}...", end='', flush=True)
                # Geocode to city/country
                location = geocode_coordinates(lat, lon)
                if location:
                    m["location"] = location
                    self.cache.set_location(original_path, location)
                    self.cache.save_cache()  # Save after each successful geocode
                    geocoded_count += 1
                    print(f" → {location.get('city', 'Unknown')}", flush=True)
                else:
                    # No location found, cache empty dict to avoid re-querying
                    m["location"] = {}
                    self.cache.set_location(original_path, {})
                    self.cache.save_cache()  # Save to avoid re-querying
                    print(f" → No location found", flush=True)
            else:
                # No GPS data, cache empty dict
                m["location"] = {}
                self.cache.set_location(original_path, {})
                self.cache.save_cache()  # Save to avoid re-processing
                if not should_retry:  # Only print if not a retry attempt
                    print(f"  [{idx}/{total}] {original_path.name}: No GPS data", flush=True)

        print(f"\nGeocoded {geocoded_count} of {total} images.", flush=True)

    def build_gallery(self) -> None:
        """Main method to build the photo gallery."""
        images = ImageMetadata.find_images(self.config.source_dir)
        if not images:
            raise SystemExit(f"No images found in {self.config.source_dir}")
        
        # Clean up stale cache entries
        self.cache.cleanup_stale_entries(images)

        # Sort newest first (using cached datetime extraction)
        print("Extracting image timestamps...", flush=True)
        images_with_dates = [(p, self.image_metadata.extract_datetime(p)) for p in images]
        images_with_dates.sort(key=lambda t: t[1], reverse=True)
        ordered = [p for p, _ in images_with_dates]
        
        # Create a lookup dict for datetime by image path
        datetime_lookup = {p: dt for p, dt in images_with_dates}

        total = len(ordered)
        print(f"Found {total} images. Generating previews (max height {self.config.max_preview_height}px)...", flush=True)

        # Prepare directories
        view_dir = self.config.out_dir / "view"
        view_dir.mkdir(exist_ok=True)
        previews_dir = self.config.out_dir / "previews"
        previews_dir.mkdir(exist_ok=True)
        originals_dir = self.config.out_dir / "originals"
        originals_dir.mkdir(exist_ok=True)

        self.preview_generator.copy_favicon(self.config.out_dir)

        # Process images in parallel
        meta = [None] * total  # type: ignore[list-item]
        print(f"Processing with {self.config.workers} threads...", flush=True)
        with ThreadPoolExecutor(max_workers=self.config.workers) as ex:
            futures = {
                ex.submit(self._process_one_image, idx, p, originals_dir, previews_dir, datetime_lookup[p]): idx
                for idx, p in enumerate(ordered)
            }
            done = 0
            for fut in as_completed(futures):
                idx = futures[fut]
                meta[idx] = fut.result()
                done += 1
                self._progress(done, total, label="Images")

        # Drop any failed items (ensures we never link to unsanitized originals)
        meta = [m for m in meta if m is not None]

        # Handle duplicate timestamp IDs by appending counter
        id_counts: Dict[str, int] = {}
        for m in meta:
            original_id = m["id"]
            if original_id in id_counts:
                id_counts[original_id] += 1
                m["id"] = f"{original_id}-{id_counts[original_id]}"
            else:
                id_counts[original_id] = 0

        # Extract GPS and geocode if enabled
        if self.config.geocode:
            print("Geocoding image locations...", flush=True)
            self._geocode_images(meta)

        print("Writing index and pages...", flush=True)

        # Generate month/year data for date picker
        month_data = self._generate_month_data(meta, datetime_lookup)

        # Write index.html with LCP optimization
        preload_images = meta[:self.config.preload_count] if meta else []
        index_ctx = IndexPageContext(
            photos_json=json.dumps(meta, ensure_ascii=False),
            month_data=json.dumps(month_data, ensure_ascii=False),
            preload_images=preload_images,
            preload_count=self.config.preload_count,
            photos=meta,
            title=self.config.title,
            description=self.config.description,
            footer=self.config.footer,
            link1_title=self.config.link1_title,
            link1_url=self.config.link1_url,
            link2_title=self.config.link2_title,
            link2_url=self.config.link2_url,
            link3_title=self.config.link3_title,
            link3_url=self.config.link3_url
        )
        index_html = self.template_renderer.render_index(index_ctx)
        (self.config.out_dir / "index.html").write_text(index_html, encoding="utf-8")

        # Write per-photo pages
        n = len(meta)
        for i, m in enumerate(meta):
            prev_idx = (i - 1) % n  # wrap-around
            next_idx = (i + 1) % n

            # Look up the datetime for this photo and format the title
            original_path = Path(m["original_path"])
            photo_datetime = datetime_lookup.get(original_path)
            if photo_datetime:
                formatted_title = self._format_photo_title(photo_datetime)
                # Format date and time separately for info overlay
                date_str = photo_datetime.strftime("%B %d, %Y")  # e.g., "July 8, 2025"
                hour = photo_datetime.hour
                minute = photo_datetime.minute
                ampm = "am" if hour < 12 else "pm"
                if hour == 0:
                    display_hour = 12
                elif hour > 12:
                    display_hour = hour - 12
                else:
                    display_hour = hour
                time_str = f"{display_hour}:{minute:02d}{ampm}"  # e.g., "12:28pm"
            else:
                # Fallback to filename if datetime not found
                formatted_title = f"[{m['name']}]"
                date_str = ""
                time_str = ""

            # Extract location info if available
            location = m.get("location", {})
            city = location.get("city", "") if location else ""
            country = location.get("country", "") if location else ""

            html_out = self.template_renderer.render_photo(
                title=html.escape(formatted_title),
                prev_page=f"./{meta[prev_idx]['slug']}",
                next_page=f"./{meta[next_idx]['slug']}",
                prev_id=meta[prev_idx]['id'],
                next_id=meta[next_idx]['id'],
                img_src=f"../{m['full']}",
                preview_src=f"../{m['src']}",
                img_width=m['w'],
                img_height=m['h'],
                alt=html.escape(m["name"]),
                anchor_id=m["id"],
                bg_color=m.get("bg_color", "#000000"),
                accent_color=m.get("accent_color", "#333333"),
                text_color=m.get("text_color", "#ffffff"),
                location_city=city,
                location_country=country,
                photo_date=date_str,
                photo_time=time_str,
            )
            (view_dir / m["slug"]).write_text(html_out, encoding="utf-8")

        # Save cache to disk
        self.cache.save_cache()
        
        print(
            f"Done:\n"
            f"- index.html\n"
            f"- favicon.svg (copied)\n"
            f"- {originals_dir}/* (copied originals)\n"
            f"- {previews_dir}/* (grid previews)\n"
            f"- {view_dir}/* ({n} pages)\n"
            f"- .metadata_cache.pkl (cached metadata)"
        )



def parse_args():
    """Parse command line arguments."""
    ap = argparse.ArgumentParser(
        description="Generate a justified photo gallery with per-photo pages (newest first)."
    )
    ap.add_argument("folder", type=Path, help="Folder containing photos (scanned recursively).")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="Directory to write index.html, previews/, and view/. Defaults to current working directory.")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4,
                    help="Number of worker threads to use for image processing (default: number of CPU cores).")
    ap.add_argument("--template-dir", type=Path, default=None,
                    help="Directory containing custom templates (index.html, photo.html). Defaults to ./templates/")
    ap.add_argument("--preview-height", type=int, default=DEFAULT_PREVIEW_HEIGHT,
                    help=f"Maximum height for preview images in pixels (default: {DEFAULT_PREVIEW_HEIGHT}). Lower values reduce file sizes and improve loading speed.")
    ap.add_argument("--preload-count", type=int, default=20,
                    help="Number of first images to preload for LCP optimization (default: 20). Higher values may slow initial page load.")
    ap.add_argument("--rename", action="store_true",
                    help="Rename image files based on EXIF datetime (format: YYYY-MM-DD-HH-MM-SS.ext) before processing.")
    ap.add_argument("--title", type=str, default="[photostream]",
                    help="Title for the gallery site (default: '[photostream]').")
    ap.add_argument("--description", type=str, default="",
                    help="Description text to display under the title (default: empty).")
    ap.add_argument("--footer", type=str, default="",
                    help="Footer text to display at bottom-right of the page (default: empty).")
    ap.add_argument("--link1-title", type=str, default="",
                    help="Title for first footer link (default: empty).")
    ap.add_argument("--link1-url", type=str, default="",
                    help="URL for first footer link (default: empty).")
    ap.add_argument("--link2-title", type=str, default="",
                    help="Title for second footer link (default: empty).")
    ap.add_argument("--link2-url", type=str, default="",
                    help="URL for second footer link (default: empty).")
    ap.add_argument("--link3-title", type=str, default="",
                    help="Title for third footer link (default: empty).")
    ap.add_argument("--link3-url", type=str, default="",
                    help="URL for third footer link (default: empty).")
    ap.add_argument("--geocode", action="store_true",
                    help="Enable reverse geocoding to extract city names from GPS coordinates (requires internet connection).")
    ap.add_argument("--regeocode", action="store_true",
                    help="Force re-geocoding of all images, ignoring cached location data. Requires --geocode flag.")
    return ap.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    try:
        # Rename images if requested
        if args.rename:
            print("Renaming image files based on EXIF datetime...")
            metadata = ImageMetadata()
            images = ImageMetadata.find_images(args.folder)
            renamed_count = 0
            for img_path in images:
                new_path = metadata.rename_by_datetime(img_path)
                if new_path:
                    print(f"  {img_path.name} → {new_path.name}")
                    renamed_count += 1
            print(f"Renamed {renamed_count} of {len(images)} images.")

        config = Config(
            source_dir=args.folder,
            out_dir=args.out_dir or Path.cwd(),
            max_preview_height=args.preview_height,
            preload_count=args.preload_count,
            workers=args.workers,
            geocode=args.geocode,
            regeocode=args.regeocode,
            title=args.title,
            description=args.description,
            footer=args.footer,
            link1_title=args.link1_title,
            link1_url=args.link1_url,
            link2_title=args.link2_title,
            link2_url=args.link2_url,
            link3_title=args.link3_title,
            link3_url=args.link3_url
        )
        processor = PhotoProcessor(config, args.template_dir)
        processor.build_gallery()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
