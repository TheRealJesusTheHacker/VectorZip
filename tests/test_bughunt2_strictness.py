"""Round-2 bug hunt regressions: coded-chunk shapes the encoder never
writes, stream-termination pins, and CLI argument validation.

A coded (Huffman) chunk is only ever emitted for a non-empty input
chunk, so its serialized table is non-empty and its pad_bits — the
padding inside the final encoded byte — is in 0..7. The container
reader used to accept the shapes below anyway; an empty table was the
nasty one, because ``huffman_decode`` returns ``b''`` for it regardless
of the payload, so the chunk's encoded bytes were skipped undecoded
with only the CRC32 of ``b''`` (0) to satisfy. Both shapes now raise
``ValueError`` like every other malformed chunk.
"""

import os
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.compressor import (  # noqa: E402
    _CHUNK,
    _DATA_HEADER,
    _FLAG_END,
    _HEADER_V1,
    _HEADER_V2,
    compress_file,
    decompress_file,
)
from src.huffman import huffman_encode, serialize_table  # noqa: E402
from src.lz77 import lz77_compress  # noqa: E402

_END = _HEADER_V2.pack(0, 0, 0, _FLAG_END)
_PAYLOAD = b"hello world, hello vectorzip! " * 8


def _coded_chunk(chunk, pad=None, table_blob=None, encoded=None):
    lz = lz77_compress(chunk)
    enc, real_pad, table = huffman_encode(lz)
    tbl = serialize_table(table) if table_blob is None else table_blob
    enc = enc if encoded is None else encoded
    chk = zlib.crc32(chunk) & 0xFFFFFFFF
    return (
        _HEADER_V2.pack(chk, len(tbl), real_pad if pad is None else pad, 0)
        + tbl
        + _DATA_HEADER.pack(len(enc))
        + enc
    )


def _v1_chunk(chunk, table_blob=None, encoded=None):
    lz = lz77_compress(chunk)
    enc, pad, table = huffman_encode(lz)
    tbl = serialize_table(table) if table_blob is None else table_blob
    enc = enc if encoded is None else encoded
    chk = zlib.crc32(chunk) & 0xFFFFFFFF
    return _HEADER_V1.pack(chk, len(tbl), pad) + tbl + _DATA_HEADER.pack(len(enc)) + enc


class _Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def _write(self, name, blob):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as f:
            f.write(blob)
        return path

    def _decompress(self, blob, name="case.vzip"):
        return decompress_file(self._write(name, blob), overwrite=True)

    def _roundtrip(self, blob, expected, name="case.vzip"):
        out = self._decompress(blob, name)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), expected)


class TestCodedChunkStrictness(_Case):
    def test_ghost_chunk_payload_skipped_undecoded(self):
        # table_len=0 with 5 payload bytes and chk = crc32(b'') = 0:
        # pre-fix this chunk was silently swallowed.
        ghost = _HEADER_V2.pack(0, 0, 0, 0) + _DATA_HEADER.pack(5) + b"XXXXX"
        blob = b"VZP3" + ghost + _coded_chunk(_PAYLOAD) + _END
        with self.assertRaises(ValueError):
            self._decompress(blob)

    def test_empty_coded_chunk_rejected(self):
        ghost = _HEADER_V2.pack(0, 0, 0, 0) + _DATA_HEADER.pack(0)
        blob = b"VZP3" + ghost + _coded_chunk(_PAYLOAD) + _END
        with self.assertRaises(ValueError):
            self._decompress(blob)

    def test_ghost_chunk_v1_rejected(self):
        blob = _v1_chunk(_PAYLOAD, table_blob=b"", encoded=b"XXXXX")
        # v1 has no CRC-of-empty shortcut discussion: header crc belongs
        # to a real chunk, but the table is empty so it must not decode.
        with self.assertRaises(ValueError):
            self._decompress(blob)

    def test_pad_bits_above_seven_rejected(self):
        for pad in (8, 100, 255):
            blob = b"VZP3" + _coded_chunk(_PAYLOAD, pad=pad) + _END
            with self.assertRaises(ValueError, msg=f"pad={pad}"):
                self._decompress(blob)

    def test_pad_bits_seven_boundary_still_valid(self):
        # Find a payload whose honest encoding really uses pad == 7.
        chunk = None
        for n in range(1, 500):
            cand = bytes((i * 37 + n) % 256 for i in range(n))
            _, pad, _ = huffman_encode(lz77_compress(cand))
            if pad == 7:
                chunk = cand
                break
        self.assertIsNotNone(chunk, "no pad==7 fixture found")
        self._roundtrip(b"VZP3" + _coded_chunk(chunk) + _END, chunk)


