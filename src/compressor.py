"""Chunked file compression: LZ77 -> Huffman -> .vzip container.

Chunk layout on disk (all big-endian):
    header:      crc32 u32 | table_len u16 | pad_bits u8      ('>IHB')
    table:       table_len bytes (see huffman.serialize_table)
    data header: encoded_len u32                              ('>I')
    data:        encoded_len bytes of Huffman-packed LZ77 tokens

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
_HEADER = struct.Struct('>IHB')   # crc32, table_len, pad_bits
_DATA_HEADER = struct.Struct('>I')  # encoded_len


def compress_file(input_path, progress=None):
    """Compress ``input_path`` to ``input_path + '.vzip'``.

    ``progress`` is an optional callback ``(bytes_done, bytes_total)``
    invoked after each chunk.
    """
    output_path = input_path + '.vzip'
    total = os.path.getsize(input_path)
    done = 0
    with open(input_path, 'rb') as fin, open(output_path, 'wb') as fout:
        while True:
            chunk = fin.read(_CHUNK)
            if not chunk:
                break
            chk = zlib.crc32(chunk) & 0xFFFFFFFF
            lz_data = lz77_compress(chunk)
            encoded, pad, table = huffman_encode(lz_data)
            table_blob = serialize_table(table)
            fout.write(_HEADER.pack(chk, len(table_blob), pad))
            fout.write(table_blob)
            fout.write(_DATA_HEADER.pack(len(encoded)))
            fout.write(encoded)
            done += len(chunk)
            if progress is not None:
                progress(done, total)
    if progress is not None:
        progress(total, total)
    return output_path


def decompress_file(input_path, progress=None):
    """Decompress a ``.vzip`` file; returns the restored file path.

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
    done = 0
    with open(input_path, 'rb') as fin, open(output_path, 'wb') as fout:
        while True:
            header = fin.read(_HEADER.size)
            if not header:
                break
            if len(header) < _HEADER.size:
                raise ValueError('corrupt file: truncated chunk header')
            chk, table_len, pad = _HEADER.unpack(header)
            table_blob = fin.read(table_len)
            if len(table_blob) < table_len:
                raise ValueError('corrupt file: truncated Huffman table')
            table = deserialize_table(table_blob)
            raw_len = fin.read(_DATA_HEADER.size)
            if len(raw_len) < _DATA_HEADER.size:
                raise ValueError('corrupt file: truncated data header')
            (encoded_len,) = _DATA_HEADER.unpack(raw_len)
            encoded = fin.read(encoded_len)
            if len(encoded) < encoded_len:
                raise ValueError('corrupt file: truncated data')
            original = lz77_decompress(huffman_decode(encoded, pad, table))
            if (zlib.crc32(original) & 0xFFFFFFFF) != chk:
                raise ValueError('corrupt file: checksum mismatch')
            fout.write(original)
            done += _HEADER.size + table_len + _DATA_HEADER.size + encoded_len
            if progress is not None:
                progress(min(done, total), total)
    if progress is not None:
        progress(total, total)
    return output_path
