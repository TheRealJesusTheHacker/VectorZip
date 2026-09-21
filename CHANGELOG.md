# Changelog

All notable changes to VectorZip are documented here.

## [1.2.2] — 2026-09-20

**The integrity fix.** Bug hunt on the compression core found a real data
hole: an archive truncated exactly at a chunk boundary (or down to just the
magic) decompressed silently to partial/empty data with no error. Format v3
closes it: every archive now ends with an explicit end-of-stream marker
chunk (`VZP3` magic), and the decompressor raises `ValueError` if the file
ends without one. Files written by 1.2.0/1.2.1 (v2) and 1.0.0/1.1.0 (v1)
still decompress. Also fuzzed 196 round-trips across sizes 0–200 KB
(including 32 KiB window and 64 KiB chunk boundaries) plus a full
truncate-at-every-offset sweep and 3000 byte-flip trials — no other bugs.

## [1.2.1] — 2026-09-20

**The launch fix.** The GUI exe crashed immediately on startup with
`AttributeError: End` — the log widget scrolled to the bottom of the log with
`QTextCursor.MoveMode.End`, an enum value that doesn't exist in PyQt6. Fixed to
`QTextCursor.MoveOperation.End`. The app now launches and the log scrolls
correctly.

## [1.2.0] — 2026-09-19

**The workhorse update.** Speed is the feature: incompressible data now flies
through instead of choking the entropy coder.

### Added
- Format v2 `.vzip` container: `VZP2` magic + per-chunk flags byte. Files from
  1.0.0/1.1.0 (format v1) still decompress — the reader auto-detects.
- Raw-store fallback: chunks that wouldn't shrink are stored literally.
  Random/already-compressed data compresses at ~800 MB/s, decompresses at
  ~340 MB/s, and never grows (was: <1 MB/s and +51% size).

### Changed
- LZ77 sliding window widened 4 KiB → 32 KiB: better ratios on text and code
  at the same speed.
- Incompressible-input sampling heuristic skips LZ77+Huffman before they can
  waste time.

### Performance (measured, 10 MB inputs)
- Text/repetitive: ~10 MB/s compress, ~15 MB/s decompress, 0.4–1.4% of original
- Random bytes: ~790 MB/s compress, ~340 MB/s decompress, 100.0% (no bloat)
- Still 100% lossless: every byte verified identical on round-trip.

### Tests
- 8 new tests (31 total): v2 magic, no-expansion guarantee, mixed
  compressible+random chunks, v1 legacy files (normal and expanded) still
  decompress, corrupt raw chunks rejected, tiny corrupt files rejected.

## [1.1.0] — 2026-09-19

**The desktop release.** VectorZip grows a full graphical app and one-click
installers, while staying 100% lossless under the hood.

### Added
- Desktop GUI (`gui_launcher.py`): dark, modern interface with drag-and-drop
  file queue, batch compress/decompress, live progress bars, per-file and
  batch statistics (original size, output size, space saved), custom output
  folder, overwrite protection, and a color-coded activity log.
- PyInstaller packaging (`vectorzip.spec`): standalone `VectorZip.exe`
  (Windows, windowed) and `VectorZip` (Linux) — no Python install required.
- GitHub Actions release workflow: pushing a `v*` tag builds the Windows
  `.exe` and Linux binary with SHA256 checksums and attaches them to the
  GitHub release automatically.
- GitHub Actions CI: byte-compile checks on Linux and Windows plus the full
  pytest suite on every push to `main`.
- `CHANGELOG.md`, `VERSION` file, and `requirements-dev.txt` (test deps).

### Changed
- README rewritten with GUI walkthrough, download links, and install guide.
- Version bumped to 1.1.0 across `src/__init__.py`, `setup.py`, `VERSION`.

## [1.0.0] — 2026-09-19

First tagged release — the compression pipeline fully repaired.

### Fixed
- LZ77 compressor dropped most literal bytes and all trailing bytes; now
  compresses coherently with fixed big-endian `>HBB` tokens.
- Decompressor import was broken (`lz77_decompress` did not exist).
- Huffman tables were discarded, so decompression always failed CRC; tables
  are now serialized per chunk and reconstructed on decode.
- Single-symbol Huffman input encoded to empty output; now uses code `0`.
- `decompress_file` could truncate and destroy its own input; it now refuses
  to overwrite its input and writes to a safe `.restored` path.

### Removed
- Dead, incompatible Cython fast path (`src/lz77_fast.pyx`, `build.py`).

### Verified
- Byte-identical round trips for empty input, one byte, 10,000 repeated
  zeros, short text, all 256 byte values, 1 KiB random data, and 1 MiB
  repetitive data. Full suite: **23/23 tests passing**.
