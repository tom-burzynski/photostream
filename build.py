#!/usr/bin/env python3
import argparse
import configparser
import datetime as dt
import json
import re
import unicodedata
import os
import sys
import shutil
import subprocess
import hashlib
import pickle
import time
import urllib.request
import urllib.parse
from pathlib import Path
from PIL import Image, ExifTags, ImageOps
from dataclasses import dataclass, fields
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List, Tuple, Any
from functools import lru_cache
try:
    from jinja2 import Environment, DictLoader, select_autoescape
except ImportError:
    raise SystemExit(
        "Jinja2 is required to build the gallery. Install it with: pip install jinja2"
    )

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

def slugify(text: str) -> str:
    """Convert text to a URL-safe slug (cached)."""
    s = unicodedata.normalize("NFKD", text)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-._")
    return s or "photo"
slugify = lru_cache(maxsize=1000)(slugify)


def _assign_unique_ids(meta: List[Dict[str, Any]]) -> None:
    """Ensure every photo has a unique `id` by appending a counter to
    duplicates (e.g. `ph-...`, `ph-...-1`, `ph-...-2`). Mutates `meta` in place.
    """
    id_counts: Dict[str, int] = {}
    for m in meta:
        original_id = m["id"]
        if original_id in id_counts:
            id_counts[original_id] += 1
            m["id"] = f"{original_id}-{id_counts[original_id]}"
        else:
            id_counts[original_id] = 0


# Default max height for grid preview images (in pixels) - width will be proportional
DEFAULT_PREVIEW_HEIGHT = 400

# WebP conversion quality settings
WEBP_QUALITY = 90  # 0-100, higher is better quality but larger file size
WEBP_METHOD = 6    # 0-6, higher is slower but better compression
PREVIEW_WEBP_QUALITY = 80  # Lower than full-size; previews are downscaled anyway


