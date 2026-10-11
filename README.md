# VectorZip

[![CI](https://github.com/TheRealJesusTheHacker/VectorZip/actions/workflows/ci.yml/badge.svg)](https://github.com/TheRealJesusTheHacker/VectorZip/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/TheRealJesusTheHacker/VectorZip)](https://github.com/TheRealJesusTheHacker/VectorZip/releases/latest)
[![License](https://img.shields.io/badge/license-MPL--2.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](setup.py)
[![Tests](https://img.shields.io/badge/tests-34%2F34_passing-brightgreen)](tests/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)](#downloads)

**VectorZip** is a *completely lossless* file compression tool built in pure
Python. It chains **LZ77** sliding-window dictionary matching with **Huffman**
entropy coding to shrink files, and every 64 KiB chunk carries a **CRC32**
checksum that is verified on decompression — so a damaged archive fails loudly
instead of silently handing you corrupt data. Decompressing a `.vzip` file
always returns byte-identical data, or an error. There is no "close enough."

## What it is, in detail

VectorZip is a real compression container format and a small family of tools
around it:

- **A compression engine** (`src/`) — LZ77 tokenization, Huffman entropy
  coding, and the `.vzip` chunked container that ties them together with
  per-chunk CRC32 integrity.
- **A command-line tool** (`main.py`, installed as `vzip`) — compress and
  decompress single files with live progress bars and safety caps, scriptable
  from anything.
- **A desktop GUI** (`gui/`, installed as `vectorzip-gui`) — a dark,
  modern PyQt6 app with drag-and-drop batch queues for people who never want
  to touch a terminal.
- **A Python library** — `compress_file` / `decompress_file` with progress
  callbacks, so other programs can embed the engine directly.
- **Standalone binaries** — PyInstaller-built `VectorZip.exe` (Windows) and
  `VectorZip` (Linux), published on every release tag with SHA256 checksums
  and build-provenance attestations. No Python install required.

Nothing is compiled into the package itself: the engine is pure Python 3
(3.8+), which makes it portable and auditable. The GUI needs PyQt6 and the
CLI needs tqdm for its progress bars — both pinned to exact versions.

## How it works

Compression is a pipeline that runs **per 64 KiB chunk**:

1. **Read** the next 64 KiB of the input file.
2. **Workhorse policy** — decide whether this chunk is worth compressing
   (see below). If not, the chunk is stored literally.
3. **LZ77** — greedy 3-byte hash matching over a 32 KiB sliding window finds
   repeated byte runs (match lengths 3–255) and emits fixed 4-byte tokens
   `(distance, length, next_byte)` in big-endian `>HBB` layout. A distance of
   0 marks a literal byte.
4. **Huffman** — frequency-based variable-length prefix codes are built over
   the LZ77 token stream, and the packed bitstream plus its code table are
   written after the chunk header.
5. **CRC32** — every chunk header records the CRC32 of the *original* chunk
   bytes, so corruption is detectable on read.

Decompression reverses the pipeline — CRC check, Huffman decode, LZ77
decode — and the stream ends with an explicit **end-of-stream marker chunk**.
The decompressor *requires* that marker: if a file is truncated anywhere, it
raises `ValueError` instead of returning partial data.

### The workhorse policy

Not every chunk deserves entropy coding. Before compressing, each chunk goes
through three gates — if any says "not worth it," the chunk is stored raw and
skips LZ77+Huffman entirely:

1. **Sampling heuristic** — a few slices of the chunk are checked for byte
   diversity. If ~all 256 byte values appear in a few KiB, this is random
   data; store it raw.
2. **LZ77 trial** — if the token stream isn't smaller than the chunk, store
   raw.
3. **Huffman trial** — if the code table plus bitstream overhead would eat the
   savings, store raw.

Measured performance on 10 MB inputs (from the 1.2.0 changelog):

| Input | Compress | Decompress | Size vs original |
|---|---|---|---|
| Text / repetitive | ~10 MB/s | ~15 MB/s | 0.4–1.4% |
| Random bytes | ~790 MB/s | ~340 MB/s | 100.0% (no bloat) |

Incompressible data (random bytes, zips, videos) passes through at I/O speed
instead of being force-compressed — an old version managed under 1 MB/s and
*bloated* such files by ~51%. That failure mode is gone. Memory usage stays
flat no matter the file size because everything is chunked; multi-gigabyte
files compress fine on modest hardware.

## Components

| Path | What it does |
|---|---|
| `src/lz77.py` | LZ77 compressor/decompressor: 32 KiB window, greedy 3-byte hash matching, `>HBB` tokens. |
| `src/huffman.py` | Huffman encoder/decoder plus code-table serialization for the container format. |
| `src/compressor.py` | The engine: `compress_file` / `decompress_file`, the workhorse policy, format v1/v2/v3 readers, output-cap enforcement, and all the overwrite/atomicity safety logic. |
| `src/__init__.py` | Public API surface and `__version__`. |
| `main.py` | The `vzip` CLI: argument parsing, tqdm progress bars, cancel/OOM quarantine of partial outputs. |
| `gui/` | The PyQt6 desktop app: main window, worker thread, queue table, stat cards, styled log. |
| `gui_launcher.py` | `vectorzip-gui` entry point. |
| `vectorzip.spec` | PyInstaller spec for the standalone release binaries. |
| `tests/test_compression.py` | 34 pytest round-trip / corruption / legacy-format / safety tests. |
| `tests/fuzz_decompress.py` | Stdlib-only decompressor fuzzer (also runs in CI). |
| `tests/benchmark.py` | Dev-only throughput benchmark harness. |
| `docs/compression.md` | Algorithm and container-format documentation. |

## Feature rundown

### Compression engine
- **Completely lossless** — byte-identical round trips, verified by 34 unit
  tests and tens of thousands of fuzz cases (24,767 recent round-trip fuzz
  cases, 0 failures).
- **Fast on real data, instant on junk** — ~10 MB/s on compressible files;
  random/already-compressed data stores raw at ~800 MB/s and never balloons.
- **Flat memory** — 64 KiB chunked processing; file size doesn't move the
  memory footprint.
- **Pure Python, portable** — no compiled extensions; runs anywhere Python
  3.8+ runs.
- **Legacy-format reader** — files written by 1.0.0–1.2.1 (formats v1/v2,
  including v1's no-magic layout) still decompress. v2 files truncated at a
  chunk boundary could previously return partial data silently — v3's
  end-of-stream marker closes that hole.

### Integrity and anti-corruption
- **CRC32 on every chunk**, verified during decompression; any mismatch or
  truncation raises `ValueError` instead of returning bad bytes.
- **End-of-stream marker** (format v3) — the decompressor requires it, so a
  truncated archive can never silently produce partial output.
- **Chunk-length caps validated before allocation** — malformed headers can't
  trick the reader into giant allocations.

### Safety hardening
- **Outputs never overwrite by default** — compressing refuses to clobber an
  existing `.vzip`; decompressing refuses to clobber its own input or any
  existing output. Pass `overwrite=True` / `--force` to opt in explicitly.
- **Atomic, symlink-safe opens** — outputs are created with `O_EXCL`, and
  `O_NOFOLLOW` where the platform supports it, so a symlink at the output
  path is never followed.
- **Decompression-bomb defense** — total output is capped at 8 GiB by default
  (`--max-output-gb` to adjust, `--no-output-limit` to disable, or
  `max_output_bytes=None` in the library), and every decoded chunk is
  additionally capped at 128 KiB *during* LZ77 expansion (legit chunks are
  exactly one 64 KiB input chunk), so a malicious chunk can't force a huge
  in-memory allocation before its checksum is verified.
- **Clean `MemoryError` handling** — a corrupt archive that would exhaust
  memory fails with a clear error in CLI and GUI instead of killing the
  worker thread with a raw traceback.
- **Partial outputs quarantined** — a cancelled or failed CLI job renames the
  half-written file to `.partial` so it can never be mistaken for a good
  result (the GUI quarantines failed, cancelled, and out-of-memory jobs).

### Command line (`vzip`)
- `vzip compress path/to/file` → `path/to/file.vzip`
- `vzip decompress path/to/file.vzip` → `path/to/file.restored`
- Live tqdm progress bars with byte counts; Ctrl-C cancels cleanly (exit
  130) with the partial output quarantined.
- `--max-output-gb`, `--no-output-limit`, `--force` — the same safety
  controls as the library.

### Desktop GUI
- **Drag & drop** files or whole folders straight into the queue (or use
  *Add files*).
- **Batch queue** — compress or decompress dozens of files in one run, with
  *Remove selected* / *Clear queue* management.
- **Live progress** — per-file progress bars with byte counts in the queue
  table, plus a status bar for overall state.
- **Stat cards** — files done, original size, output size, and space saved
  for the whole batch.
- **Color-coded activity log** — every file's outcome, HTML-escaped so log
  content can't inject markup.
- **Mode switch** — Compress / Decompress with one click.
- **Custom output folder** — with browse and reset-to-default buttons.
- **Overwrite protection** — an explicit checkbox; existing outputs are
  skipped unless you opt in.
- **Cancel** — stops the run and quarantines partials.
- Runs jobs on a worker `QThread`, so the interface stays responsive during
  long batches.

### Python library
```python
from vectorzip import compress_file, decompress_file

out = compress_file('input.txt')              # -> 'input.txt.vzip'
restored = decompress_file(out)               # -> 'input.txt.restored'
```
Both accept a `progress` callback `(bytes_done, bytes_total)` invoked after
each chunk, and `overwrite=False` by default. `decompress_file` also accepts
`max_output_bytes` (default 8 GiB) for the decompression-bomb cap. The
low-level `lz77_compress` / `lz77_decompress` / `huffman_encode` /
`huffman_decode` building blocks are exported too.

### Releases and packaging
- Pushing a `v*` tag builds `VectorZip.exe` (Windows, windowed) and the
  Linux `VectorZip` binary automatically via GitHub Actions.
- Every release ships **`SHA256SUMS-windows.txt` / `SHA256SUMS-linux.txt`**
  and signed **build-provenance attestations** — verify before you run.
- `pip install .` installs the `vectorzip` package plus the `vzip` CLI and
  `vectorzip-gui` launcher.
- A PyPI release (`vectorzip-py`) is **planned, not yet published** — the
  release-triggered publish workflow exists, but the package is not on PyPI
  today.

## Who it's for

- **Everyday users** who want drag-and-drop lossless archiving with loud,
  verifiable integrity — the GUI needs no technical background.
- **Scripters and sysadmins** who need a dependable `vzip` one-liner with
  sane safety defaults in pipelines.
- **Python developers** who want an embeddable, auditable, pure-Python
  compressor with progress callbacks.

## Install from source

PyPI is planned but not published yet — install from source for now:

```bash
git clone https://github.com/TheRealJesusTheHacker/VectorZip
cd VectorZip
pip install .
```

This installs the `vectorzip` package, the `vzip` command-line tool, and the
`vectorzip-gui` desktop app launcher.

## Downloads

No Python required — grab the standalone app:

| Platform | Download |
|----------|----------|
| Windows | [VectorZip.exe](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.2.3/VectorZip.exe) |
| Linux | [VectorZip](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.2.3/VectorZip) |

(Screenshots: none published — the GUI ships in the binaries above and in
`gui/`.)

### Verify integrity

Every release publishes checksums — verify before running anything:

```powershell
# Windows
Get-FileHash VectorZip.exe -Algorithm SHA256
```

```bash
# Linux
sha256sum -c SHA256SUMS-linux.txt
```

Checksums: [SHA256SUMS-windows.txt](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.2.3/SHA256SUMS-windows.txt) · [SHA256SUMS-linux.txt](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.2.3/SHA256SUMS-linux.txt)

## Usage

**Desktop app:**

```bash
vectorzip-gui
# or: python gui_launcher.py
```

**Command line:**

```bash
vzip compress path/to/file          # -> path/to/file.vzip
vzip decompress path/to/file.vzip   # -> path/to/file.restored

# Safety controls
vzip decompress big.vzip --max-output-gb 2     # cap decompressed output
vzip decompress big.vzip --no-output-limit     # disable the cap
vzip compress file --force                     # allow overwriting output
```

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
```

## File format

`.vzip` files (v3, since 1.2.3) start with a `VZP3` magic; each 64 KiB chunk
carries a CRC32, a flags byte, and either the Huffman-packed LZ77 token
stream or — when compression wouldn't shrink it — the raw chunk bytes.
The stream ends with an end-of-stream marker chunk, so a truncated file
can never silently decompress to partial data.
Files written by 1.2.0/1.2.1 (v2, `VZP2` magic) and 1.0.0/1.1.0
(v1, no magic) still decompress.
See [docs/compression.md](docs/compression.md).

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q        # 34/34 passing
```

- **Unit tests** (`tests/test_compression.py`) — 34 tests covering round
  trips at every size from empty to multi-chunk, chunk/window boundary
  conditions, byte-flip and truncation corruption, legacy v1/v2 archives,
  overwrite-refusal and symlink safety, output caps, and cancel behavior.
- **Decompressor fuzzer** (`tests/fuzz_decompress.py`) — stdlib-only,
  byte-flips and truncates real archives; runs 5 minutes in CI on every
  push touching `src/` or `tests/`, plus weekly on a schedule.
- **CI** runs byte-compilation on Linux and Windows, the full pytest suite,
  a CLI compress→decompress→byte-compare round trip, and ruff + black
  checks on every push and PR.

## Building the standalone app

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm vectorzip.spec   # -> dist/VectorZip(.exe)
```

Tagged releases (`v*`) are built automatically by GitHub Actions for Windows
and Linux, with SHA256 checksums and signed build-provenance attestations
attached to the release. Decompressor fuzzing runs in CI on every push.

## Security

Found a vulnerability? Please report it privately — see
[SECURITY.md](SECURITY.md). Do not open a public issue for a security
problem.

## Contact

Business inquiries: **Sentinelsafeguard@outlook.com**

## License

Mozilla Public License 2.0 — see [LICENSE](LICENSE).

## Changelog

All notable changes are documented in [CHANGELOG.md](CHANGELOG.md),
following the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
format.

## Donations

If this tool earned its keep, BTC is welcome:

```
bc1qvydns2fmyjzj55wzxq7ta28nxdhcmu9l9m6yg0
```