class TestStreamTermination(_Case):
    def test_concatenated_v3_rejected(self):
        src = self._write("src.bin", _PAYLOAD)
        arc = compress_file(src, overwrite=True)
        with open(arc, "rb") as f:
            blob = f.read()
        with self.assertRaises(ValueError):
            self._decompress(blob + blob)

    def test_data_after_end_marker_rejected(self):
        blob = b"VZP3" + _coded_chunk(_PAYLOAD) + _END + b"x"
        with self.assertRaises(ValueError):
            self._decompress(blob)

    def test_missing_end_marker_rejected(self):
        blob = b"VZP3" + _coded_chunk(_PAYLOAD)
        with self.assertRaises(ValueError):
            self._decompress(blob)


class TestRawBoundaries(_Case):
    def _raw(self, body):
        chk = zlib.crc32(body) & 0xFFFFFFFF
        return (
            b"VZP3" + _HEADER_V2.pack(chk, 0, 0, 0x01) + _DATA_HEADER.pack(len(body)) + body + _END
        )

    def test_raw_at_cap_accepted(self):
        body = b"R" * 131072
        self._roundtrip(self._raw(body), body)

    def test_raw_above_cap_rejected(self):
        body = b"R" * 131073
        with self.assertRaises(ValueError):
            self._decompress(self._raw(body))


class TestAllVersionsStillDecode(_Case):
    def test_empty_payload_all_versions(self):
        # v3: what compress_file writes for an empty file.
        src = self._write("empty.bin", b"")
        arc = compress_file(src, overwrite=True)
        with open(arc, "rb") as f:
            self._roundtrip(f.read(), b"", "e3.vzip")
        # v2: magic + zero chunks (the v2 writer's empty file).
        self._roundtrip(b"VZP2", b"", "e2.vzip")
        # v1: the v1.0 writer's empty file is zero bytes long.
        self._roundtrip(b"", b"", "e1.vzip")

    def test_small_payload_all_versions(self):
        v3 = b"VZP3" + _coded_chunk(_PAYLOAD) + _END
        self._roundtrip(v3, _PAYLOAD, "s3.vzip")
        v2 = b"VZP2" + _coded_chunk(_PAYLOAD)
        self._roundtrip(v2, _PAYLOAD, "s2.vzip")
        v1 = _v1_chunk(_PAYLOAD)
        self._roundtrip(v1, _PAYLOAD, "s1.vzip")

    def test_multi_chunk_v3(self):
        payload = b"A" * (_CHUNK + 4464)
        src = self._write("big.bin", payload)
        arc = compress_file(src, overwrite=True)
        with open(arc, "rb") as f:
            self._roundtrip(f.read(), payload, "big.vzip")


class TestCliMaxOutputValidation(unittest.TestCase):
    def _run_main(self, argv_tail):
        import importlib.util

        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        spec = importlib.util.spec_from_file_location("vz_main", os.path.join(root, "main.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x")
            fname = f.name
        old_argv = sys.argv
        try:
            sys.argv = ["vectorzip", "decompress", fname] + argv_tail
            mod.main()
        finally:
            sys.argv = old_argv
            os.unlink(fname)

    def test_nonfinite_and_overflow_values_are_argument_errors(self):
        for val in ("inf", "-inf", "nan", "1e300", "0", "-1"):
            with self.assertRaises(SystemExit, msg=val) as cm:
                self._run_main(["--max-output-gb", val])
            self.assertEqual(cm.exception.code, 2, val)


if __name__ == "__main__":
    unittest.main()
