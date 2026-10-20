"""Regression tests: huffman_decode must reject out-of-range padding
with ValueError (the format's corrupt-input contract).

Padding is the unused-bit count of the final encoded byte, so the
encoder only ever produces 0..7. The container reader validates the
value before calling, but huffman_decode is exported public API, and
before this fix an out-of-range value escaped the contract twice
over: a negative padding raised IndexError from the bit walk, and an
oversized padding silently returned truncated (or empty) output that
looked like a successful decode.
"""

import unittest

from src.huffman import huffman_decode, huffman_encode


class TestHuffmanDecodePadding(unittest.TestCase):
    def setUp(self):
        self.encoded, self.pad, self.table = huffman_encode(b'hello hello hello')
        # Sanity: the fixture really does round-trip untouched.
        self.assertEqual(huffman_decode(self.encoded, self.pad, self.table), b'hello hello hello')

    def test_negative_padding_raises_value_error(self):
        with self.assertRaises(ValueError):
            huffman_decode(self.encoded, -1, self.table)

    def test_oversized_padding_raises_value_error(self):
        for bad in (8, 99):
            with self.assertRaises(ValueError):
                huffman_decode(self.encoded, bad, self.table)

    def test_boundary_padding_values_still_decode(self):
        # 0 and 7 are legitimate encoder outputs on other payloads;
        # they must not raise here (the decoded bytes differ from the
        # original only because the fixture's true pad is neither).
        for ok in (0, 7):
            self.assertIsInstance(huffman_decode(self.encoded, ok, self.table), bytes)


if __name__ == '__main__':
    unittest.main()
