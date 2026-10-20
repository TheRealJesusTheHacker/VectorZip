# VectorZip

**Lossless file compression in pure Python — LZ77 + Huffman in a chunked, CRC32-verified `.vzip` container, with a CLI, a desktop GUI, and output-safety hardening that treats both archives and output paths as untrusted.**

[![CI](https://img.shields.io/github/actions/workflow/status/TheRealJesusTheHacker/VectorZip/ci.yml?style=flat-square)](https://github.com/TheRealJesusTheHacker/VectorZip/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.2.7-blue?style=flat-square)](https://github.com/TheRealJesusTheHacker/VectorZip/releases/latest)
[![Tests](https://img.shields.io/badge/tests-97%20passing-brightgreen?style=flat-square)](https://github.com/TheRealJesusTheHacker/VectorZip/tree/main/tests)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue?style=flat-square)](https://github.com/TheRealJesusTheHacker/VectorZip/blob/main/setup.py)
[![License](https://img.shields.io/badge/license-MPL--2.0-green?style=flat-square)](LICENSE)

## Overview

VectorZip is a *completely lossless* file compression tool built in pure
Python. It chains **LZ77** sliding-window dictionary matching with **Huffman**
entropy coding to shrink files, and every 64 KiB chunk carries a **CRC32**
checksum that is verified on decompression — so a damaged archive fails
loudly instead of silently handing you corrupt data. Decompressing a
`.vzip` file always returns byte-identical data, or an error. There is no
"close enough."

It is a real compression container format and a small family of tools
around it:

- **A compression engine** (`src/`) — LZ77 tokenization, Huffman entropy
  coding, and the `.vzip` chunked container that ties them together with
  per-chunk CRC32 integrity.
- **A command-line tool** (`main.py`, installed as `vzip`) — compress and
  decompress single files with live progress bars and safety caps,
  scriptable from anything.
- **A desktop GUI** (`gui/`, installed as `vectorzip-gui`) — a dark PyQt6
  app with drag-and-drop batch queues for people who never want to touch
  a terminal.
- **A Python library** — `compress_file` / `decompress_file` with progress
  callbacks, so other programs can embed the engine directly.
- **Standalone binaries** — PyInstaller-built `VectorZip.exe` (Windows)
  and `VectorZip` (Linux), published on every release tag with SHA256
  checksums and build-provenance attestations. No Python install required.

Nothing is compiled into the package itself: the engine is pure Python
(3.8+, per `setup.py`), which makes it portable and auditable. The CLI
needs `tqdm` for its progress bars; the GUI needs PyQt6, which is an
optional install extra so CLI-only installs stay Qt-free.

**Status:** Released — current version **1.2.7**, stated identically in
`VERSION`, `setup.py`, and `src/__init__.py` (`__version__`), and matching
the latest GitHub release ([v1.2.7](https://github.com/TheRealJesusTheHacker/VectorZip/releases/tag/v1.2.7)). Standalone binaries and portable
zips for Windows and Linux are published on the Releases page. A PyPI
release is planned but **not yet published** — see [Install](#install)
and [Status and roadmap](#status-and-roadmap). The hardening and
performance work previously listed under `[Unreleased]` in
[CHANGELOG.md](CHANGELOG.md) shipped in v1.2.5.

## Features

### Compression engine

- **Completely lossless** — byte-identical round trips, covered by a
  97-test suite and a stdlib-only decompressor fuzzer that runs in CI
  (see [Development and testing](#development-and-testing)).
- **Fast on real data, instant on junk** — incompressible chunks are
  detected and stored raw instead of being force-compressed, so random or
  already-compressed data passes through at I/O speed and never balloons
  (see the workhorse policy and the measured figures under
  [How it works](#how-it-works)).
- **Flat memory** — 64 KiB chunked processing; file size doesn't move the
  memory footprint.
- **Pure Python, portable** — no compiled extensions; runs anywhere
  Python 3.8+ runs.
- **Legacy-format reader** — files written by 1.0.0–1.2.1 (formats v1/v2,
  including v1's no-magic layout) still decompress. v2 files truncated at
  a chunk boundary could previously return partial data silently — v3's
  end-of-stream marker closes that hole for new archives.

### Integrity and anti-corruption

- **CRC32 on every chunk**, verified during decompression; any mismatch
  or truncation raises `ValueError` instead of returning bad bytes.
- **End-of-stream marker** (format v3) — the decompressor requires it, so
  a truncated v3 archive can never silently produce partial output.
- **Chunk-length caps validated before allocation** — malformed headers
  can't trick the reader into giant allocations: raw-chunk, encoded-chunk,
  and Huffman-table lengths are all bounded before any read allocates.
- **Unknown chunk flags rejected** — a chunk carrying a reserved flag bit
  is refused with `ValueError` instead of being misparsed (fail closed,
  not forward-compatible-by-accident).
- **Strict Huffman tables** — the table is parsed from untrusted input
  before any checksum runs, so table entries the encoder could never
  have written are rejected with `ValueError`: zero-length codes, codes
  longer than 64 bits, code values that overflow their declared bit
  length, and symbols listed twice. *(Partly on `main` as unreleased
  work — see CHANGELOG `[Unreleased]`.)*
- **Impossible coded chunks rejected** — a coded chunk with an empty
  Huffman table, or `pad_bits` greater than 7 (padding lives inside the
  final encoded byte, so 0–7 are the only legal values), fails with
  `ValueError`. *(Unreleased on `main`.)*
- **Torn-input detection** — `compress_file` fingerprints the input
  (inode, size, mtime) before and after the read; if anything changed it
  mid-job (concurrent writer, truncation, replacement), it raises
  `IOError` instead of writing a torn archive that looks complete.

### Output safety

The full model, including its platform limits, is under
[Security model](#security-model). In short:

- **Outputs never overwrite by default** — compressing refuses to clobber
  an existing `.vzip`; decompressing refuses to clobber its own input or
  any existing output. Pass `overwrite=True` / `--force` to opt in
  explicitly.
- **Symlink-safe opens** — fresh outputs are created atomically with
  `O_CREAT | O_EXCL` plus `O_NOFOLLOW` where the platform provides it;
  the overwrite path opens with `O_NOFOLLOW` too and aborts with a clear
  `ELOOP` error if the output path is a symlink — including a dangling
  one, whose target would otherwise be *created* by the write.
- **Hardlink-safe overwrite** — no open flag refuses a hard link, so the
  overwrite path inspects the already-open file descriptor: a
  multiply-linked output is unlinked and replaced with a fresh file at
  the same path instead of being truncated in place. The other link
  keeps its bytes — even when the planted hard link points at a victim
  file, or at the input archive itself.
- **Decompression-bomb defense** — total output is capped at 8 GiB by
  default (`--max-output-gb` to adjust, `--no-output-limit` to disable,
  or `max_output_bytes=None` in the library), and every decoded chunk is
  additionally capped at 128 KiB *during* LZ77 expansion (legit chunks
  are exactly one 64 KiB input chunk), so a malicious chunk can't force
  a huge in-memory allocation before its checksum is verified.
- **Clean `MemoryError` handling** — a corrupt archive that would exhaust
  memory fails with a clear error in CLI and GUI instead of killing the
  worker thread with a raw traceback.
- **Partial outputs quarantined** — a cancelled or failed CLI or GUI job
  renames the half-written file to `.partial` so it can never be mistaken
  for a good result. Quarantine only fires when the job actually wrote
  output: an overwrite refusal leaves the pre-existing file untouched
  instead of renaming it to `.partial`, and an existing leftover
  `.partial` is replaced rather than blocking the quarantine.

### Command line (`vzip`)

- `vzip compress path/to/file` → `path/to/file.vzip`
- `vzip decompress path/to/file.vzip` → `path/to/file.restored`
- Live tqdm progress bars with byte counts; Ctrl-C cancels cleanly (exit
  130) with the partial output quarantined.
- `--max-output-gb`, `--no-output-limit`, `--force` — the same safety
  controls as the library. `--max-output-gb` values that are NaN,
  infinite, or too large to convert to a byte count fail argument
  validation up front *(unreleased on `main`)*.

### Desktop GUI

- **Drag & drop** files or whole folders straight into the queue (or use
  *Add files*).
- **Batch queue** — compress or decompress dozens of files in one run,
  with *Remove selected* / *Clear queue* management.
- **Live progress** — per-file progress bars with byte counts in the
  queue table, plus a status bar for overall state.
- **Stat cards** — files done, original size, output size, and space
  saved for the whole batch.
- **Color-coded activity log** — every file's outcome, HTML-escaped so
  log content can't inject markup.
- **Mode switch** — Compress / Decompress with one click.
- **Custom output folder** — with browse and reset-to-default buttons.
- **Overwrite protection** — an explicit checkbox; existing outputs are
  skipped unless you opt in. The output-folder move is atomic (a
  hard-link claim for the no-clobber case — not to be confused with the
  planted-hardlink defense in the engine), and jobs whose output name
  collides with another job in the same batch are skipped up front so a
  later job can never silently replace an earlier job's result.
- **Cancel** — stops the run and quarantines partials.
- **Graceful close** — closing the window mid-batch cancels the worker
  and finishes the close once the thread has exited, instead of
  destroying a running `QThread`.
- **Remembers your setup** — window geometry, mode, output folder, and
  the overwrite choice persist between runs (platform settings store,
  via Qt `QSettings`).
- Runs jobs on a worker `QThread`, so the interface stays responsive
  during long batches.

### Python library

```python
from vectorzip import compress_file, decompress_file

out = compress_file('input.txt')              # -> 'input.txt.vzip'
restored = decompress_file(out)               # -> 'input.txt.restored'
```

Both accept a `progress` callback `(bytes_done, bytes_total)` invoked
after each chunk, and `overwrite=False` by default. `decompress_file`
also accepts `max_output_bytes` (default 8 GiB) for the
decompression-bomb cap. The low-level `lz77_compress` / `lz77_decompress`
/ `huffman_encode` / `huffman_decode` building blocks are exported too.

## Install

### Standalone binaries (no Python required)

| Platform | Download |
|----------|----------|
| Windows | [VectorZip.exe](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.2.7/VectorZip.exe) |
| Linux | [VectorZip](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.2.7/VectorZip) |

These are the windowed desktop app, built by PyInstaller from
`vectorzip.spec`. (Screenshots: none published — the GUI ships in the
binaries above and in `gui/`.)

Verify integrity before running anything — every release publishes
checksums and signed build-provenance attestations:

```powershell
# Windows
Get-FileHash VectorZip.exe -Algorithm SHA256
```

```bash
# Linux
sha256sum -c SHA256SUMS-linux.txt
```

Checksums: [SHA256SUMS-windows.txt](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.2.7/SHA256SUMS-windows.txt) · [SHA256SUMS-linux.txt](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.2.7/SHA256SUMS-linux.txt)

### Portable edition (no install)

**Shipped — available since [v1.2.5](https://github.com/TheRealJesusTheHacker/VectorZip/releases/tag/v1.2.5).** Download
[VectorZipPortable.zip](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.2.7/VectorZipPortable.zip)
(Windows) or
[VectorZipPortable-linux.zip](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.2.7/VectorZipPortable-linux.zip)
(Linux). The release workflow assembles a portable zip for each
platform, containing the standalone binary and
`packaging/portable/README-PORTABLE.txt`. Unzip it into any folder
(including a USB stick), run the app, delete the folder to remove
it. Nothing is installed and no Python is required.

These portable zips ship in the release assets, and each
platform's `SHA256SUMS-*.txt` covers the portable zip as well as
the binary.

### From source

PyPI is **planned but not yet published**: the release-triggered publish
workflow (`.github/workflows/publish-pypi.yml`, OIDC trusted publishing)
exists, but there is no live `vectorzip-py` listing on PyPI today — do
not `pip install vectorzip-py`, and note that the unrelated `vectorzip`
project on PyPI is a different package by a different author. Install
from source for now:

```bash
git clone https://github.com/TheRealJesusTheHacker/VectorZip
cd VectorZip
pip install .          # CLI + library (installs tqdm; Qt-free)
pip install .[gui]     # + the desktop GUI (adds PyQt6)
```

This installs the `vectorzip` package and the `vzip` command-line tool;
the `[gui]` extra adds the `vectorzip-gui` desktop app launcher and its
PyQt6 dependency. Requires Python 3.8+. Without installing, the CLI and
library also run straight from the repo root (`python main.py …`), which
is how the test suite uses them.

## Usage

**Desktop app:**

```bash
vectorzip-gui
# or, from the repo root: python gui_launcher.py
```

**Command line:**

```bash
vzip compress path/to/file          # -> path/to/file.vzip
vzip decompress path/to/file.vzip   # -> path/to/file.restored

# The same CLI without installing, from the repo root:
python main.py compress path/to/file
python main.py decompress path/to/file.vzip

# Safety controls
vzip decompress big.vzip --max-output-gb 2     # cap decompressed output at 2 GiB
vzip decompress big.vzip --no-output-limit     # disable the cap
vzip compress file --force                     # allow overwriting output
```

Output naming is one shared rule (`src.compressor.expected_output_path`,
used by both the CLI and the GUI): compress appends `.vzip`; decompress
replaces a trailing `.vzip` with `.restored`, or appends `.restored`
when the input name doesn't end in `.vzip`. Decompression never writes
over its own input.

**Python API:**

```python
from vectorzip import compress_file, decompress_file

out = compress_file('input.txt')              # -> 'input.txt.vzip'
restored = decompress_file(out)               # -> 'input.txt.restored'

# With progress reporting and safety controls
def show(done, total):
    print(f'{done / total:.0%}', end='\r')

out = compress_file('input.txt', progress=show)
restored = decompress_file(out, progress=show, max_output_bytes=2 * 1024**3)

# Opting in to overwriting an existing output (default is to refuse)
out = compress_file('input.txt', progress=show, overwrite=True)
```

## How it works

Compression is a pipeline that runs **per 64 KiB chunk**:

1. **Read** the next 64 KiB of the input file.
2. **Workhorse policy** — decide whether this chunk is worth compressing
   (see below). If not, the chunk is stored literally.
3. **LZ77** — greedy 3-byte hash matching over a 32 KiB sliding window
   finds repeated byte runs (match lengths 3–255) and emits fixed 4-byte
   tokens `(distance, length, next_byte)` in big-endian `>HBB` layout.
   A distance of 0 marks a literal byte; every match token carries a
   valid trailing byte, so the stream decodes unambiguously.
4. **Huffman** — frequency-based variable-length prefix codes are built
   over the LZ77 token stream, and the packed bitstream plus its
   serialized code table are written after the chunk header.
5. **CRC32** — every chunk header records the CRC32 of the *original*
   chunk bytes, so corruption is detectable on read.

Decompression reverses the pipeline — header validation, Huffman decode,
LZ77 decode, CRC check — and the v3 stream ends with an explicit
**end-of-stream marker chunk**. The decompressor *requires* that marker:
if a v3 file is truncated anywhere, it raises `ValueError` instead of
returning partial data.

### The workhorse policy

Not every chunk deserves entropy coding. Before compressing, each chunk
goes through three gates — if any says "not worth it," the chunk is
stored raw and skips LZ77+Huffman entirely:

1. **Sampling heuristic** — slices from the start, middle, and end of the
   chunk are checked for byte diversity. If ~all 256 byte values appear
   in a few KiB, this is random data; store it raw.
2. **LZ77 trial** — if the token stream isn't smaller than the chunk,
   store raw.
3. **Huffman trial** — if the code table plus bitstream overhead would
   eat the savings, store raw.

Performance figures reported in the CHANGELOG for 1.2.0, measured on
10 MB inputs:

| Input | Compress | Decompress | Size vs original |
|---|---|---|---|
| Text / repetitive | ~10 MB/s | ~15 MB/s | 0.4–1.4% |
| Random bytes | ~790 MB/s | ~340 MB/s | 100.0% (no bloat) |

Incompressible data (random bytes, zips, videos) passes through at I/O
speed instead of being force-compressed — an old version managed under
1 MB/s and *bloated* such files by ~51%. That failure mode is gone.
Memory usage stays flat no matter the file size because everything is
chunked; multi-gigabyte files compress fine on modest hardware.

### File format

`.vzip` files (v3, since 1.2.2) start with a `VZP3` magic; each chunk
carries a header of `crc32 u32 | table_len u16 | pad_bits u8 | flags u8`,
a flags byte (bit 0 = RAW, stored literally; bit 7 = END, the
end-of-stream marker; all other bits reserved and rejected), and either
the Huffman-packed LZ77 token stream or — when compression wouldn't
shrink it — the raw chunk bytes preceded by their length. Files written
by 1.2.0/1.2.1 (v2, `VZP2` magic) and 1.0.0/1.1.0 (v1, no magic, 7-byte
headers) still decompress; the reader auto-detects the format. The full
byte-level layout for all three versions is in
[docs/compression.md](docs/compression.md).

## Security model

VectorZip assumes two hostile inputs: **the archive being decompressed**
(anyone can hand you a crafted `.vzip`) and **the output path** (anyone
who can plant files in the output directory can try to redirect a
write). The defenses, as implemented in `src/compressor.py`:

### Untrusted archives

- Every length that comes from the file (raw length, encoded length,
  table length) is capped *before* the read that allocates for it.
- Total decompressed output is capped (8 GiB by default), and each
  decoded chunk is capped at 128 KiB *during* LZ77 expansion — before
  its CRC32 is verified, not after.
- CRC32 is verified per chunk; a mismatch, a truncated header/table/
  payload, an unknown flag bit, a malformed END marker, data after the
  END marker, an empty Huffman table on a coded chunk, `pad_bits > 7`,
  or a strictly-invalid Huffman table entry (zero-length code, code
  longer than 64 bits, code overflowing its declared length, duplicate
  symbol) all raise `ValueError`. The decompressor never returns partial
  output for a truncated v3 archive.
- `MemoryError` is caught at the CLI/GUI layer and reported as a clean
  error (a possible decompression bomb), not a raw traceback.

### Untrusted output paths — symlinks

- **No overwrite (default):** the existence check and the create are one
  atomic step — `os.open` with `O_CREAT | O_EXCL`, plus `O_NOFOLLOW`
  where the platform provides it. Anything already at the output path,
  symlink included, raises `FileExistsError` and is never followed.
- **Overwrite (`--force` / `overwrite=True`):** the output path is
  checked for a symlink first (every platform), then opened with
  `O_NOFOLLOW` (where available) *without* truncating first. A
  symlink at the output path — live or dangling — fails with `OSError`
  (`ELOOP`) and a message naming the refusal, and the link target is
  never touched. Regression tests plant real symlinks and assert the
  victim file stays byte-identical for both compress and decompress, in
  both modes (`tests/test_symlink_output_safety.py`), including with
  `O_NOFOLLOW` simulated as absent — the Windows shape
  (`tests/test_kithunt_windows.py`).

### Untrusted output paths — hard links

Symlink defenses don't cover hard links: there is no `O_NOFOLLOW`
equivalent for them, and a plain truncating open of a multiply-linked
output path would clobber *every* file sharing that inode — which can
be a victim file, or even the input file itself (truncated while it is
being read). The overwrite path therefore:

1. Opens the existing output without `O_TRUNC` and inspects the
   **already-open file descriptor** with `fstat` — a path swap after the
   open cannot redirect an fd.
2. If `st_nlink > 1`, it closes the fd, **unlinks the output name, and
   creates a fresh file** there with `O_CREAT | O_EXCL` (so a name
   planted in the gap fails the open instead of being followed). The
   output path still ends up holding the new content; the other link
   keeps its bytes.
3. If the file is singly linked, it is truncated in place exactly as
   before — the legitimate `--force` behavior is unchanged.

Regression tests plant real hard links for compress and decompress —
victim-file and output-linked-to-the-input cases — and assert both
halves of the contract (`tests/test_hardlink_output_safety.py`).

### Platform caveat — read this honestly

`O_NOFOLLOW` is a POSIX facility. The code requests it with
`getattr(os, 'O_NOFOLLOW', 0)`. On platforms that don't provide it —
notably Windows — the overwrite path instead refuses up front when
the output path **is** a symlink (`os.path.islink`), which closes the
pre-planted-symlink case on every platform. The residual on Windows
is the check-to-open gap: a symlink swapped in *between* that check
and the open could still be followed, because Windows has no atomic
open flag for it; on POSIX the `O_NOFOLLOW` open closes the same gap
atomically. The no-overwrite path is protected everywhere by the
atomic `O_EXCL` create. The hardlink defense has the analogous
residual caveat: it depends on the platform reporting a link count —
where `st_nlink` is reported as 1 regardless, the in-place path is
taken. Be correspondingly careful with `--force` in shared output
directories on Windows.

### Other boundaries

- Decompression never overwrites its own input (`.vzip` →
  `.restored` naming, plus an explicit same-path refusal).
- Compression detects an input that changed mid-job and refuses to
  produce a torn archive (see [Features](#features)).
- Failed or cancelled jobs quarantine half-written outputs to
  `.partial` (see [Features](#features)).
- Every raw-fd output open (engine fresh-create and overwrite, and
  the GUI's no-clobber move fallback) requests `O_BINARY` where the
  platform provides it, so on Windows no archive byte is ever subject
  to text-mode newline translation.
- CRC32 is an integrity check against corruption and casual tampering,
  **not** a cryptographic authenticity check — VectorZip does not sign
  archives, and a CRC match does not prove who wrote a file. For the
  release binaries, authenticity comes from the published SHA256
  checksums and build-provenance attestations instead.

Found a vulnerability? Please report it privately — see
[SECURITY.md](SECURITY.md) (reports go to Sentinelsafeguard@outlook.com;
do not open a public issue for a security problem). That policy covers
this repository and the binaries published under Releases.

## Configuration

There is no configuration file and no environment-variable interface.
Behavior is controlled in exactly three places:

**CLI flags** (`vzip` / `python main.py`):

| Flag | Default | Effect |
|---|---|---|
| `--force` | off | Allow overwriting an existing output file. |
| `--max-output-gb GB` | 8 GiB cap | Cap total decompressed output, in GiB. Must be positive. |
| `--no-output-limit` | off | Disable the decompression output cap entirely. |

**Library parameters** (`compress_file` / `decompress_file`):

| Parameter | Default | Effect |
|---|---|---|
| `progress` | `None` | Callback `(bytes_done, bytes_total)` invoked after each chunk. |
| `overwrite` | `False` | Allow clobbering an existing output. |
| `max_output_bytes` | `8 * 1024**3` (decompress only) | Total-output cap in bytes; `None` disables it. |

**GUI preferences** — the desktop app persists window geometry, mode,
output folder, and the overwrite checkbox between runs through Qt
`QSettings` (application/organization name `VectorZip`), which lands in
the platform's standard settings store. There is nothing to edit by
hand.

Packaging is configured in `setup.py` (package name `vectorzip-py`,
console scripts `vzip` and `vectorzip-gui`, the `[gui]` extra), and
lint/format style in `pyproject.toml` (black and ruff, 100-column lines,
single-quote-preserving). Runtime pins live in `requirements.txt`
(`tqdm==4.70.1`, `PyQt6==6.11.0` — the latter is for the GUI and the
release builds; a plain `pip install .` does not require it).

## Components

| Path | What it does |
|---|---|
| `src/lz77.py` | LZ77 compressor/decompressor: 32 KiB window, greedy 3-byte hash matching, `>HBB` tokens, optional per-call output cap. |
| `src/huffman.py` | Huffman encoder/decoder (table-driven decode with a 9-bit lookup), plus strict code-table serialization/deserialization for the container format. |
| `src/compressor.py` | The engine: `compress_file` / `decompress_file`, `expected_output_path`, the workhorse policy, format v1/v2/v3 readers, output-cap enforcement, and all the overwrite/symlink/hardlink safety logic. |
| `src/__init__.py` | Public API surface and `__version__` (`1.2.7`). |
| `main.py` | The `vzip` CLI: argument parsing, tqdm progress bars, cancel/OOM/failure quarantine of partial outputs. |
| `gui/` | The PyQt6 desktop app: main window, worker thread, queue table, stat cards, styled log, atomic no-clobber output-folder move, batch duplicate-output planning. |
| `gui_launcher.py` | `vectorzip-gui` entry point. |
| `vectorzip.spec` | PyInstaller spec for the standalone release binaries (windowed, no console). |
| `tests/` | The pytest suite — 97 tests across eight files; see [Development and testing](#development-and-testing). |
| `tests/fuzz_decompress.py` | Stdlib-only decompressor fuzzer (also runs in CI). |
| `tests/benchmark.py` | Dev-only throughput benchmark harness. |
| `docs/compression.md` | Algorithm and container-format documentation for v1/v2/v3. |
| `.github/workflows/` | `ci.yml`, `fuzz.yml`, `codeql.yml`, `release.yml`, and `publish-pypi.yml` (release-triggered; PyPI publishing itself is still pending — see below). |

## Who it's for

- **Everyday users** who want drag-and-drop lossless archiving with loud,
  verifiable integrity — the GUI needs no technical background.
- **Scripters and sysadmins** who need a dependable `vzip` one-liner with
  sane safety defaults in pipelines.
- **Python developers** who want an embeddable, auditable, pure-Python
  compressor with progress callbacks.

## Development and testing

```bash
git clone https://github.com/TheRealJesusTheHacker/VectorZip
cd VectorZip
pip install -r requirements-dev.txt   # pytest (pinned) + runtime deps
python -m pytest tests/ -q            # 97 tests
```

The suite is **97 tests**, collected and run from the current tree:

| File | Tests | Covers |
|---|---|---|
| `tests/test_compression.py` | 37 | Round trips at every size from empty to multi-chunk, chunk/window boundary conditions, byte-flip and truncation corruption, legacy v1/v2 archives, overwrite refusal, output caps, cancel behavior, torn-input detection, unknown chunk flags. |
| `tests/test_audit2_concurrency.py` | 17 | GUI worker behavior (with a stubbed PyQt6): atomic no-clobber move, batch duplicate-output planning, quarantine semantics, graceful close. |
| `tests/test_bughunt2_strictness.py` | 14 | Strictness regressions for malformed inputs and CLI validation. |
| `tests/test_huffman_table_strictness.py` | 8 | Huffman table rejection cases (zero-length, overlong, overflowing, duplicate) plus the accepted 64-bit boundary and normal round trips. |
| `tests/test_hardlink_output_safety.py` | 6 | Planted-hardlink overwrite attacks for compress and decompress (victim and input-linked cases), in-place truncation for singly-linked files, CLI quarantine replacing a leftover `.partial`. |
| `tests/test_symlink_output_safety.py` | 5 | Planted-symlink attacks for compress and decompress in both modes, dangling symlinks, and the legitimate overwrite path. POSIX-only. |
| `tests/test_kithunt_windows.py` | 7 | Windows-shaped regressions: planted-symlink overwrite with `O_NOFOLLOW` absent, `O_BINARY` requested on every raw-fd output open, GUI worker signals carrying 64-bit byte counts (live PyQt6 probe). |
| `tests/test_huffman_decode_padding.py` | 3 | `huffman_decode` padding validation: negative and oversized padding raise `ValueError`; boundary values still decode. |

**Fuzzing.** `tests/fuzz_decompress.py` is stdlib-only: it builds a seed
corpus of valid archives in all three format versions, then feeds
mutated, truncated, spliced, and random bytes into `decompress_file` and
asserts that no exception other than `ValueError` / `MemoryError`
escapes and no single case hangs (per-case timeout, SIGALRM on Unix).
CI (`.github/workflows/fuzz.yml`) runs it for a **300-second budget** on
every push to `main` touching `src/` or `tests/`, plus weekly on a
schedule (Sunday 03:00 UTC). Run it locally with:

```bash
python tests/fuzz_decompress.py --seconds 300   # --seed and --case-timeout also available
```

Historically, the 1.2.2 integrity work was verified with 196 fuzz
round-trips across sizes 0–200 KB, a truncate-at-every-offset sweep, and
3000 byte-flip trials (see CHANGELOG).

**CI** (`.github/workflows/ci.yml`) runs on every push and pull request
to `main`: byte-compilation on Linux and Windows (Python 3.11), the full
pytest suite on **both** Linux and Windows, a frozen-app start smoke on
Windows (the release spec's exe is built and launched, offscreen, and
must still be running seconds later — the release workflow runs the
same smoke before anything is uploaded), a CLI compress → decompress →
byte-compare round trip, and ruff + black checks with pinned tool
versions and the `pyproject.toml` style config. CodeQL analysis runs via
`.github/workflows/codeql.yml`.

**Building the standalone app:**

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm vectorzip.spec   # -> dist/VectorZip(.exe)
```

The portable zips are assembled by the same script CI runs
(`packaging/portable/build-portable.py`):

```bash
python packaging/portable/build-portable.py --binary dist/VectorZip.exe --output dist/VectorZipPortable.zip
```

Tagged releases (`v*`) are built automatically by GitHub Actions for
Windows and Linux, with the portable zips, SHA256 checksums, and
signed build-provenance attestations attached to the release.

## Status and roadmap

- **Current release: 1.2.7** (2026-10-20) — standalone Windows and Linux
  binaries and portable zips on the Releases page, with checksums and
  attestations: [v1.2.7](https://github.com/TheRealJesusTheHacker/VectorZip/releases/tag/v1.2.7).
- **Shipped in 1.2.7:** the namesake "blueprint" palette — the GUI's
  colors now live in a single theme module (`gui/theme.py`) carrying the
  graphite-slate + blueprint-cyan identity, with the fleet danger red
  for destructive actions. Colors only: no behavior, layout, wording,
  or format change, and the 1.2.6 Windows fixes stand untouched.
- **Shipped in 1.2.6:** the Windows kit-hunt fixes — overwrite no longer
  follows a planted symlink on platforms without `O_NOFOLLOW` (Windows
  included), every raw-fd output open requests `O_BINARY`, and the GUI
  worker's signals carry 64-bit byte counts so jobs past 2 GiB no
  longer report wrapped/negative progress and stats. CI now runs the
  full test suite on Windows and smoke-launches the frozen exe; the
  release workflow runs the same start smoke before uploading.
- **Shipped in 1.2.5:** stricter container/Huffman-table validation
  (empty table, `pad_bits`, table-entry strictness), CLI
  `--max-output-gb` validation, output-path symlink/hardlink hardening,
  and decoder performance work that does not change the on-disk format
  (LZ77 slice/repeat match copies; a 9-bit lookup table in Huffman
  decode; one parameterized chunk loop for v1/v2/v3; the output-path
  naming rule unified in `expected_output_path`).
- **Portable edition: shipped with v1.2.5.**
  `VectorZipPortable.zip` (Windows) and `VectorZipPortable-linux.zip`
  (Linux) are assembled by the release workflow and attached to the
  [v1.2.5 release](https://github.com/TheRealJesusTheHacker/VectorZip/releases/tag/v1.2.5)
  (see [Portable edition](#portable-edition-no-install)).
- **PyPI: pending, owner-side.** The trusted-publisher publish workflow
  is in the repo and fires on release publication, but the
  `vectorzip-py` project is not live on PyPI yet — until it is, install
  from source or use the release binaries, exactly as
  [Install](#install) describes.
- **Format direction:** v3 is the current write format; v1/v2 reading is
  permanent — old archives must keep decompressing.

All notable changes are documented in [CHANGELOG.md](CHANGELOG.md),
following the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
format and Semantic Versioning.

## Contact

Business inquiries: **Sentinelsafeguard@outlook.com**

## License

Mozilla Public License 2.0 — see [LICENSE](LICENSE).

## Donations

If this tool earned its keep, BTC is welcome:

```
bc1qvydns2fmyjzj55wzxq7ta28nxdhcmu9l9m6yg0
```
