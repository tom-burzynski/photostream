# Refactoring Notes for build.py

Code review of `build.py` (1494 lines). Findings ordered by severity.
Last reviewed: 2026-07-07.

## Bugs (correctness / privacy)

### 1. `--config` override is dead
`build.py:1355-1362` (`parse_args`)

When a custom `--config path` is given, the file is re-loaded but values are
applied only via `if not hasattr(args, key)`. argparse has already set every
attribute from the default `config.ini`, so `hasattr` is always true and the
custom values are silently ignored. Custom config files do not actually
override anything.

Fix: re-run `parse_known_args`/`set_defaults` with the custom config, or compare
against the pre-override `config_defaults` instead of checking `hasattr`.

### 2. Privacy leak on preview generation failure
`build.py:641-643` (`generate_preview` fallback) and `build.py:901-948` (`_process_one_image`)

`generate_preview` returns the original `src` path on any exception. That path
becomes `photo.src` (the grid `<img>`), so a failed preview would serve the
original file with all EXIF/GPS intact — contradicting the project's
metadata-stripping goal. `_process_one_image` only skips a photo when
`convert_to_webp` fails, not when preview generation fails.

Fix: return `None` (skip the photo) or a safe placeholder on preview failure.

### 3. Broken non-Jinja2 fallback path
`build.py:834-851` (`TemplateRenderer.render_photo`)

The fallback references `PHOTO_TMPL`, which is **never defined** anywhere in the
file. If Jinja2 is ever absent, `render_photo` raises `NameError`. The
`render_index` fallback (`build.py:784-811`) has the same fragility (hardcoded
Jinja-syntax string replacement).

Fix: define `PHOTO_TMPL` or delete the dead fallback branches.

## Code quality / duplication

### 4. Duplicated am/pm datetime formatting
`build.py:878-898` (`_format_photo_title`) vs `build.py:1142-1152` (inline in `build_gallery`)

The `display_hour` / `ampm` conversion exists in both places.

Fix: extract one helper (e.g. `_format_time(photo_datetime)`) and reuse it.

### 5. Preview save bypasses the WebP constants
`build.py:52-53` (constants), `build.py:634` (preview save)

`WEBP_QUALITY` (90) and `WEBP_METHOD` (6) are both used for full-size images at
`build.py:662`. The preview save hardcodes `quality=80, method=6`. The lower
preview quality is intentional, but it should reference `WEBP_METHOD` rather
than re-hardcoding `6` — and ideally a separate `PREVIEW_WEBP_QUALITY` constant
so the intent is explicit.

### 6. `strip_all_metadata` does an unnecessary full image copy
`build.py:496-507`

`im.copy()` duplicates all pixel data just to pop `info` keys before save. The
pixel copy is never needed — `im.info` can be popped in place and saved
directly, halving peak memory on large images.

### 7. Source image decoded twice per photo
`build.py:912` (`convert_to_webp`) and `build.py:918` (`generate_preview`)

`_process_one_image` opens the original for the full WebP, then `generate_preview`
opens it again for the preview + color extraction. The already-converted full
WebP (or a single decode) could be reused to avoid a second decode of large
originals.

### 8. Silent image drops
`build.py:946-948` (`_process_one_image`)

All exceptions are swallowed and `None` is returned with no log, so a skipped
photo is invisible during a build.

Fix: at minimum log the filename and exception.

## Minor / design

### 9. `slugify` cross-class dependency
`build.py:198` (defined on `ImageMetadata`) used by `PreviewGenerator`
(`build.py:491`, `build.py:602`). A module-level function would be cleaner.

### 10. Caches keyed on `st_mtime`
`build.py:101` (`_get_cache_key`)

datetime/dimensions/gps caches use `filename:size:mtime`. On macOS mtime has
1-second resolution, so a content change within the same second won't invalidate
them. The preview already uses a content hash (`build.py:567-581`); consider
extending that approach to the other caches.

### 11. Docs vs code drift
`CLAUDE.md` / `AGENTS.md` describe a "month/year picker" that is not present in
`templates/index.html`. Documentation should be reconciled with the current code.

### 12. No tests
Pure functions are easily unit-testable but untested: `slugify`, EXIF datetime
parsing (`_extract_datetime_uncached`), ID dedup (`build.py:1054-1062`), and the
time formatter from #4.

## Suggested order of work
1. #1 (config bug) — correctness, easy win
2. #2 (privacy) — correctness
3. #3 (broken fallback) — correctness
4. #4, #5, #6, #7, #8 — dedupe / consistency / perf
5. #9, #10, #11, #12 — design / hygiene

## Tasks

Checklist of fixes to apply. Each item references the finding above.

- [x] **#1** Fix `--config` override. Two-pass parsing: pre-parse `--config`, load
      that file, apply its values as argparse defaults via `set_defaults` so
      custom config files are honored and CLI flags override them.
      (`build.py:1300-1380`)
- [x] **#2** Stop privacy leak on preview failure. `generate_preview` now returns
      `None` on failure instead of the original `src`; `_process_one_image`
      skips the photo in that case. (`build.py:583`, `build.py:641-643`,
      `build.py:917-921`)
- [x] **#3** Remove the broken non-Jinja2 fallback. Jinja2 is now a hard
      requirement (already in `requirements.txt`); `build.py` fails fast with a
      clear message if it is missing. `TemplateRenderer` keeps only the Jinja2
      path. (`build.py:23-28`, `build.py:717-735`, `build.py:758`, `build.py:815`)
- [x] **#4** Extract a single `_format_time(photo_datetime)` helper; reused by
      `_format_photo_title` and `build_gallery`. Removes the duplicated am/pm
      logic. (`build.py:802-819`, `build.py:1068-1071`)
- [x] **#5** Use constants for the preview save. Added `PREVIEW_WEBP_QUALITY` (80)
      and use `WEBP_METHOD` instead of hardcoded `6`.
      (`build.py:54`, `build.py:634`)
- [x] **#6** Remove the unnecessary `im.copy()` in `strip_all_metadata`; pop
      `im.info` keys in place. (`build.py:495-505`)
- [x] **#7** Decode each source image once. `convert_to_webp` and `generate_preview`
      accept a reused in-memory image opened+transposed once in `_process_one_image`.
      (`build.py:583`, `build.py:648`, `build.py:835-856`)
- [x] **#8** Log skipped photos. `_process_one_image` now warns (to stderr) with
      the filename for conversion failure, preview failure, and any unexpected
      exception. (`build.py:873`, `build.py:886`, `build.py:916`)
- [x] **#9** Move `slugify` to a module-level function; updated `PreviewGenerator`
      callers. (`build.py:48`, `build.py:492`, `build.py:603`)
- [x] **#10** Make datetime/dimensions/gps caches content-based. `_get_cache_key`
      now includes a content signature (size + first 4KB) instead of `mtime`,
      avoiding stale hits when bytes change within 1s mtime resolution.
      (`build.py:96-114`)
- [x] **#11** Reconcile docs with code. Removed the "Month/Year Picker" section
      from `AGENTS.md` (feature is not present in `index.html`). `CLAUDE.md`
      had no such references. (`AGENTS.md:192-207`)
- [x] **#12** Add unit tests (`tests/test_build.py`, unittest) for `slugify`,
      `_format_time`, EXIF `extract_datetime`, and the extracted
      `_assign_unique_ids` dedup helper. (`build.py:53`, `build.py:1042`)