def _read_version() -> str:
    """Read the project version from the VERSION file (single source of truth)."""
    try:
        return Path(__file__).resolve().parent.joinpath("VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "unknown"


__version__ = _read_version()

# Color extraction settings
COLOR_BG_FACTOR = 0.3      # Multiplier for background darkness (30% of average)
COLOR_ACCENT_FACTOR = 0.6  # Multiplier for accent color brightness (60% of average)
COLOR_BRIGHTNESS_THRESHOLD = 128  # Threshold for choosing light/dark text

# Geocoding settings
GEOCODE_TIMEOUT = 5  # Timeout in seconds for geocoding API requests
# Nominatim's usage policy requires an identifying User-Agent and at most 1 request/second
GEOCODE_USER_AGENT = f"photostream/{__version__} (+https://github.com/tom-burzynski/photostream)"
GEOCODE_MIN_INTERVAL = 1.0  # seconds between geocoding requests
_last_geocode_request = 0.0


def _throttle_geocode() -> None:
    """Sleep as needed so geocoding requests are GEOCODE_MIN_INTERVAL apart."""
    global _last_geocode_request
    wait = _last_geocode_request + GEOCODE_MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_geocode_request = time.monotonic()

# Sentinel for "not in the cache", distinct from a cached None.
MISSING = object()


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file + rename so readers (or a crash) never see a
    half-written file."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class MetadataCache:
    """Persistent JSON cache of per-image metadata, keyed by kind and file.

    It holds exact GPS coordinates, so it must live OUTSIDE the output
    directory: anything under out_dir gets deployed.
    """

    KINDS = ("datetime", "dimensions", "preview_hash", "colors", "gps", "location")
    LEGACY_FILE = Path("data") / ".metadata_cache.pkl"  # relative to out_dir

    def __init__(self, cache_dir: Path, legacy_out_dir: Optional[Path] = None):
        self.cache_dir = cache_dir
        self.cache_file = cache_dir / "metadata.json"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._keys: Dict[Path, str] = {}
        self._dirty = False
        self._cache = self._load_cache()
        if legacy_out_dir is not None:
            self._migrate_legacy(legacy_out_dir / self.LEGACY_FILE)

    def _load_cache(self) -> Dict[str, Any]:
        """Load cache from disk or create empty cache."""
        if not self.cache_file.exists():
            return {}
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Warning: Ignoring unreadable cache {self.cache_file}: {e}", file=sys.stderr)
            return {}

    def _migrate_legacy(self, legacy: Path) -> None:
        """Import, then delete, the old pickle cache that lived inside the
        published output. It is deleted even if the import fails: the data
        regenerates, the leak does not undo itself."""
        if not legacy.exists():
            return
        if not self._cache:
            try:
                with open(legacy, "rb") as f:
                    old = pickle.load(f)
                for key, value in old.items():
                    kind = key.split(":", 1)[0]
                    if kind in self.KINDS:
                        self._cache[key] = self._encode(kind, value)
                self._dirty = True
                self.save_cache()
            except Exception as e:
                print(f"Warning: Could not import legacy cache {legacy}: {e}", file=sys.stderr)
        legacy.unlink()
        print(f"Moved metadata cache out of the site output to {self.cache_file}", flush=True)

    def save_cache(self) -> None:
        """Save cache to disk if dirty."""
        if self._dirty:
            try:
                _atomic_write_text(self.cache_file, json.dumps(self._cache, ensure_ascii=False))
                self._dirty = False
            except Exception as e:
                print(f"Warning: Could not save cache {self.cache_file}: {e}", file=sys.stderr)

    @staticmethod
    def _encode(kind: str, value: Any) -> Any:
        if kind == "datetime" and value is not None:
            return value.isoformat()
        if isinstance(value, tuple):
            return list(value)
        return value

    @staticmethod
    def _decode(kind: str, value: Any) -> Any:
        if value is None:
            return None
        if kind == "datetime":
            return dt.datetime.fromisoformat(value)
        if kind in ("dimensions", "gps"):
            return tuple(value)
        return value

    def _content_signature(self, image_path: Path) -> str:
        """Short, content-aware signature (size + first bytes) used in cache keys.

        Including file content (rather than only mtime) avoids stale cache hits
        when a file's bytes change within the 1-second mtime resolution.
        """
        try:
            stat = image_path.stat()
            with open(image_path, 'rb') as f:
                head = f.read(1024)
            return f"{stat.st_size}:{hashlib.md5(head).hexdigest()[:16]}"
        except Exception:
            return str(image_path.name)

    def key(self, image_path: Path) -> str:
        """Content-aware, path-independent key (filename + content signature).

        Computed once per file per build: the cache lives for a single build,
        and recomputing means reopening the file on every lookup.
        """
        k = self._keys.get(image_path)
        if k is None:
            # Filename only (not full path) keeps the cache portable between environments
            k = f"{image_path.name}:{self._content_signature(image_path)}"
            self._keys[image_path] = k
        return k

    def get(self, kind: str, image_path: Path, default: Any = None) -> Any:
        """Cached value, or `default` if absent. Pass MISSING as the default
        to tell "not cached" apart from a cached None."""
        value = self._cache.get(f"{kind}:{self.key(image_path)}", MISSING)
        return default if value is MISSING else self._decode(kind, value)

    def set(self, kind: str, image_path: Path, value: Any) -> None:
        self._cache[f"{kind}:{self.key(image_path)}"] = self._encode(kind, value)
        self._dirty = True

    def cleanup_stale_entries(self, valid_paths: List[Path]) -> None:
        """Remove cache entries for files that no longer exist."""
        valid_keys = {f"{kind}:{self.key(p)}" for p in valid_paths for kind in self.KINDS}
        stale_keys = [key for key in self._cache if key not in valid_keys]
        if stale_keys:
            for key in stale_keys:
                del self._cache[key]
            self._dirty = True

class ImageMetadata:
    """Handles image metadata extraction and datetime parsing with caching."""
    
    def __init__(self, cache: Optional[MetadataCache] = None):
        self.cache = cache

    def _cached(self, kind: str, image_path: Path, compute):
        """Return the cached `kind` value for the file, computing and storing it on a miss."""
        if self.cache:
            cached = self.cache.get(kind, image_path, MISSING)
            if cached is not MISSING:
                return cached
        value = compute(image_path)
        if self.cache:
            self.cache.set(kind, image_path, value)
        return value

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
        return self._cached("datetime", image_path, self._extract_datetime_uncached)

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
        return self._cached("gps", image_path, self._extract_gps_uncached)

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
        return self._cached("dimensions", image_path, self._get_dimensions_uncached)

    def _get_dimensions_uncached(self, image_path: Path) -> Tuple[int, int]:
        """Extract display dimensions without decoding pixels.

        Header-only: `Image.open` and `getexif` read metadata, not pixel data.
        The size is adjusted for EXIF orientation so it matches the dimensions
        `ImageOps.exif_transpose` would produce on the decode path (orientations
        5/6/7/8 rotate 90/270 and swap width/height).
        """
        try:
            with Image.open(image_path) as im:
                w, h = im.size
                if im.getexif().get(0x0112, 1) in (5, 6, 7, 8):  # 90/270 rotations
                    w, h = h, w
                return (w, h)
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
        _throttle_geocode()
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
        _throttle_geocode()
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
    cache_dir: Path = Path("cache")
    preview_height: int = DEFAULT_PREVIEW_HEIGHT
    preload_count: int = 20
    workers: int = 4
    geocode: bool = False
    regeocode: bool = False
    page_size: int = 30  # Number of photos per page for infinite scroll
    title: str = "[photostream]"
    description: str = ""
    footer: str = ""
    links: Tuple[Tuple[str, str], ...] = ()  # (title, url) footer links

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Config":
        """Build from parsed arguments; field names match the OPTIONS dests."""
        links = ((getattr(args, f"link{n}_title"), getattr(args, f"link{n}_url")) for n in (1, 2, 3))
        names = {f.name for f in fields(cls)} - {"source_dir", "links"}
        return cls(
            source_dir=args.folder,
            links=tuple((t, u) for t, u in links if t and u),
            **{name: getattr(args, name) for name in names},
        )

    def __post_init__(self):
        if not self.source_dir.exists():
            raise ValueError(f"Source directory does not exist: {self.source_dir}")
        if self.preview_height <= 0:
            raise ValueError(f"Max preview height must be positive: {self.preview_height}")
        if self.page_size <= 0:
            raise ValueError(f"Page size must be positive: {self.page_size}")
        if self.workers <= 0:
            object.__setattr__(self, 'workers', os.cpu_count() or 4)
        if self.cache_dir.resolve().is_relative_to(self.out_dir.resolve()):
            raise ValueError(f"Cache directory must be outside the output directory (it holds GPS data): {self.cache_dir}")
        src, out = self.source_dir.resolve(), self.out_dir.resolve()
        if src.is_relative_to(out) or out.is_relative_to(src):
            raise ValueError(f"Source and output directories must not contain each other: {self.source_dir}, {self.out_dir}")
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
        stem = slugify(image_path.stem)
        h = hashlib.sha1(str(rel).encode("utf-8")).hexdigest()[:8]
        return f"{stem}-{h}.html"
    
    @staticmethod
    def strip_all_metadata(im: Image.Image) -> Image.Image:
        """Strip EXIF/GPS/IPTC/XMP/ICC metadata from the image's info dict in
        place, so saved outputs don't leak identifying information. Avoids a
        full pixel copy just to drop metadata.
        """
        for k in ("exif", "icc_profile", "XMP", "xml", "iptc", "photoshop", "APP1", "APP13"):
            try:
                im.info.pop(k, None)
            except Exception:
                pass
        return im
    
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
        """Hash naming the preview file: changes when the source or the preview
        height changes. Path-independent (filename, size, mtime, first 1KB), so
        a Docker build and a local build of the same files agree."""
        try:
            stat = src.stat()
            hasher = hashlib.sha256()
            hasher.update(f"{src.name}:{stat.st_size}:{int(stat.st_mtime)}:{self.config.preview_height}".encode())
            with open(src, 'rb') as f:
                hasher.update(f.read(1024))
            return hasher.hexdigest()[:16]
        except Exception:
            return hashlib.sha256(src.name.encode()).hexdigest()[:16]
    
    @staticmethod
    def preview_path(src: Path, previews_dir: Path, content_hash: str) -> Path:
        return previews_dir / f"{slugify(src.stem)}-{content_hash}.webp"

    def cached_preview(self, src: Path, previews_dir: Path, content_hash: str) -> Optional[Tuple[Path, Dict[str, str]]]:
        """(preview_path, colors) if an up-to-date preview already exists, else None."""
        if not self.cache:
            return None
        out = self.preview_path(src, previews_dir, content_hash)
        colors = self.cache.get("colors", src)
        if self.cache.get("preview_hash", src) == content_hash and colors and out.exists():
            return out, colors
        return None

    def generate_preview(self, src: Path, previews_dir: Path, image_metadata: Optional[ImageMetadata] = None, im: Optional[Image.Image] = None, content_hash: Optional[str] = None) -> Optional[Tuple[Path, int, int, Dict[str, str]]]:
        """Create or reuse a WebP preview for `src` under `previews_dir`.

        If `im` is supplied (an already opened + EXIF-transposed image), it is
        reused so the source file is decoded only once per photo. Otherwise the
        source is opened here.

        Returns (preview_path, width, height, colors) with colors dict containing
        bg_color, accent_color, text_color. Returns None if preview generation
        fails, so the caller can skip the photo rather than serving the original
        (un-stripped) file.
        """
        opened = im is None
        try:
            # Compute the content hash up front (cheap) so the cache can be
            # checked before decoding anything.
            if content_hash is None:
                content_hash = self._get_content_hash(src)

            out = self.preview_path(src, previews_dir, content_hash)

            # Cache hit: reuse the existing preview WITHOUT decoding the source.
            # Dimensions come from cached metadata so no image open is needed.
            hit = self.cached_preview(src, previews_dir, content_hash)
            if hit:
                w, h = image_metadata.get_image_dimensions(src) if image_metadata else (1, 1)
                return (out, w, h, hit[1])

            # Cache miss (or no cache): decode the source to (re)generate the preview.
            if im is None:
                try:
                    im = Image.open(src)
                    im = ImageOps.exif_transpose(im)
                except Exception:
                    return None
            # A caller-supplied `im` is already opened + EXIF-transposed.
            w, h = im.size

            # Generate preview and extract colors
            colors = {"bg_color": "#000000", "accent_color": "#333333", "text_color": "#ffffff"}
            try:
                # Extract colors from the image before resizing
                colors = self.extract_colors(im)

                pw, ph = im.size
                # Scale based on height for consistent gallery loading
                scale = min(1.0, self.config.preview_height / float(ph)) if self.config.preview_height > 0 else 1.0
                new_w = max(1, int(round(pw * scale)))
                new_h = max(1, int(round(ph * scale)))
                if (new_w, new_h) != (pw, ph):
                    im = im.resize((new_w, new_h), Image.LANCZOS)
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                # Strip all metadata to avoid leaking EXIF/GPS/etc in previews
                im = self.strip_all_metadata(im)
                out.parent.mkdir(parents=True, exist_ok=True)
                im.save(out, format="WEBP", quality=PREVIEW_WEBP_QUALITY, optimize=True, method=WEBP_METHOD)

                # Cache the hash and colors
                if self.cache:
                    self.cache.set("preview_hash", src, content_hash)
                    self.cache.set("colors", src, colors)

            except Exception:
                # Do NOT fall back to the original file: it would leak EXIF/GPS
                # metadata in the grid. Signal failure so the caller skips the photo.
                return None
            return (out, w, h, colors)
        finally:
            if opened and im is not None:
                im.close()
    
    def convert_to_webp(self, src: Path, dst: Path, im: Optional[Image.Image] = None) -> bool:
        """Convert image to WebP format with metadata stripped.

        If `im` is supplied (already opened + EXIF-transposed), it is reused so
        the source file is decoded only once per photo. Otherwise the source is
        opened here.
        """
        opened = im is None
        try:
            try:
                needs = (not dst.exists()) or (dst.stat().st_mtime < src.stat().st_mtime)
            except Exception:
                needs = True

            if needs:
                if opened:
                    try:
                        im = Image.open(src)
                        im = ImageOps.exif_transpose(im)
                    except Exception as e:
                        print(f"Warning: Failed to open {src.name}: {e}", file=sys.stderr)
                        return False
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                # Strip all metadata so the WebP contains no identifying data
                im = self.strip_all_metadata(im)
                dst.parent.mkdir(parents=True, exist_ok=True)
                im.save(dst, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
            return True
        except Exception as e:
            # If conversion fails, remove any partial/empty file and do not leak the original with metadata
            if dst.exists():
                try:
                    dst.unlink()
                except Exception:
                    pass
            print(f"Warning: Failed to convert {src.name} to WebP: {e}", file=sys.stderr)
            return False
        finally:
            if opened and im is not None:
                im.close()

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



class TemplateRenderer:
    """Handles HTML template rendering with Jinja2."""

    def __init__(self, template_dir: Optional[Path] = None):
        self.template_dir = template_dir or self._get_default_template_dir()
        self.templates = self._load_templates()
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
    
    def render_index(self, **ctx) -> str:
        """Render the main index page with photo grid."""
        return self._env.get_template('index.html').render(**ctx)

    def render_photo(self, **ctx) -> str:
        """Render individual photo page."""
        return self._env.get_template('photo.html').render(**ctx)


class PhotoProcessor:
    """Main class for processing photos and generating the gallery with caching."""
    
    def __init__(self, config: Config, template_dir: Optional[Path] = None):
        self.config = config
        self.cache = MetadataCache(config.cache_dir, legacy_out_dir=config.out_dir)
        self.image_metadata = ImageMetadata(self.cache)
        self.preview_generator = PreviewGenerator(config, self.cache)
        self.template_renderer = TemplateRenderer(template_dir)
    
    @staticmethod
    def _progress(i: int, n: int, label: str = "") -> None:
        """Display a progress bar - only output every 10 items for clean Docker logs."""
        if n <= 0:
            return

        # Output progress bar on single line with carriage return
        width = 30
        filled = int(width * (i / n))
        bar = "#" * filled + "-" * (width - filled)
        # Use \r to update same line, add newline only when complete
        end_char = '\n' if i >= n else ''
        print(f"\r{label} [{bar}] {i}/{n}", end=end_char, flush=True)
    
    @staticmethod
    def _format_time(photo_datetime: dt.datetime) -> str:
        """Format the time part as '12:28pm' (12-hour clock)."""
        hour = photo_datetime.hour
        minute = photo_datetime.minute
        ampm = "am" if hour < 12 else "pm"
        if hour == 0:
            display_hour = 12
        elif hour > 12:
            display_hour = hour - 12
        else:
            display_hour = hour
        return f"{display_hour}:{minute:02d}{ampm}"

    @staticmethod
    def _format_photo_title(photo_datetime: dt.datetime) -> str:
        """Format photo datetime as '[July 8, 2025 at 12:28pm]'."""
        month = photo_datetime.strftime("%B")
        day = photo_datetime.day
        year = photo_datetime.year
        formatted_datetime = f"{month} {day}, {year} at {PhotoProcessor._format_time(photo_datetime)}"
        return f"[{formatted_datetime}]"


    def _process_one_image(self, idx: int, image_path: Path, originals_dir: Path, previews_dir: Path, photo_datetime: dt.datetime) -> Optional[Dict[str, Any]]:
        """Process a single image: convert to WebP, generate preview, extract metadata."""
        try:
            # Determine relative structure under source
            try:
                rel_under_src = image_path.relative_to(self.config.source_dir)
            except Exception:
                rel_under_src = Path(image_path.name)

            dst_full = (originals_dir / rel_under_src).with_suffix(".webp")

            # Only decode the source if we actually have work to do. The full
            # WebP is reused when it is newer than the source; the preview is
            # reused when its cache entry still matches. On a warm incremental
            # rebuild (the Docker file-watcher workflow) unchanged images then
            # skip decoding entirely instead of forcing one decode each.
            convert_needed = (
                not dst_full.exists()
                or dst_full.stat().st_mtime < image_path.stat().st_mtime
            )

            content_hash = self.preview_generator._get_content_hash(image_path)
            decode_needed = convert_needed or not self.preview_generator.cached_preview(
                image_path, previews_dir, content_hash
            )

            # Open and normalize orientation once; reuse the decoded image for
            # both the full WebP and the preview so the source is read a single time.
            im = None
            if decode_needed:
                try:
                    im = Image.open(image_path)
                    im = ImageOps.exif_transpose(im)
                    if im.mode not in ("RGB", "L"):
                        im = im.convert("RGB")
                except Exception:
                    return None

            # Convert full-size to WebP inside originals/
            if not self.preview_generator.convert_to_webp(image_path, dst_full, im=im):
                if im is not None:
                    im.close()
                print(f"Warning: Skipping {image_path.name}: full-size WebP conversion failed", file=sys.stderr)
                return None

            rel_src_full = PreviewGenerator.rel_to_out(dst_full, self.config.out_dir)

            # Generate / reuse preview (WebP) and get dimensions + colors
            result = self.preview_generator.generate_preview(
                image_path, previews_dir, self.image_metadata, im=im, content_hash=content_hash
            )
            if im is not None:
                im.close()
            if result is None:
                # Preview generation failed; skip this photo rather than
                # serving the original (un-stripped) file in the grid.
                print(f"Warning: Skipping {image_path.name}: preview generation failed", file=sys.stderr)
                return None
            preview_path, w_meta, h_meta, colors = result
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
        except Exception as e:
            # Skip this image to avoid referencing originals that may contain metadata
            print(f"Warning: Skipping {image_path.name}: {e}", file=sys.stderr)
            return None

    def _geocode_images(self, meta: List[Dict[str, Any]]) -> None:
        """Extract GPS coordinates and geocode to city names for all images."""
        geocoded_count = 0
        total = len(meta)

        for idx, m in enumerate(meta, 1):
            original_path = Path(m["original_path"])

            # Check cache first
            location = self.cache.get("location", original_path)

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
                    self.cache.set("location", original_path, location)
                    self.cache.save_cache()  # Save after each successful geocode
                    geocoded_count += 1
                    print(f" → {location.get('city', 'Unknown')}", flush=True)
                else:
                    # No location found, cache empty dict to avoid re-querying
                    m["location"] = {}
                    self.cache.set("location", original_path, {})
                    self.cache.save_cache()  # Save to avoid re-querying
                    print(f" → No location found", flush=True)
            else:
                # No GPS data, cache empty dict
                m["location"] = {}
                self.cache.set("location", original_path, {})
                self.cache.save_cache()  # Save to avoid re-processing
                if not should_retry:  # Only print if not a retry attempt
                    print(f"  [{idx}/{total}] {original_path.name}: No GPS data", flush=True)

        print(f"\nGeocoded {geocoded_count} of {total} images.", flush=True)

    def _remove_stale_outputs(self, meta: List[Dict[str, Any]], total_pages: int) -> None:
        """Delete generated files that no current photo references: outputs of
        removed or renamed sources, superseded previews, surplus JSON pages.
        Without this, a photo taken out of the source folder stays reachable
        on the deployed site."""
        out = self.config.out_dir
        keep = set()
        for m in meta:
            keep |= {(out / m["src"]).resolve(), (out / m["full"]).resolve(), (out / "view" / m["slug"]).resolve()}
        keep |= {(out / "data" / f"page_{n}.json").resolve() for n in range(total_pages)}

        candidates = [
            *(out / "previews").glob("*.webp"),
            *(out / "originals").rglob("*.webp"),
            *(out / "view").glob("*.html"),
            *(out / "data").glob("page_*.json"),
        ]
        removed = 0
        for p in candidates:
            if p.resolve() not in keep:
                p.unlink()
                removed += 1
        # Drop subfolders of originals/ left empty by removed photos
        for d in sorted((out / "originals").rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        if removed:
            print(f"Removed {removed} stale output file(s).", flush=True)

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
        print(f"Found {total} images. Generating previews (max height {self.config.preview_height}px)...", flush=True)

        # Prepare directories
        view_dir = self.config.out_dir / "view"
        view_dir.mkdir(parents=True, exist_ok=True)
        previews_dir = self.config.out_dir / "previews"
        previews_dir.mkdir(parents=True, exist_ok=True)
        originals_dir = self.config.out_dir / "originals"
        originals_dir.mkdir(parents=True, exist_ok=True)

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

        # Handle duplicate timestamp IDs by appending a counter
        _assign_unique_ids(meta)

        # Extract GPS and geocode if enabled
        if self.config.geocode:
            print("Geocoding image locations...", flush=True)
            self._geocode_images(meta)

        print("Writing index and pages...", flush=True)

        # What gets published: drop build-only fields (the source path) from the JSON
        public_meta = [{k: v for k, v in m.items() if k != "original_path"} for m in meta]

        # Generate paginated JSON data for infinite scroll
        data_dir = self.config.out_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # Split photos into pages
        page_size = self.config.page_size
        total_pages = (len(meta) + page_size - 1) // page_size if meta else 0

        # Build photo index mapping photo ID -> page number and URL
        photo_index = {}
        for page_num in range(total_pages):
            start_idx = page_num * page_size
            end_idx = min(start_idx + page_size, len(meta))
            page_photos = public_meta[start_idx:end_idx]

            # Add each photo to the index
            for photo in page_photos:
                photo_index[photo["id"]] = {
                    "page": page_num,
                    "url": photo["page"]
                }

            page_data = {
                "photos": page_photos,
                "page": page_num,
                "total_pages": total_pages,
                "has_more": page_num < total_pages - 1
            }

            page_file = data_dir / f"page_{page_num}.json"
            _atomic_write_text(page_file, json.dumps(page_data, ensure_ascii=False))

        # Write photo index for direct photo link lookups
        photo_index_file = data_dir / "photo-index.json"
        _atomic_write_text(photo_index_file, json.dumps(photo_index, ensure_ascii=False))

        # Write index.html with LCP optimization (only first page inline)
        preload_images = public_meta[:self.config.preload_count]
        first_page_photos = public_meta[:page_size]

        index_html = self.template_renderer.render_index(
            photos_json=json.dumps(first_page_photos, ensure_ascii=False),
            photos=first_page_photos,
            preload_images=preload_images,
            preload_count=self.config.preload_count,
            title=self.config.title,
            description=self.config.description,
            footer=self.config.footer,
            links=[{"title": t, "url": u} for t, u in self.config.links],
        )
        _atomic_write_text(self.config.out_dir / "index.html", index_html)

        # Write per-photo pages
        n = len(meta)
        for i, m in enumerate(meta):
            # No wrap-around: stop at boundaries
            prev_idx = max(0, i - 1)  # stay at first photo
            next_idx = min(n - 1, i + 1)  # stay at last photo

            # Look up the datetime for this photo and format the title
            original_path = Path(m["original_path"])
            photo_datetime = datetime_lookup.get(original_path)
            if photo_datetime:
                formatted_title = self._format_photo_title(photo_datetime)
                # Format date and time separately for info overlay
                date_str = f"{photo_datetime:%B} {photo_datetime.day}, {photo_datetime.year}"  # e.g., "July 8, 2025"
                time_str = self._format_time(photo_datetime)  # e.g., "12:28pm"
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
                title=formatted_title,
                prev_page=f"./{meta[prev_idx]['slug']}",
                next_page=f"./{meta[next_idx]['slug']}",
                prev_id=meta[prev_idx]['id'],
                next_id=meta[next_idx]['id'],
                img_src=f"../{m['full']}",
                preview_src=f"../{m['src']}",
                img_width=m['w'],
                img_height=m['h'],
                alt=m["name"],
                anchor_id=m["id"],
                bg_color=m.get("bg_color", "#000000"),
                accent_color=m.get("accent_color", "#333333"),
                text_color=m.get("text_color", "#ffffff"),
                location_city=city,
                location_country=country,
                photo_date=date_str,
                photo_time=time_str,
            )
            _atomic_write_text(view_dir / m["slug"], html_out)

        if meta:  # an empty run (e.g. every decode failed) must not wipe the site
            self._remove_stale_outputs(meta, total_pages)

        # Save cache to disk
        self.cache.save_cache()
        
        print(
            f"Done:\n"
            f"- index.html\n"
            f"- favicon.svg (copied)\n"
            f"- {originals_dir}/* (copied originals)\n"
            f"- {previews_dir}/* (grid previews)\n"
            f"- {view_dir}/* ({n} pages)\n"
            f"- {self.cache.cache_file} (cached metadata, not published)"
        )



@dataclass(frozen=True)
class Option:
    """One setting: read from config.ini when it has a `section`, exposed as a
    CLI flag when it has `help`, and handed to Config under `dest`."""
    dest: str
    type: Any
    default: Any
    help: Optional[str] = None
    section: Optional[str] = None
    key: Optional[str] = None  # config.ini key, when it differs from dest


# The single list of settings. Config file, CLI flags and Config all derive from it.
OPTIONS = [
    Option("folder", Path, "./originals", section="build"),  # the positional argument
    Option("out_dir", Path, "./site", "Directory to write index.html, previews/ and view/ to.", "build"),
    Option("cache_dir", Path, "./cache", "Directory for the metadata cache. Must be outside --out-dir: it holds GPS data.", "build"),
    Option("workers", int, os.cpu_count() or 4, "Worker threads for image processing.", "build"),
    Option("template_dir", Path, None, "Directory with custom index.html and photo.html; unset uses templates/ next to build.py.", "build"),
    Option("preview_height", int, DEFAULT_PREVIEW_HEIGHT, "Max height of grid preview images in pixels; lower means smaller files.", "build"),
    Option("preload_count", int, 20, "Number of first images to preload for LCP.", "build"),
    Option("page_size", int, 30, "Photos per page for infinite scroll.", "build"),
    Option("rename", bool, False, "Rename source images to their EXIF datetime (YYYY-MM-DD-HH-MM-SS.ext) before building.", "build"),
    Option("geocode", bool, False, "Reverse geocode GPS coordinates to city/country (needs internet).", "build"),
    Option("regeocode", bool, False, "Retry geocoding photos whose earlier lookup found no location. Requires --geocode.", "build"),
    Option("title", str, "[photostream]", "Gallery title.", "gallery"),
    Option("description", str, "", "Text under the title.", "gallery"),
    Option("footer", str, "", "Footer text at the bottom right.", "gallery"),
    *(Option(f"link{n}_{part}", str, "", f"{part.capitalize()} of footer link {n}.", "gallery")
      for n in (1, 2, 3) for part in ("title", "url")),
    Option("deploy_method", str, "", "Deployment method: rsync, rclone or robocopy. When set in config.ini, every build deploys.",
           "deployment", key="method"),
    Option("rsync_destination", str, "", section="deployment"),
    Option("rclone_destination", str, "", section="deployment"),
    Option("robocopy_destination", str, "", section="deployment"),
]


def load_config_file(config_path: Path = Path("config.ini")) -> Dict[str, Any]:
    """OPTIONS defaults overlaid with the INI file's values (if the file exists).

    An empty value keeps the default, so `workers =` means "number of CPU
    cores". An invalid value raises ValueError naming the key.
    """
    values = {o.dest: o.default for o in OPTIONS}
    if not config_path.exists():
        return values
    parser = configparser.ConfigParser()
    parser.read(config_path)
    for o in OPTIONS:
        key = o.key or o.dest
        raw = parser.get(o.section, key, fallback="") if o.section else ""
        if not raw:
            continue
        try:
            if o.type is bool:
                values[o.dest] = parser.getboolean(o.section, key)
            else:
                values[o.dest] = o.type(raw)
        except ValueError as e:
            raise ValueError(f"{config_path}: [{o.section}] {key}: {e}") from None
    return values


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments with config file support.

    The config file path is resolved first (via a pre-parser) so a custom
    ``--config`` is honored. Its values become argparse defaults; any flag
    passed on the command line overrides the corresponding config value.
    Every OPTIONS value, flag or not, ends up on the returned namespace.
    """
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=Path, default=Path("config.ini"))
    pre_args, _ = pre_parser.parse_known_args(argv)
    try:
        values = load_config_file(pre_args.config)
    except ValueError as e:
        raise SystemExit(f"Configuration error: {e}")

    ap = argparse.ArgumentParser(
        description="Generate a justified photo gallery with per-photo pages (newest first).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("folder", nargs="?", type=Path, help="Folder containing photos (scanned recursively).")
    ap.add_argument("--config", type=Path, default=Path("config.ini"), help="Path to the configuration file.")
    for o in OPTIONS:
        if o.help is None:
            continue
        flag = "--" + o.dest.replace("_", "-")
        if o.type is bool:
            ap.add_argument(flag, action=argparse.BooleanOptionalAction, help=o.help)
        else:
            ap.add_argument(flag, type=o.type, help=o.help)
    ap.add_argument("--deploy", action="store_true",
                    help="Deploy after building, using the method and destination from config.ini or --deploy-method.")
    ap.set_defaults(**values)  # config.ini values are the defaults; CLI flags override them
    return ap.parse_args(argv)


def deploy_gallery(output_dir: Path, method: str, config_defaults: Dict[str, Any]) -> bool:
    """Deploy the gallery to a remote destination using the specified method.
    Returns False if the deployment failed."""
    if not method:
        print("No deployment method specified. Skipping deployment.", flush=True)
        return True

    print(f"\nDeploying gallery using {method}...", flush=True)

    if method == "rsync":
        destination = config_defaults.get("rsync_destination", "")
        if not destination:
            print("Error: rsync method specified but rsync_destination not configured", file=sys.stderr)
            return False

        cmd = ["rsync", "-avu", "--delete", f"{output_dir}/", destination]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(result.stdout, flush=True)
            print(f"Successfully deployed to {destination} via rsync", flush=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error deploying via rsync: {e}", file=sys.stderr)
            print(e.stderr, file=sys.stderr)
            return False
        except FileNotFoundError:
            print("Error: rsync command not found. Please install rsync.", file=sys.stderr)
            return False

    elif method == "rclone":
        destination = config_defaults.get("rclone_destination", "")
        if not destination:
            print("Error: rclone method specified but rclone_destination not configured", file=sys.stderr)
            return False

        print(f"Syncing {output_dir} to {destination}...", flush=True)
        cmd = ["rclone", "sync", "--progress", str(output_dir), destination]
        try:
            # Run rclone with direct output to terminal (no capture)
            result = subprocess.run(cmd)

            if result.returncode == 0:
                print(f"\nSuccessfully deployed to {destination} via rclone", flush=True)
                return True
            else:
                print(f"\nError deploying via rclone (exit code {result.returncode})", file=sys.stderr)
                return False
        except FileNotFoundError:
            print("Error: rclone command not found. Please install rclone.", file=sys.stderr)
            return False

    elif method == "robocopy":
        destination = config_defaults.get("robocopy_destination", "")
        if not destination:
            print("Error: robocopy method specified but robocopy_destination not configured", file=sys.stderr)
            return False

        cmd = ["robocopy", str(output_dir), destination, "/MIR", "/R:3", "/W:5", "/MT:8"]
        try:
            # Robocopy returns exit code 1 for success with files copied
            result = subprocess.run(cmd, capture_output=True, text=True)
            print(result.stdout, flush=True)
            if result.returncode <= 7:  # Robocopy exit codes 0-7 are success/warnings
                print(f"Successfully deployed to {destination} via robocopy", flush=True)
                return True
            else:
                print(f"Error deploying via robocopy (exit code {result.returncode})", file=sys.stderr)
                print(result.stderr, file=sys.stderr)
                return False
        except FileNotFoundError:
            print("Error: robocopy command not found (Windows only).", file=sys.stderr)
            return False

    else:
        print(f"Error: Unknown deployment method: {method}", file=sys.stderr)
        return False


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

        config = Config.from_args(args)
        processor = PhotoProcessor(config, args.template_dir)
        processor.build_gallery()

        # Deploy if requested
        if args.deploy or args.deploy_method:
            if not args.deploy_method:
                print("Warning: --deploy specified but no deployment method configured", file=sys.stderr)
            elif not deploy_gallery(config.out_dir, args.deploy_method, vars(args)):
                sys.exit(1)

    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
