# File Compression Algorithm Documentation

## Overview
This tool implements a hybrid compression algorithm combining LZ77 and Huffman encoding for maximum efficiency.

## Algorithm Components

### 1. LZ77 Compression
- Sliding window dictionary matching (32 KiB window)
- Greedy 3-byte hash matching, match lengths 3..255
- Output: fixed 4-byte tokens `(distance, length, next_byte)` in big-endian `>HBB` layout
- A distance of 0 marks a literal token (the byte itself)

### 2. Huffman Encoding
- Frequency-based variable-length encoding over the LZ77 token stream
- Creates optimal prefix codes
- Output: packed binary sequence plus the code table

## Implementation Details

### The workhorse policy (v1.2.0+)
Not every chunk is worth compressing. Before the entropy coder runs:
1. **Sampling heuristic** — a few slices of the chunk are checked for byte
   diversity. ~all 256 values in a few KiB means random data: store raw.
2. **LZ77 trial** — if the token stream isn't smaller than the chunk, store raw.
3. **Huffman trial** — if table + bitstream overhead eats the savings, store raw.

Raw chunks skip LZ77+Huffman entirely, so incompressible data moves at I/O
speed and a `.vzip` file never exceeds its input size.

### Compression Process
1. Read input file (raw bytes) in 64 KiB chunks
2. Apply the workhorse policy per chunk (raw-store or LZ77 -> Huffman)
3. Write chunk: CRC32 of the original chunk, flags, then either the
   serialized Huffman table + Huffman-packed data, or the raw chunk bytes

### Decompression Process
1. Read chunk header (CRC32, table size, padding)
2. Deserialize the Huffman table
3. Huffman-decode -> LZ77-decode -> original chunk bytes
4. Verify CRC32 per chunk; raise `ValueError` on any mismatch or truncation

### Container Format v3 (all integers big-endian; VectorZip >= 1.2.2)
```
magic:       b'VZP3'
per chunk:
  header:      crc32 u32 | table_len u16 | pad_bits u8 | flags u8
  flags bit 0 (RAW): chunk stored literally
  flags bit 7 (END): end-of-stream marker; carries no table and no data.
                     The decompressor requires it: reaching EOF without it
                     raises ValueError instead of returning partial data.
  if RAW:
    data header: raw_len u32
    data:        raw_len bytes (original chunk bytes)
  else:
    table:       table_len bytes: per entry symbol u8 | code_bits u8 |
                 ceil(code_bits/8) bytes of code, MSB-first
    data header: encoded_len u32
    data:        encoded_len bytes of Huffman-packed LZ77 tokens
```

### Container Format v2 (VectorZip 1.2.0/1.2.1 — still readable)
Same chunk layout as v3 but with `b'VZP2'` magic and no END marker.
Note: a v2 file truncated exactly at a chunk boundary decompresses to
partial data without an error — v3 closes that hole.

### Container Format v1 (VectorZip 1.0.0/1.1.0 — still readable)
Same as v2 but with no magic and no flags byte: the chunk header is
`crc32 u32 | table_len u16 | pad_bits u8`. The decompressor detects the
`VZP3`/`VZP2` magic and selects the parser automatically.

## Usage Examples

### Basic Compression
```python
from src.compressor import compress_file, decompress_file

out = compress_file('input.txt')      # -> 'input.txt.vzip'
restored = decompress_file(out)       # -> 'input.txt.restored'
```

### Command Line
```bash
python main.py compress path/to/file
python main.py decompress path/to/file.vzip
```
