VectorZip - Portable Edition
============================

This zip is the portable edition of the VectorZip desktop app.
Nothing is installed: there is no installer, no setup step, and no
Python requirement. The app inside is the same PyInstaller-built
standalone binary published on the GitHub Releases page.

Run it
------
Windows:  double-click VectorZip.exe
Linux:    make the file executable if needed (chmod +x VectorZip),
          then run ./VectorZip

Use it from anywhere
--------------------
Unzip this file into any folder you control - a folder on your PC
or a USB stick for field work - and run the app from there. To
remove VectorZip, delete the unzipped files; nothing else was
added to your system by the portable edition.

What it does
------------
VectorZip compresses and decompresses files losslessly into the
.vzip format (LZ77 + Huffman, per-chunk CRC32 verified on
decompression). Compressed and restored files are written next to
the files you choose in the app - the portable edition writes no
output anywhere else on its own.

Verify your download
--------------------
Every release also publishes SHA256SUMS-windows.txt (Windows) and
SHA256SUMS-linux.txt (Linux) covering both the standalone binary
and this portable zip. Compare the hash of the file you downloaded
before running it:

  Windows (PowerShell):  Get-FileHash VectorZipPortable.zip -Algorithm SHA256
  Linux:                  sha256sum -c SHA256SUMS-linux.txt

Notes
-----
- The portable edition is the desktop (GUI) app. The command-line
  tool (vzip) is available from a source install - see the Install
  section of the README in the VectorZip repository.
- License: Mozilla Public License 2.0 - see LICENSE in the
  VectorZip repository.
