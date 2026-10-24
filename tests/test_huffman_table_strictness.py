"""deserialize_table must reject table entries the encoder never writes.

The Huffman table is parsed straight from the (possibly hostile) input
file before any checksum is verified. Entries with a zero-length code,
a code past the depth any real encoder output can reach, a code value
that overflows its declared bit length, or a duplicated symbol are
hand-crafted by definition — serialize_table writes dict entries with
1 <= bitlen and value < 2**bitlen — so they raise ValueError instead of
being silently reinterpreted into a different decode tree.

Fleet Sweep #5 added the code-space half of that rule: the encoder's
tables are always prefix-free, so a code that duplicates another
entry's code, or that is a prefix of (or has as a prefix) another
entry's code, is hand-crafted too. Before the fix such a table was
accepted and silently reinterpreted — a duplicated code decoded to
whichever symbol was inserted last, and a prefix code shadowed the
longer code entirely. huffman_decode applies the same refusal to
tables handed to it directly, matching its padding contract.
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

    def test_duplicate_code_rejected(self):
        # Two symbols, one code ('0'): individually well-formed entries
        # whose code assignment the encoder could never produce.
        blob = _entry(65, 1, b'\x00') + _entry(66, 1, b'\x00')
        with self.assertRaises(ValueError):
            deserialize_table(blob)

    def test_prefix_code_rejected_short_first(self):
        # '0' for A, then '01' for B: B's code has A's as a prefix.
        blob = _entry(65, 1, b'\x00') + _entry(66, 2, b'\x01')
        with self.assertRaises(ValueError):
            deserialize_table(blob)

    def test_prefix_code_rejected_long_first(self):
        # Same conflict, opposite entry order: '01' first, then '0'.
        blob = _entry(66, 2, b'\x01') + _entry(65, 1, b'\x00')
        with self.assertRaises(ValueError):
            deserialize_table(blob)

    def test_decode_rejects_conflicting_table_directly(self):
        # huffman_decode is public API (the padding tests' precedent):
        # a conflicting table handed to it directly raises ValueError,
        # never a silently shadowed decode.
        from src.huffman import huffman_decode

        for table in ({65: '0', 66: '0'}, {65: '0', 66: '01'}, {66: '01', 65: '0'}):
            with self.assertRaises(ValueError, msg=repr(table)):
                huffman_decode(b'\x00', 7, table)

    def test_crafted_archive_with_duplicate_code_table_rejected(self):
        # End-to-end: a v3 archive whose chunk table assigns one code
        # to two symbols must fail with ValueError, not decode.
        table_blob = _entry(65, 1, b'\x00') + _entry(66, 1, b'\x00')
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
