import contextlib
import datetime as dt
import io
import json
import pickle
import tempfile
import unittest
from pathlib import Path

import build


class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(build.slugify("Hello World"), "Hello-World")

    def test_strips_non_ascii(self):
        self.assertEqual(build.slugify("Café déjà"), "Cafe-deja")

    def test_empty_becomes_photo(self):
        self.assertEqual(build.slugify("!!!"), "photo")

    def test_cached(self):
        # lru_cache returns the same object for identical input
        self.assertIs(build.slugify("Same"), build.slugify("Same"))


class FormatTimeTests(unittest.TestCase):
    def test_midnight(self):
        self.assertEqual(
            build.PhotoProcessor._format_time(dt.datetime(2025, 1, 1, 0, 5)), "12:05am"
        )

    def test_noon(self):
        self.assertEqual(
            build.PhotoProcessor._format_time(dt.datetime(2025, 1, 1, 12, 0)), "12:00pm"
        )

    def test_pm(self):
        self.assertEqual(
            build.PhotoProcessor._format_time(dt.datetime(2025, 1, 1, 13, 30)), "1:30pm"
        )

    def test_am_pads_minutes(self):
        self.assertEqual(
            build.PhotoProcessor._format_time(dt.datetime(2025, 1, 1, 9, 3)), "9:03am"
        )


class ExtractDatetimeTests(unittest.TestCase):
    def _make_image_with_exif(self, exif_value):
        from PIL import Image

        d = tempfile.mkdtemp()
        p = Path(d) / "img.jpg"
        img = Image.new("RGB", (10, 10), (255, 255, 255))
        exif = Image.Exif()
        exif[0x9003] = exif_value  # DateTimeOriginal
        img.save(p, exif=exif.tobytes())
        return p

    def test_exif_datetime_original(self):
        p = self._make_image_with_exif("2025:01:02 03:04:05")
        md = build.ImageMetadata()
        self.assertEqual(md.extract_datetime(p), dt.datetime(2025, 1, 2, 3, 4, 5))

    def test_missing_exif_falls_back_to_mtime(self):
        from PIL import Image

        d = tempfile.mkdtemp()
        p = Path(d) / "img.jpg"
        Image.new("RGB", (10, 10)).save(p)
        now = dt.datetime.now()
        md = build.ImageMetadata()
        result = md.extract_datetime(p)
        self.assertLess(abs((result - now).total_seconds()), 5)


class AssignUniqueIdsTests(unittest.TestCase):
    def test_duplicates_get_counter_suffix(self):
        meta = [
            {"id": "ph-1"},
            {"id": "ph-1"},
            {"id": "ph-1"},
            {"id": "ph-2"},
            {"id": "ph-1"},
        ]
        build._assign_unique_ids(meta)
        ids = [m["id"] for m in meta]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, ["ph-1", "ph-1-1", "ph-1-2", "ph-2", "ph-1-3"])

    def test_no_duplicates_unchanged(self):
        meta = [{"id": "a"}, {"id": "b"}]
        build._assign_unique_ids(meta)
        self.assertEqual([m["id"] for m in meta], ["a", "b"])


class DimensionsTests(unittest.TestCase):
    def _make_image(self, size, orientation=None):
        from PIL import Image

        d = tempfile.mkdtemp()
        p = Path(d) / "img.jpg"
        img = Image.new("RGB", size, (10, 20, 30))
        if orientation is not None:
            exif = Image.Exif()
            exif[0x0112] = orientation
            img.save(p, exif=exif.tobytes())
        else:
            img.save(p)
        return p

    def test_raw_dimensions_unchanged(self):
        p = self._make_image((20, 40))
        self.assertEqual(build.ImageMetadata().get_image_dimensions(p), (20, 40))

    def test_orientation_1_unchanged(self):
        p = self._make_image((20, 40), orientation=1)
        self.assertEqual(build.ImageMetadata().get_image_dimensions(p), (20, 40))

    def test_orientation_6_swaps(self):
        # Orientation 6 rotates 90deg: display size is swapped (40x20).
        p = self._make_image((20, 40), orientation=6)
        self.assertEqual(build.ImageMetadata().get_image_dimensions(p), (40, 20))

    def test_orientation_7_swaps(self):
        p = self._make_image((20, 40), orientation=7)
        self.assertEqual(build.ImageMetadata().get_image_dimensions(p), (40, 20))


def _make_photo(folder, name, when="2025:01:02 03:04:05", size=(40, 30), gps=False):
    """Write a small JPEG with a DateTimeOriginal (and optionally GPS) tag."""
    from PIL import Image

    exif = Image.Exif()
    exif[0x9003] = when
    if gps:
        exif.get_ifd(0x8825).update({1: "N", 2: (52.0, 13.0, 0.0), 3: "E", 4: (21.0, 0.0, 0.0)})
    p = Path(folder) / name
    Image.new("RGB", size, (120, 60, 30)).save(p, exif=exif.tobytes())
    return p


def _build(src, out, cache, **kwargs):
    cfg = build.Config(source_dir=Path(src), out_dir=Path(out), cache_dir=Path(cache), workers=2, **kwargs)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        build.PhotoProcessor(cfg).build_gallery()


class MetadataCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.img = _make_photo(self.tmp, "a.jpg")

    def test_round_trip_through_json(self):
        c = build.MetadataCache(self.tmp / "cache")
        c.set("datetime", self.img, dt.datetime(2025, 1, 2, 3, 4, 5))
        c.set("dimensions", self.img, (40, 30))
        c.set("gps", self.img, None)
        c.save_cache()
        c2 = build.MetadataCache(self.tmp / "cache")
        self.assertEqual(c2.get("datetime", self.img), dt.datetime(2025, 1, 2, 3, 4, 5))
        self.assertEqual(c2.get("dimensions", self.img), (40, 30))
        json.loads((self.tmp / "cache" / "metadata.json").read_text())  # plain JSON on disk

    def test_cached_none_is_not_missing(self):
        c = build.MetadataCache(self.tmp / "cache")
        self.assertIs(c.get("gps", self.img, build.MISSING), build.MISSING)
        c.set("gps", self.img, None)
        self.assertIsNone(c.get("gps", self.img, build.MISSING))

    def test_legacy_pickle_is_imported_and_deleted(self):
        out = self.tmp / "site"
        legacy = out / "data" / ".metadata_cache.pkl"
        legacy.parent.mkdir(parents=True)
        key = build.MetadataCache(self.tmp / "scratch").key(self.img)
        legacy.write_bytes(pickle.dumps({
            f"gps:{key}": (52.0, 21.0),
            f"datetime:{key}": dt.datetime(2020, 5, 6, 7, 8, 9),
        }))
        with contextlib.redirect_stdout(io.StringIO()):
            c = build.MetadataCache(self.tmp / "cache", legacy_out_dir=out)
        self.assertFalse(legacy.exists())
        self.assertEqual(c.get("gps", self.img), (52.0, 21.0))
        self.assertEqual(c.get("datetime", self.img), dt.datetime(2020, 5, 6, 7, 8, 9))

    def test_config_refuses_cache_inside_out_dir(self):
        (self.tmp / "photos").mkdir()
        build.Config(source_dir=self.tmp / "photos", out_dir=self.tmp / "site", cache_dir=self.tmp / "other")  # control: valid
        with self.assertRaises(ValueError):
            build.Config(source_dir=self.tmp / "photos", out_dir=self.tmp / "site", cache_dir=self.tmp / "site" / "cache")


class BuildOutputTests(unittest.TestCase):
    def test_site_holds_no_cache_or_source_paths(self):
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "photos"
        src.mkdir()
        _make_photo(src, "a.jpg", gps=True)
        _make_photo(src, "b.jpg", when="2025:03:04 05:06:07")
        _build(src, tmp / "site", tmp / "cache")

        site_files = [p.name for p in (tmp / "site").rglob("*")]
        self.assertNotIn(".metadata_cache.pkl", site_files)
        self.assertNotIn("metadata.json", site_files)
        self.assertTrue((tmp / "cache" / "metadata.json").exists())
        for page in (tmp / "site" / "data").glob("*.json"):
            self.assertNotIn("original_path", page.read_text())
        self.assertNotIn("original_path", (tmp / "site" / "index.html").read_text())
        self.assertNotIn(str(src), (tmp / "site" / "index.html").read_text())


class StaleOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / "photos"
        self.src.mkdir()
        self.site = self.tmp / "site"
        self.a = _make_photo(self.src, "a.jpg")
        _make_photo(self.src, "b.jpg", when="2025:03:04 05:06:07")

    def _files(self, sub, pattern):
        return sorted(p.name for p in (self.site / sub).glob(pattern))

    def test_removed_source_disappears_from_site(self):
        _build(self.src, self.site, self.tmp / "cache")
        self.assertEqual(len(self._files("view", "*.html")), 2)
        self.a.unlink()
        _build(self.src, self.site, self.tmp / "cache")
        for sub, pattern in (("view", "*.html"), ("previews", "*.webp"), ("originals", "*.webp")):
            files = self._files(sub, pattern)
            self.assertEqual(len(files), 1, (sub, files))
            self.assertFalse(any(f.startswith("a") for f in files), (sub, files))

    def test_surplus_json_pages_removed(self):
        _build(self.src, self.site, self.tmp / "cache", page_size=1)
        self.assertEqual(self._files("data", "page_*.json"), ["page_0.json", "page_1.json"])
        self.a.unlink()
        _build(self.src, self.site, self.tmp / "cache", page_size=1)
        self.assertEqual(self._files("data", "page_*.json"), ["page_0.json"])

    def test_preview_height_change_regenerates_previews(self):
        _build(self.src, self.site, self.tmp / "cache", max_preview_height=20)
        before = self._files("previews", "*.webp")
        _build(self.src, self.site, self.tmp / "cache", max_preview_height=10)
        after = self._files("previews", "*.webp")
        self.assertEqual(len(after), 2)
        self.assertFalse(set(before) & set(after))

    def test_preview_name_is_path_independent(self):
        import shutil
        other = self.tmp / "elsewhere"
        other.mkdir()
        copy = Path(shutil.copy2(self.a, other / "a.jpg"))
        gen = build.PreviewGenerator(build.Config(source_dir=self.src, out_dir=self.site, cache_dir=self.tmp / "cache"))
        self.assertEqual(gen._get_content_hash(self.a), gen._get_content_hash(copy))

    def test_config_refuses_overlapping_source_and_output(self):
        with self.assertRaises(ValueError):
            build.Config(source_dir=self.tmp / "site" / "originals", out_dir=self.tmp / "site", cache_dir=self.tmp / "cache")
        with self.assertRaises(ValueError):
            build.Config(source_dir=self.tmp, out_dir=self.tmp / "site", cache_dir=self.tmp / "cache")


class EscapingTests(unittest.TestCase):
    def test_filename_escaped_once_in_photo_page(self):
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "photos"
        src.mkdir()
        _make_photo(src, "rock & roll.jpg")
        _build(src, tmp / "site", tmp / "cache")
        page = next((tmp / "site" / "view").glob("*.html")).read_text()
        self.assertIn('alt="rock &amp; roll.jpg"', page)
        self.assertNotIn("&amp;amp;", page)
        self.assertIn("January 2, 2025 at 3:04am", page)


if __name__ == "__main__":
    unittest.main()
