# VectorZip

**VectorZip** is a *completely lossless* file compression tool that combines
**LZ77** sliding-window dictionary matching with **Huffman** entropy coding.
Compress anything — documents, backups, datasets — and get back byte-identical
data, every time. Corruption is never silent: every 64 KiB chunk carries a
CRC32 that is verified on decompression.

![Version](https://img.shields.io/badge/version-1.1.0-blue)
![License](https://img.shields.io/badge/license-MPL--2.0-green)
![Tests](https://img.shields.io/badge/tests-23%2F23_passing-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)

## Downloads

No Python required — grab the standalone app:

| Platform | Download |
|----------|----------|
| Windows | [VectorZip.exe](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.1.0/VectorZip.exe) |
| Linux | [VectorZip](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.1.0/VectorZip) |

Verify integrity with the published checksums:

```powershell
# Windows
Get-FileHash VectorZip.exe -Algorithm SHA256
```

```bash
# Linux
sha256sum -c SHA256SUMS-linux.txt
```

Checksums: [SHA256SUMS-windows.txt](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.1.0/SHA256SUMS-windows.txt) · [SHA256SUMS-linux.txt](https://github.com/TheRealJesusTheHacker/VectorZip/releases/download/v1.1.0/SHA256SUMS-linux.txt)

## The desktop app

Double-click and go. The VectorZip GUI gives you:

- **Drag & drop** — drop files or whole folders straight into the queue
- **Batch processing** — compress or decompress dozens of files in one run
- **Live progress** — per-file progress bar with byte counts, plus overall status
- **Real statistics** — original size, output size, and space saved per file
  and for the whole batch
- **Safe by default** — outputs never overwrite your originals; existing
  outputs are skipped unless you explicitly enable overwrite
- **Custom output folder** — keep your `.vzip` archives wherever you like
- **Activity log** — a color-coded console showing exactly what happened,
  file by file

Switch between **Compress** and **Decompress** modes with one click. Dropping
`.vzip` files in Decompress mode restores them to byte-identical originals.

## Features

- **Completely lossless:** decompressing a `.vzip` file returns byte-identical
  data — verified by round-trip tests, never "close enough."
- **Workhorse fast:** ~10 MB/s on everyday files; incompressible data
  (random bytes, zips, videos) passes through at ~800 MB/s and never grows
  the file — stored raw instead of force-compressed.
- **Corruption-proof:** every 64 KiB chunk carries a CRC32 checked on
  decompression; truncated or damaged archives fail loudly instead of
  silently returning bad data.
- **Memory-efficient:** chunked processing keeps memory usage flat regardless
  of file size — compress multi-gigabyte files on modest hardware.
- **Portable:** pure Python 3 (3.8+), no compiled extensions required.
- **Developer-friendly:** clean API for both CLI and programmatic use.

## Install from source

```bash
git clone https://github.com/TheRealJesusTheHacker/VectorZip
cd VectorZip
pip install .
```

This installs the `vectorzip` package, the `vzip` command-line tool, and the
`vectorzip-gui` desktop app launcher.

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
```

**Python API:**

```python
from vectorzip import compress_file, decompress_file

out = compress_file('input.txt')    # -> 'input.txt.vzip'
restored = decompress_file(out)     # -> 'input.txt.restored'
```

## File format

`.vzip` files (v3, since 1.2.2) start with a `VZP3` magic; each 64 KiB chunk
carries a CRC32, a flags byte, and either the Huffman-packed LZ77 token
stream or — when compression wouldn't shrink it — the raw chunk bytes.
The stream ends with an end-of-stream marker chunk, so a truncated file
can never silently decompress to partial data.
Files written by 1.2.0/1.2.1 (v2, `VZP2` magic) and 1.0.0/1.1.0
(v1, no magic) still decompress.
See [docs/compression.md](docs/compression.md).

## Running tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## Building the standalone app

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm vectorzip.spec   # -> dist/VectorZip(.exe)
```

Tagged releases (`v*`) are built automatically by GitHub Actions for Windows
and Linux, with SHA256 checksums attached to the release.

## License

Mozilla Public License 2.0 — see [LICENSE](LICENSE).
