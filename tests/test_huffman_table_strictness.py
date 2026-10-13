"""deserialize_table must reject table entries the encoder never writes.

The Huffman table is parsed straight from the (possibly hostile) input
file before any checksum is verified. Entries with a zero-length code,
a code past the depth any real encoder output can reach, a code value
that overflows its declared bit length, or a duplicated symbol are
hand-crafted by definition — serialize_table writes dict entries with
1 <= bitlen and value < 2**bitlen — so they raise ValueError instead of
being silently reinterpreted into a different decode tree.
"""

import os
import struct
import tempfile
import unittest
import zlib

from src.compressor import _DATA_HEADER, _FLAG_END, _HEADER_V2, decompress_file
from src.huffman import deserialize_table, serialize_table


def _entry(symbol, bitlen, code_bytes):
    return struct.pack('>BB', symbol, bitlen) + code_bytes


class TestDeserializeTableStrictness(unittest.TestCase):
    def test_roundtrip_normal_table(self):
        table = {65: '0', 66: '10', 67: '110', 68: '111'}
        self.assertEqual(deserialize_table(serialize_table(table)), table)

    def test_zero_length_code_rejected(self):
        with self.assertRaises(ValueError):
            deserialize_table(_entry(65, 0, b''))

    def test_overlong_code_rejected(self):
        # 65 bits: one past the cap, and far past the ~26-bit deepest
        # code a real 64 KiB chunk can produce.
        with self.assertRaises(ValueError):
            deserialize_table(_entry(65, 65, b'\x00' * 9))
        with self.assertRaises(ValueError):
            deserialize_table(_entry(65, 255, b'\x00' * 32))

    def test_max_length_code_accepted(self):
        # Boundary: a 64-bit code is still a legal table entry.
        blob = _entry(65, 64, (1).to_bytes(8, 'big'))
        self.assertEqual(deserialize_table(blob), {65: bin(1)[2:].zfill(64)})

    def test_code_value_overflow_rejected(self):
        # Declared as a 1-bit code, but the stored byte carries an
        # 8-bit value (0x80) — the padding bits are not part of the code.
        with self.assertRaises(ValueError):
            deserialize_table(_entry(65, 1, b'\x80'))

    def test_duplicate_symbol_rejected(self):
        # Both entries are individually well-formed (values fit their
        # declared lengths); only the repeated symbol is wrong.
        blob = _entry(65, 1, b'\x00') + _entry(65, 1, b'\x01')
        with self.assertRaises(ValueError):
            deserialize_table(blob)

    def test_truncated_entry_still_rejected(self):
        with self.assertRaises(ValueError):
            deserialize_table(b'\x41')

    def test_crafted_archive_with_bad_table_rejected(self):
        # End-to-end: a v3 archive whose chunk table declares a
        # zero-length code must fail with ValueError, not decode.
        table_blob = _entry(65, 0, b'')
        chk = zlib.crc32(b'x') & 0xFFFFFFFF
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'evil.vzip')
            with open(path, 'wb') as f:
                f.write(b'VZP3')
                f.write(_HEADER_V2.pack(chk, len(table_blob), 0, 0))
                f.write(table_blob)
                f.write(_DATA_HEADER.pack(1))
                f.write(b'\x00')
                f.write(_HEADER_V2.pack(0, 0, 0, _FLAG_END))
            with self.assertRaises(ValueError):
                decompress_file(path)


if __name__ == '__main__':
    unittest.main()
