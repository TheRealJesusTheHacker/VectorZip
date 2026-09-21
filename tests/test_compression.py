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


class TestFormatV2Workhorse(unittest.TestCase):
    """v1.2.0: raw-store fallback for incompressible chunks, v1 back-compat."""

    def _compress(self, tmp, data, name='input.bin'):
        src = os.path.join(tmp, name)
        with open(src, 'wb') as f:
            f.write(data)
        return compress_file(src)

    def test_v2_magic_present(self):
        import struct
        with tempfile.TemporaryDirectory() as tmp:
            vp = self._compress(tmp, b'hello world' * 1000)
            with open(vp, 'rb') as f:
                self.assertEqual(f.read(4), b'VZP3')  # v3 since 1.2.2

    def test_truncated_at_chunk_boundary_rejected(self):
        # Regression: a v2 file cut exactly at a chunk boundary used to
        # silently decompress to partial data. v3 must raise.
        import random
        random.seed(7)
        data = b'chunk-boundary test data. ' * 8000  # > 1 chunk
        with tempfile.TemporaryDirectory() as tmp:
            vp = self._compress(tmp, data)
            with open(vp, 'rb') as f:
                blob = f.read()
            # Find the end of the first data chunk (8 = header + 8 = END marker)
            cut = len(blob) - 8  # strip only the END marker
            cut_vp = os.path.join(tmp, 'cut.vzip')
            with open(cut_vp, 'wb') as f:
                f.write(blob[:cut])
            with self.assertRaises(ValueError):
                decompress_file(cut_vp)

    def test_data_after_end_marker_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            vp = self._compress(tmp, b'trailing junk test' * 500)
            with open(vp, 'ab') as f:
                f.write(b'junk')
            with self.assertRaises(ValueError):
                decompress_file(vp)

    def test_v2_file_still_decompresses(self):
        # Hand-build a legacy v2 file (magic VZP2, no END marker) and read it.
        import struct
        import zlib
        from src.huffman import serialize_table
        chunk = b'v2 format still works! ' * 500
        chk = zlib.crc32(chunk) & 0xFFFFFFFF
        lz_data = lz77_compress(chunk)
        encoded, pad, table = huffman_encode(lz_data)
        blob = serialize_table(table)
        with tempfile.TemporaryDirectory() as tmp:
            vp = os.path.join(tmp, 'legacy2.vzip')
            with open(vp, 'wb') as f:
                f.write(b'VZP2')
                f.write(struct.pack('>IHBB', chk, len(blob), pad, 0))
                f.write(blob)
                f.write(struct.pack('>I', len(encoded)))
                f.write(encoded)
            restored = decompress_file(vp)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), chunk)

    def test_random_data_not_expanded(self):
        # Incompressible input must never grow: raw-store fallback.
        with tempfile.TemporaryDirectory() as tmp:
            data = os.urandom(100000)
            vp = self._compress(tmp, data)
            self.assertLessEqual(os.path.getsize(vp), len(data) + 64)

    def test_random_data_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = os.urandom(100000)
            vp = self._compress(tmp, data)
            restored = decompress_file(vp)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), data)

    def test_mixed_chunks_roundtrip(self):
        # One compressible chunk + one random chunk in the same file.
        import random
        random.seed(99)
        data = (b'ABCD' * 20000 +
                bytes(random.getrandbits(8) for _ in range(70000)))
        with tempfile.TemporaryDirectory() as tmp:
            vp = self._compress(tmp, data)
            restored = decompress_file(vp)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), data)

    def test_v1_file_still_decompresses(self):
        # Hand-build a legacy v1 file (no magic, '>IHB' header) and read it.
        import struct
        import zlib
        from src.huffman import serialize_table
        chunk = b'legacy format still works! ' * 500
        chk = zlib.crc32(chunk) & 0xFFFFFFFF
        lz_data = lz77_compress(chunk)
        encoded, pad, table = huffman_encode(lz_data)
        blob = serialize_table(table)
        with tempfile.TemporaryDirectory() as tmp:
            vp = os.path.join(tmp, 'legacy.vzip')
            with open(vp, 'wb') as f:
                f.write(struct.pack('>IHB', chk, len(blob), pad))
                f.write(blob)
                f.write(struct.pack('>I', len(encoded)))
                f.write(encoded)
            restored = decompress_file(vp)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), chunk)

    def test_v1_random_data_still_decompresses(self):
        # Legacy v1 files that were *expanded* by the old encoder still read.
        import struct
        import zlib
        from src.huffman import serialize_table
        chunk = os.urandom(5000)
        chk = zlib.crc32(chunk) & 0xFFFFFFFF
        lz_data = lz77_compress(chunk)
        encoded, pad, table = huffman_encode(lz_data)
        blob = serialize_table(table)
        with tempfile.TemporaryDirectory() as tmp:
            vp = os.path.join(tmp, 'legacy.vzip')
            with open(vp, 'wb') as f:
                f.write(struct.pack('>IHB', chk, len(blob), pad))
                f.write(blob)
                f.write(struct.pack('>I', len(encoded)))
                f.write(encoded)
            restored = decompress_file(vp)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), chunk)

    def test_corrupt_raw_chunk_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            vp = self._compress(tmp, os.urandom(100000))
            with open(vp, 'r+b') as f:
                f.seek(20)
                b = f.read(1)
                f.seek(20)
                f.write(bytes([b[0] ^ 0xFF]))
            with self.assertRaises(ValueError):
                decompress_file(vp)

    def test_tiny_corrupt_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            vp = os.path.join(tmp, 'tiny.vzip')
            with open(vp, 'wb') as f:
                f.write(b'\x01\x02')
            with self.assertRaises(ValueError):
                decompress_file(vp)
