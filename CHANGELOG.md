# Changelog

All notable changes to VectorZip are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.8] — 2026-10-21

**GUI honesty fixes** (fleet sweep #3). No engine, format, or CLI change.

### Fixed
- A cancelled batch no longer reports success it didn't earn: the
  completion path jumped the progress bar to 100% and announced
  "Finished" even when the user had cancelled. It now reads
  "Cancelled after …", keeps the bar where the work stopped, and
  logs the batch as cancelled (the files completed before the
  cancel are still counted).
- When a finished file could not be moved into the chosen output
  folder because a file with that name already existed there, the
  result was a bare "Output exists" that never said the finished
  file had been kept — every other move failure already named the
  kept location. The refusal now names it too.

### Tests
- New `tests/test_gui_finished_state.py`: subprocess probes against
  real PyQt6 (cancelled vs completed completion state, and the
  move-refusal message with the kept file verified on disk). Suite:
  107 passed in the Qt environment.


## [1.2.7] — 2026-10-20

**The namesake palette release.** VectorZip's GUI gets the identity its
name calls for — vectors, blueprints, precision: a graphite-slate
surface ruled with blueprint-cyan lines and pale-cyan fine detail,
replacing the earlier electric-cyan dark theme. This is a colors-only
release: no behavior, layout, wording, or on-disk format change, and
the v1.2.6 Windows kit-hunt fixes (symlink-refusing overwrite,
`O_BINARY` output descriptors, 64-bit progress signals, the Windows CI
gate) are byte-for-byte untouched.

### Changed
- GUI colors are centralized in a new single-source theme module,
  `gui/theme.py`; the main window imports every color from it and no
  color literals remain anywhere else in `gui/`. The danger button now
  uses the fleet danger red (`#b03a2e`) shared by every Sentinel tool —
  a dark-red border at rest and a red fill with white text on hover —
  while error *text* keeps the brighter signal red, which is the
  readable form of red on these dark surfaces.
- Theme tests (`tests/test_gui_theme.py`) pin the palette's exact
  values, the alias wiring, the no-purple rule, and WCAG contrast
  ≥4.5:1 for every text/background pair the stylesheet renders
  (worst pair: disabled text on panel, 5.65:1).

## [1.2.6] — 2026-10-20

**The Windows kit-hunt release.** A physical Windows test of the
Technician's Toolkit bundle exposed defects in sibling tools that no
Linux process had caught, so VectorZip was hunted specifically for
Windows-shaped, frozen-build, and clean-machine failures before the
next physical test. Three real defects were found, each with a
regression pin proven to fail on the pre-fix code; the on-disk format
did not change and archives written by earlier versions decompress
exactly as before.

### Security
- Overwrite (`--force` / `overwrite=True`) no longer follows a planted
  symlink on platforms without `O_NOFOLLOW` — notably Windows, where
  the flag contributes 0 and the write previously went straight
  through the link and clobbered its target. The overwrite path now
  refuses up front when the output path is a symlink (same `ELOOP`
  refusal as POSIX), on every platform. Residual, documented in the
  README security model: on Windows a symlink swapped in between that
  check and the open could still be followed (no atomic flag exists);
  POSIX keeps the atomic `O_NOFOLLOW` guarantee.
- Every raw-fd output open now requests `O_BINARY` where the platform
  provides it (engine fresh-create and overwrite opens, and the GUI
  worker's no-clobber move fallback copy). On Windows an fd without
  it is text-mode, which can translate `0x0A` bytes in an archive to
  CRLF and corrupt the file on disk — the failure class that damaged
  a sibling tool's key file on a physical Windows test.

### Fixed
- GUI worker signals now carry 64-bit byte counts (`qint64`) instead
  of 32-bit Qt `int`. Past 2 GiB, a job's progress and per-file sizes
  wrapped to negative values on the receiving side, corrupting the
  progress display and the batch statistics for exactly the
  multi-gigabyte files the engine is built for. Proven with a live
  PyQt6 probe (3 GB / 5 GB counts arrive exact, not wrapped).

### Changed
- CI now runs the full pytest suite on `windows-latest` as well as
  Linux (Windows previously got only a byte-compile), and both CI and
  the release workflow build the frozen exe from the release spec on
  Windows and smoke-launch it (offscreen Qt; the app must still be
  running seconds later) — in the release workflow, before any asset
  is uploaded. `ci.yml` also accepts manual dispatch.
- 7 new tests (97 total) in `tests/test_kithunt_windows.py`.

## [1.2.5] — 2026-10-20

**The portable release.** This release's headline is packaging: the
portable editions — `VectorZipPortable.zip` (Windows) and
`VectorZipPortable-linux.zip` (Linux) — ship as release assets for
the first time, alongside the standalone binaries and per-platform
`SHA256SUMS-*.txt` checksums covering the zips. It also carries the
real product work merged since v1.2.4 and previously listed under
Unreleased: stricter container/Huffman validation, output-path
symlink/hardlink hardening, CLI/GUI fixes, and decoder performance
work that does not change the on-disk format.

### Added
- Portable edition packaging: the release workflow now assembles
  `VectorZipPortable.zip` (Windows) and `VectorZipPortable-linux.zip`
  (Linux) — the standalone binary plus
  `packaging/portable/README-PORTABLE.txt`, built by
  `packaging/portable/build-portable.py` — and attaches them to the
  release with checksums and build-provenance attestations covering
  the zips. No installer, no Python required. These zips ship for
  the first time in this release (v1.2.5); they were not in the
  1.2.4 assets.

### Security
- The container reader now rejects two coded-chunk shapes the encoder
  could never have written: a chunk whose Huffman table is empty (its
  payload bytes were previously skipped undecoded, satisfying only the
  CRC32 of empty input) and `pad_bits` greater than 7 (padding lives
  inside the final encoded byte, so 0–7 are the only legal values).
  Both fail with `ValueError` like other malformed chunks. No archive
  produced by any released version is affected — every writer emits
  coded chunks only for non-empty input (non-empty table) and computes
  `pad_bits` as `(8 - nbits % 8) % 8`.
- Output-path hardening on overwrite: a planted symlink at the output
  path is no longer followed, and a planted hard link can no longer
  cause the linked file (including the input file itself) to be
  clobbered on overwrite.
- `huffman_decode` now rejects out-of-range padding with `ValueError`
  (previously an `IndexError` for negative values and silent
  truncation for oversized values).

### Fixed
- CLI: `--max-output-gb` values that are NaN, infinite, or too large
  to convert to a byte count now fail argument validation (exit 2)
  instead of escaping it and surfacing as a mid-operation error.

- CLI quarantine now uses `os.replace`, so a leftover `.partial`
  cannot strand a half-written output under its good name (GUI parity).
- CLI and GUI progress no longer exceed 100% on decompress, and a
  failed GUI output-folder move no longer quarantines the completed
  archive.

### Performance
- `lz77_decompress` copies matches with slice/repeat operations and
  iterates tokens with `struct.iter_unpack` instead of appending byte by
  byte — roughly 1.6–2.3× faster depending on the data.
- `huffman_decode` resolves most symbols through a 9-bit lookup table
  over a bit accumulator (long codes and stream tails still walk the
  decode tree, so output and error behavior are unchanged) — roughly
  1.4–1.9× faster. `huffman_encode` uses list-indexed code tables for a
  small gain. Compressed output is byte-for-byte identical to before:
  the on-disk format and the encoder's decisions did not change, and
  archives written by earlier versions decompress exactly as before.

### Changed
- The three per-version decompression chunk loops (v1/v2/v3) are one
  parameterized loop with the same validation order and error messages,
  and the CLI/GUI output-path naming rule now lives in one place
  (`src.compressor.expected_output_path`).

### Security
- `deserialize_table` now rejects Huffman table entries the encoder could
  never have written, instead of silently reinterpreting them: zero-length
  codes, codes longer than 64 bits (a real 64 KiB chunk tops out near 26;
  the cap only excludes hand-crafted tables), code values that overflow
  their declared bit length, and symbols listed twice. The table is parsed
  from the untrusted input file before any checksum runs, so malformed
  tables now fail fast with `ValueError` rather than building a decode
  tree the format never intended. No legitimately produced archive is
  affected — regression tests cover both the rejections and the
  boundary (a 64-bit code is still accepted).

## [1.2.4] — 2026-10-11

### Security
- Per-chunk decoded-output cap (128 KiB, enforced during LZ77 expansion):
  a malicious chunk can no longer force a multi-hundred-MiB in-memory
  expansion before its checksum is verified (the 8 GiB total-output cap
  only caught it after the fact).
- Partial outputs are now quarantined to `.partial` on *any* failed CLI or
  GUI job, not just cancelled/out-of-memory ones — a corrupt archive can no
  longer leave a half-written file that looks like a finished result.
- Unknown chunk flag bits are rejected with `ValueError` instead of being
  misparsed (v3 allows only RAW/END; v2 only RAW — v2 never had an END
  marker, so `0x80` there is foreign).

### Fixed
- Overwrite refusals no longer quarantine: a CLI/GUI job that fails with
  `FileExistsError` used to rename the *pre-existing* good output to
  `.partial` — the refusal path now leaves it untouched (quarantine only
  fires when the job actually wrote output).
- `compress_file` now fingerprints the input (inode, size, mtime) and
  raises `IOError` if it changed mid-job, instead of silently writing a
  torn archive that looks complete.
- GUI worker: the output-folder move is now atomic — a hard-link claim
  (`O_EXCL`-claimed copy across filesystems) with `overwrite=False`, a
  single `os.replace` with `overwrite=True` — closing the check-then-move
  overwrite race and the Windows rename-replace workaround.
- GUI pre-flight now skips batch jobs whose output name collides with
  another job in the batch, so a later job can never silently replace (or,
  on refusal, quarantine) an earlier job's good output.
- Closing the GUI mid-batch no longer destroys a running `QThread` (a hard
  Qt crash): the close cancels the worker and completes once the thread
  has exited.
- GUI queue no longer throws if a file vanishes between the dialog/drop
  and enqueue — it is skipped with a log line.

### Added
- Lint/format enforcement in CI (ruff + black) with pinned versions and a
  matching `pyproject.toml` config.
- CLI compress → decompress → byte-compare round-trip as a CI job.
- GitHub issue (bug/feature) and pull request templates.
- Detailed README feature rundown with verification notes.
- 16 new tests (53 total): torn-input detection, unknown chunk flags,
  CLI/GUI quarantine semantics on refusal, atomic no-clobber move, batch
  duplicate-output planning, and cancel-mid-job.

## [1.2.3] — 2026-10-10

**The hardening release.** Two full security audits plus performance passes.

### Security
- Decompression bombs closed: chunk-length caps validated before allocation,
  plus an 8 GiB total-output cap (`--max-output-gb` / `--no-output-limit` to override)
- `MemoryError` now fails cleanly in CLI and GUI instead of killing the thread
- `compress`/`decompress` refuse to overwrite existing outputs without
  `overwrite=True` / `--force`; atomic `O_EXCL` opens (`O_NOFOLLOW` where available)
- Cancelled CLI jobs quarantine partial outputs to `.partial`
- CI least-privilege; pip dependencies and GitHub Actions pinned to SHAs

### Performance
- Huffman decode rewritten table-driven; encode uses a bit-buffer
  (fixed an O(n²) accumulator regression: 694 ms → 70 ms per 64 KiB chunk)
- Integer codes precomputed once per table

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
