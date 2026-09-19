# VectorZip

**VectorZip** is a lossless file compression library that combines **LZ77** sliding window dictionary matching with **Huffman** entropy coding.

## Features
- **Hybrid Compression:** Leverages LZ77 for redundancy elimination and Huffman for optimal bit-packing.
- **Lossless:** Verified by round-trip tests — decompressing a `.vzip` file returns byte-identical data. Every 64 KiB chunk carries a CRC32 that is checked on decompression.
- **Memory-Efficient:** Chunked processing keeps memory usage flat regardless of file size.
- **Portable:** Pure Python 3 (3.8+), no compiled extensions required.
- **Developer-Friendly:** Clean API designed for both CLI and programmatic integration.

## Installation

```bash
git clone https://github.com/TheRealJesusTheHacker/VectorZip
cd VectorZip
pip install .
```

This installs the `vectorzip` package and the `vzip` command-line tool.

## Usage

```bash
vzip compress path/to/file        # -> path/to/file.vzip
vzip decompress path/to/file.vzip # -> path/to/file.restored
```

```python
from vectorzip import compress_file, decompress_file

out = compress_file('input.txt')    # -> 'input.txt.vzip'
restored = decompress_file(out)     # -> 'input.txt.restored'
```

## File format

Each 64 KiB chunk is stored as (all integers big-endian): CRC32 of the
original chunk, the serialized Huffman code table, then the
Huffman-packed LZ77 token stream. See [docs/compression.md](docs/compression.md).

## Running tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
```
