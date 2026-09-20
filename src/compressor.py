"""Chunked file compression: LZ77 -> Huffman -> .vzip container.

Format v2 (written by VectorZip >= 1.2.0):
    magic:       b'VZP2'
    per chunk:
      header:      crc32 u32 | table_len u16 | pad_bits u8 | flags u8  ('>IHBB')
      flags bit 0 (RAW): chunk stored literally, no LZ77/Huffman.
      if RAW:
        data header: raw_len u32                              ('>I')
        data:        raw_len bytes (the original chunk bytes)
      else:
        table:       table_len bytes (see huffman.serialize_table)
        data header: encoded_len u32                          ('>I')
        data:        encoded_len bytes of Huffman-packed LZ77 tokens

Format v1 (VectorZip 1.0.0/1.1.0, no magic, '>IHB' chunk header) is still
fully readable: the decompressor detects the magic and picks the parser.

A chunk is stored RAW whenever compressing it would not shrink it, so
incompressible data (random bytes, already-compressed files) passes through
at I/O speed instead of being expanded by the entropy coder.

Decompression verifies the CRC32 of every chunk and raises ValueError
on any truncation or mismatch.
"""
import os
import struct
import zlib

from .lz77 import lz77_compress, lz77_decompress
from .huffman import (huffman_encode, huffman_decode,
                      serialize_table, deserialize_table)

_CHUNK = 65536
_MAGIC = b'VZP2'
_HEADER_V2 = struct.Struct('>IHBB')  # crc32, table_len, pad_bits, flags
_HEADER_V1 = struct.Struct('>IHB')   # crc32, table_len, pad_bits (no flags)
_DATA_HEADER = struct.Struct('>I')   # encoded_len / raw_len
_FLAG_RAW = 0x01
# Sampling heuristic: slices taken from the start/middle/end of a chunk.
# Random (incompressible) data shows ~all 256 byte values in a few KiB;
# text/code/binary show far fewer. Above this many distinct values we
# skip LZ77+Huffman entirely and store the chunk raw.
_SAMPLE_SLICES = 3
_SAMPLE_EACH = 2048
_SAMPLE_DISTINCT_LIMIT = 224


