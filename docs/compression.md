# File Compression Algorithm Documentation

## Overview
This tool implements a hybrid compression algorithm combining LZ77 and Huffman encoding for maximum efficiency.

## Algorithm Components

### 1. LZ77 Compression
- Sliding window dictionary matching (4 KB window)
- Greedy 3-byte hash-chain matching, match lengths 3..255
- Output: fixed 4-byte tokens `(distance, length, next_byte)` in big-endian `>HBB` layout
- A distance of 0 marks a literal token (the byte itself)

### 2. Huffman Encoding
- Frequency-based variable-length encoding over the LZ77 token stream
- Creates optimal prefix codes
- Output: packed binary sequence plus the code table

## Implementation Details

### Compression Process
1. Read input file (raw bytes) in 64 KiB chunks
2. Apply LZ77 compression (dictionary matching) per chunk
3. Apply Huffman encoding (frequency optimization) per chunk
4. Write chunk: CRC32 of the original chunk, the serialized Huffman table,
   then the Huffman-packed data

### Decompression Process
1. Read chunk header (CRC32, table size, padding)
2. Deserialize the Huffman table
3. Huffman-decode -> LZ77-decode -> original chunk bytes
4. Verify CRC32 per chunk; raise `ValueError` on any mismatch or truncation

### Container Format (all integers big-endian)
```
header:      crc32 u32 | table_len u16 | pad_bits u8
table:       table_len bytes: per entry symbol u8 | code_bits u8 |
             ceil(code_bits/8) bytes of code, MSB-first
data header: encoded_len u32
data:        encoded_len bytes
```

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
