import os
import tempfile
import unittest

from src.compressor import compress_file, decompress_file
from src.lz77 import lz77_compress, lz77_decompress
from src.huffman import huffman_encode, huffman_decode


class TestFileRoundTrip(unittest.TestCase):
    """compress_file -> decompress_file must be byte-identical."""

    def _roundtrip(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'input.bin')
            with open(src, 'wb') as f:
                f.write(data)
            compressed = compress_file(src)
            self.assertTrue(os.path.exists(compressed))
            restored = decompress_file(compressed)
            with open(restored, 'rb') as f:
                out = f.read()
            self.assertEqual(out, data)

    def test_empty(self):
        self._roundtrip(b'')

    def test_single_byte(self):
        self._roundtrip(b'A')

    def test_single_symbol_repeated(self):
        self._roundtrip(b'\x00' * 10000)

    def test_short_text(self):
        self._roundtrip(b'hello world')

    def test_all_byte_values(self):
        self._roundtrip(bytes(range(256)))

    def test_random_1k(self):
        self._roundtrip(os.urandom(1024))

    def test_repetitive_1m(self):
        self._roundtrip(b'abcdefgh' * 125000)

    def test_multi_chunk(self):
        # > 64 KiB forces multiple chunks through the container format
        self._roundtrip(os.urandom(200000))

    def test_decompress_rejects_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'input.bin')
            with open(src, 'wb') as f:
                f.write(b'corrupt me' * 1000)
            compressed = compress_file(src)
            with open(compressed, 'r+b') as f:
                f.seek(-10, os.SEEK_END)
                f.write(b'\x00' * 10)
            with self.assertRaises(ValueError):
                decompress_file(compressed)

    def test_decompress_never_overwrites_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'data.bin')
            with open(src, 'wb') as f:
                f.write(b'data' * 100)
            # Valid archive, but without the .vzip suffix
            archive = os.path.join(tmp, 'archive.dat')
            os.rename(compress_file(src), archive)
            out = decompress_file(archive)
            self.assertEqual(out, archive + '.restored')
            with open(out, 'rb') as f:
                self.assertEqual(f.read(), b'data' * 100)
            with open(archive, 'rb') as f:  # input untouched
                self.assertTrue(len(f.read()) > 0)


class TestLz77(unittest.TestCase):
    def _rt(self, data):
        self.assertEqual(lz77_decompress(lz77_compress(data)), data)

    def test_empty(self):
        self._rt(b'')

    def test_literals_only(self):
        self._rt(b'abcdefgh')

    def test_runs(self):
        self._rt(b'A' * 1000)

    def test_repeating_pattern(self):
        self._rt(b'abcabcabcabc')

    def test_match_to_end_of_input(self):
        self._rt(b'xyz' * 100 + b'xyz' * 50)

    def test_binary(self):
        self._rt(bytes(range(256)) * 4)

    def test_rejects_truncated(self):
        with self.assertRaises(ValueError):
            lz77_decompress(b'\x00\x00\x00')


class TestHuffman(unittest.TestCase):
    def _rt(self, data):
        encoded, pad, table = huffman_encode(data)
        self.assertEqual(huffman_decode(encoded, pad, table), data)

    def test_empty(self):
        self._rt(b'')

    def test_single_symbol(self):
        encoded, pad, table = huffman_encode(b'\x00' * 10000)
        self.assertTrue(len(encoded) > 0)  # must not encode to nothing
        self.assertEqual(huffman_decode(encoded, pad, table), b'\x00' * 10000)

    def test_two_symbols(self):
        self._rt(b'AB' * 500)

    def test_text(self):
        self._rt(b'The quick brown fox jumps over the lazy dog. ' * 20)

    def test_all_bytes(self):
        self._rt(bytes(range(256)))

    def test_table_serialization_roundtrip(self):
        from src.huffman import serialize_table, deserialize_table
        _, _, table = huffman_encode(bytes(range(256)) * 10)
        self.assertEqual(deserialize_table(serialize_table(table)), table)


if __name__ == '__main__':
    unittest.main()