def _looks_incompressible(chunk):
    """Cheap pre-check: does this chunk look like random data?"""
    n = len(chunk)
    if n < _SAMPLE_EACH:
        return len(set(chunk)) > min(_SAMPLE_DISTINCT_LIMIT, n // 2)
    step = (n - _SAMPLE_EACH) // (_SAMPLE_SLICES - 1) if _SAMPLE_SLICES > 1 else 0
    seen = set()
    for s in range(_SAMPLE_SLICES):
        seen.update(chunk[s * step:s * step + _SAMPLE_EACH])
        if len(seen) > _SAMPLE_DISTINCT_LIMIT:
            return True
    return False


def _write_raw(fout, chunk, chk):
    fout.write(_HEADER_V2.pack(chk, 0, 0, _FLAG_RAW))
    fout.write(_DATA_HEADER.pack(len(chunk)))
    fout.write(chunk)


def _write_chunk_v2(fout, chunk):
    """Compress one chunk with the v2 workhorse policy; write it to fout."""
    chk = zlib.crc32(chunk) & 0xFFFFFFFF
    if _looks_incompressible(chunk):
        # Random data: don't even try LZ77, store raw at I/O speed.
        _write_raw(fout, chunk, chk)
        return
    lz_data = lz77_compress(chunk)
    if len(lz_data) >= len(chunk):
        # LZ77 couldn't shrink it: skip Huffman entirely, store raw.
        _write_raw(fout, chunk, chk)
        return
    encoded, pad, table = huffman_encode(lz_data)
    table_blob = serialize_table(table)
    if _HEADER_V2.size + len(table_blob) + _DATA_HEADER.size + len(encoded) >= len(chunk):
        # Table + bitstream overhead ate the savings: store raw.
        _write_raw(fout, chunk, chk)
        return
    fout.write(_HEADER_V2.pack(chk, len(table_blob), pad, 0))
    fout.write(table_blob)
    fout.write(_DATA_HEADER.pack(len(encoded)))
    fout.write(encoded)


def _read_exact(fin, n, what):
    data = fin.read(n)
    if len(data) < n:
        raise ValueError(f'corrupt file: truncated {what}')
    return data


def _decompress_chunks_v2(fin, fout, progress, total):
    done = 0
    while True:
        header = fin.read(_HEADER_V2.size)
        if not header:
            break
        if len(header) < _HEADER_V2.size:
            raise ValueError('corrupt file: truncated chunk header')
        chk, table_len, pad, flags = _HEADER_V2.unpack(header)
        if flags & _FLAG_RAW:
            raw_len = _DATA_HEADER.unpack(_read_exact(fin, _DATA_HEADER.size, 'data header'))[0]
            original = _read_exact(fin, raw_len, 'raw chunk data')
        else:
            table_blob = _read_exact(fin, table_len, 'Huffman table')
            table = deserialize_table(table_blob)
            encoded_len = _DATA_HEADER.unpack(_read_exact(fin, _DATA_HEADER.size, 'data header'))[0]
            encoded = _read_exact(fin, encoded_len, 'chunk data')
            original = lz77_decompress(huffman_decode(encoded, pad, table))
        if (zlib.crc32(original) & 0xFFFFFFFF) != chk:
            raise ValueError('corrupt file: checksum mismatch')
        fout.write(original)
        done += len(original)
        if progress is not None:
            progress(done, total)


def _decompress_chunks_v1(fin, fout, progress, total):
    done = 0
    while True:
        header = fin.read(_HEADER_V1.size)
        if not header:
            break
        if len(header) < _HEADER_V1.size:
            raise ValueError('corrupt file: truncated chunk header')
        chk, table_len, pad = _HEADER_V1.unpack(header)
        table_blob = _read_exact(fin, table_len, 'Huffman table')
        table = deserialize_table(table_blob)
        encoded_len = _DATA_HEADER.unpack(_read_exact(fin, _DATA_HEADER.size, 'data header'))[0]
        encoded = _read_exact(fin, encoded_len, 'chunk data')
        original = lz77_decompress(huffman_decode(encoded, pad, table))
        if (zlib.crc32(original) & 0xFFFFFFFF) != chk:
            raise ValueError('corrupt file: checksum mismatch')
        fout.write(original)
        done += len(original)
        if progress is not None:
            progress(done, total)


def compress_file(input_path, progress=None):
    """Compress ``input_path`` to ``input_path + '.vzip'`` (format v2).

    ``progress`` is an optional callback ``(bytes_done, bytes_total)``
    invoked after each chunk.
    """
    output_path = input_path + '.vzip'
    total = os.path.getsize(input_path)
    done = 0
    with open(input_path, 'rb') as fin, open(output_path, 'wb') as fout:
        fout.write(_MAGIC)
        while True:
            chunk = fin.read(_CHUNK)
            if not chunk:
                break
            _write_chunk_v2(fout, chunk)
            done += len(chunk)
            if progress is not None:
                progress(done, total)
    if progress is not None:
        progress(total, total)
    return output_path


def decompress_file(input_path, progress=None):
    """Decompress a ``.vzip`` file; returns the restored file path.

    Reads both format v2 (magic ``VZP2``) and legacy format v1 files.
    The output never overwrites the input: ``'a.vzip'`` -> ``'a.restored'``,
    anything else -> ``input + '.restored'``.
    """
    if input_path.endswith('.vzip'):
        output_path = input_path[:-len('.vzip')] + '.restored'
    else:
        output_path = input_path + '.restored'
    if os.path.abspath(output_path) == os.path.abspath(input_path):
        raise ValueError('refusing to overwrite the input file')
    total = os.path.getsize(input_path)
    with open(input_path, 'rb') as fin, open(output_path, 'wb') as fout:
        magic = fin.read(len(_MAGIC))
        if magic == _MAGIC:
            _decompress_chunks_v2(fin, fout, progress, total)
        elif not magic:
            # empty input -> empty output
            pass
        elif len(magic) < len(_MAGIC):
            raise ValueError('corrupt file: truncated chunk header')
        else:
            # Legacy v1 file: rewind and parse with the old header layout.
            fin.seek(0)
            _decompress_chunks_v1(fin, fout, progress, total)
    if progress is not None:
        progress(total, total)
    return output_path
