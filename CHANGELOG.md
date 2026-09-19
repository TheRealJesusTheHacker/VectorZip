# Changelog

All notable changes to VectorZip are documented here.

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
