#!/usr/bin/env python3
"""Assemble the VectorZip portable edition zip.

Usage:
    python packaging/portable/build-portable.py --binary dist/VectorZip.exe \
        --output dist/VectorZipPortable.zip
    python packaging/portable/build-portable.py --binary dist/VectorZip \
        --output dist/VectorZipPortable-linux.zip

The zip contains exactly two entries at its root:
  * the PyInstaller standalone binary (under its own file name), and
  * README-PORTABLE.txt (from this directory).

This is the only portable-assembly path: the release workflow
(.github/workflows/release.yml) calls this script for both the
Windows and the Linux job, so what is tested locally is what CI runs.
Standard library only; works on Windows and Linux.
"""

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

README_NAME = "README-PORTABLE.txt"


def build(binary: Path, output: Path) -> str:
    if not binary.is_file():
        raise SystemExit(f"error: binary not found: {binary}")
    readme = Path(__file__).resolve().parent / README_NAME
    if not readme.is_file():
        raise SystemExit(f"error: portable readme not found: {readme}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Preserve the executable bit for the Linux binary; harmless
        # for the Windows .exe.
        info = zipfile.ZipInfo(binary.name)
        info.external_attr = 0o755 << 16
        zf.writestr(info, binary.read_bytes())
        zf.write(readme, README_NAME)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"built {output} ({output.stat().st_size} bytes)")
    print(f"sha256 {digest}  {output.name}")
    return digest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the VectorZip portable zip.")
    parser.add_argument("--binary", required=True, help="Path to the standalone binary")
    parser.add_argument("--output", required=True, help="Path of the zip to create")
    args = parser.parse_args(argv)
    build(Path(args.binary), Path(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
