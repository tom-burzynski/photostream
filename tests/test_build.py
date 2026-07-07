import datetime as dt
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


if __name__ == "__main__":
    unittest.main()
