"""Chunked file compression: LZ77 -> Huffman -> .vzip container.

Format v3 (written by VectorZip >= 1.2.2):
    magic:       b'VZP3'
    per chunk:
      header:      crc32 u32 | table_len u16 | pad_bits u8 | flags u8  ('>IHBB')
      flags bit 0 (RAW): chunk stored literally, no LZ77/Huffman.
      flags bit 7 (END): end-of-stream marker chunk; carries no table and
                         no data. The decompressor requires this marker:
                         reaching EOF without it means the file was
                         truncated, and a ValueError is raised instead of
                         silently returning partial data.
      All other flag bits are reserved: a chunk carrying an unknown flag
      bit is rejected with ValueError rather than misparsed.
      if RAW:
        data header: raw_len u32                              ('>I')
        data:        raw_len bytes (the original chunk bytes)
      else:
        table:       table_len bytes (see huffman.serialize_table)
        data header: encoded_len u32                          ('>I')
        data:        encoded_len bytes of Huffman-packed LZ77 tokens

Format v2 (VectorZip 1.2.0/1.2.1, magic ``VZP2``) and format v1
(VectorZip 1.0.0/1.1.0, no magic, '>IHB' chunk header) are still fully
readable. Note: v1/v2 files have no end marker, so a v1/v2 file truncated
exactly at a chunk boundary decompresses to partial data without an
error; v3 closes that hole.

A chunk is stored RAW whenever compressing it would not shrink it, so
incompressible data (random bytes, already-compressed files) passes through
at I/O speed instead of being expanded by the entropy coder.

Decompression verifies the CRC32 of every chunk and raises ValueError
on any truncation or mismatch. Decoded chunks are additionally capped at
128 KiB *during* LZ77 expansion (legit chunks are exactly one 64 KiB input
chunk), so a malicious chunk cannot force a huge in-memory allocation
before the checksum is verified.
"""

import errno
import os
import struct
import zlib

from .lz77 import lz77_compress, lz77_decompress
from .huffman import huffman_encode, huffman_decode, serialize_table, deserialize_table

_CHUNK = 65536
_MAGIC = b'VZP3'
_MAGIC_V2 = b'VZP2'
_HEADER_V2 = struct.Struct('>IHBB')  # crc32, table_len, pad_bits, flags
_HEADER_V1 = struct.Struct('>IHB')  # crc32, table_len, pad_bits (no flags)
_DATA_HEADER = struct.Struct('>I')  # encoded_len / raw_len
_FLAG_RAW = 0x01
_FLAG_END = 0x80
# Decompression-bomb hardening. The lengths below come from the file and
# are attacker-controlled, so every read is capped *before* allocating.
# Legit raw chunks are never larger than one input chunk (64 KiB); legit
# encoded chunks are always smaller than the chunk they were made from.
_MAX_RAW_LEN = 131072  # 128 KiB
_MAX_ENCODED_LEN = 1048576  # 1 MiB
# A decoded chunk is exactly the 64 KiB input chunk it was made from, so
# anything past 128 KiB is a bomb: reject it *during* LZ77 expansion,
# before a crafted chunk can force a multi-hundred-MiB allocation that the
# total-output cap would only catch after the fact.
_MAX_CHUNK_OUT = 131072  # 128 KiB
_MAX_TABLE_LEN = 1048576  # 1 MiB (the u16 header already caps this at 64 KiB)
_DEFAULT_MAX_OUTPUT = 8 * 1024**3  # 8 GiB total-output guard
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
        seen.update(chunk[s * step : s * step + _SAMPLE_EACH])
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


def _read_bounded(fin, n, what, limit):
    """Like _read_exact, but rejects absurd sizes before allocating.

    ``fin.read(n)`` pre-allocates ``n`` bytes, so an attacker-controlled
    length must be validated first — otherwise a 4-byte header field can
    trigger a multi-gigabyte allocation.
    """
    if n > limit:
        raise ValueError(f'corrupt file: {what} size {n} exceeds limit {limit}')
    return _read_exact(fin, n, what)


def _format_cap(max_output):
    if max_output % 1024**3 == 0:
        return f'{int(max_output // 1024**3)} GiB'
    return f'{int(max_output)} bytes'


def _check_output_limit(done, max_output):
    if done > max_output:
        raise ValueError(
            f'decompressed output exceeds the safety cap of {_format_cap(max_output)} '
            f'(possible decompression bomb); use --max-output-gb or '
            f'--no-output-limit to override'
        )


def _open_new_output(path):
    """Open ``path`` for writing, refusing if anything already exists there.

    ``O_CREAT|O_EXCL`` makes the existence check atomic (no TOCTOU race),
    and ``O_NOFOLLOW`` (where the platform provides it) stops a pre-planted
    symlink from redirecting the write elsewhere.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o666)
    return os.fdopen(fd, 'wb')


def _output_writer(path, overwrite):
    return _open_overwrite_output(path) if overwrite else _open_new_output(path)


def _open_overwrite_output(path):
    """Open ``path`` for writing, clobbering it if it is a real file.

    ``O_NOFOLLOW`` (where the platform provides it) stops a pre-planted
    symlink from redirecting the write: ``evil.restored -> victim.txt``
    raises ``OSError`` (ELOOP) instead of silently overwriting
    ``victim.txt``. A missing file is created as usual, so real-file
    behaviour is unchanged.

    Hard links need a second step, because no open flag refuses them:
    a planted hard link at the output path would make a plain
    ``O_TRUNC`` write clobber the *other* file sharing the inode —
    which can even be the input file itself, truncated while it is
    being read. So an existing output is first opened *without*
    ``O_TRUNC`` and inspected through the fd (a path swap after the
    open cannot redirect an fd): a singly-linked regular file is
    truncated in place exactly as before, while a multiply-linked
    file is unlinked and replaced with a fresh file at the same path.
    The output path still ends up holding the new content, but the
    other link keeps its bytes. (On a platform that does not report a
    link count, ``st_nlink`` is 1 and the in-place path is taken —
    the same residual platform caveat as ``O_NOFOLLOW`` on Windows.)
    """
    nofollow = getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, os.O_WRONLY | nofollow)
    except FileNotFoundError:
        return _open_new_output(path)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise OSError(
                errno.ELOOP,
                f'refusing to write through symlink at output path: {path} '
                f'(aborting to avoid clobbering the link target)',
            )
        raise
    try:
        st = os.fstat(fd)
    except BaseException:
        os.close(fd)
        raise
    if st.st_nlink > 1:
        # Multiply-linked: never truncate the shared inode. Drop this
        # name and create a fresh file in its place (O_EXCL, so a name
        # planted in the gap fails the open instead of being followed).
        os.close(fd)
        os.unlink(path)
        return _open_new_output(path)
    os.ftruncate(fd, 0)
    return os.fdopen(fd, 'wb')


def _input_fingerprint(path):
    """Identity snapshot of the input file: inode, size, and mtime.

    Compared before/after compression so a file that changed mid-job
    (concurrent writer, truncation, replacement) fails loudly instead of
    producing a torn archive that looks complete.
    """
    st = os.stat(path)
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def _decompress_chunks(fin, fout, progress, total, max_output, header, require_end):
    """Shared chunk loop for format v1/v2/v3.

    ``header`` is the chunk header struct (v1 has no flags byte; its
    chunks are always Huffman-coded). ``require_end`` is v3-only: the
    stream must terminate with an explicit END marker chunk, and EOF
    without it means the file was truncated. Per-version validation
    order and error messages are preserved exactly.
    """
    is_v1 = header is _HEADER_V1
    done = 0
    while True:
        raw_header = fin.read(header.size)
        if not raw_header:
            if require_end:
                raise ValueError('corrupt file: truncated file (missing end-of-stream marker)')
            break
        if len(raw_header) < header.size:
            raise ValueError('corrupt file: truncated chunk header')
        if is_v1:
            chk, table_len, pad = header.unpack(raw_header)
            flags = 0
        else:
            chk, table_len, pad, flags = header.unpack(raw_header)
            if require_end:
                if flags & ~(_FLAG_RAW | _FLAG_END):
                    raise ValueError('corrupt file: unknown chunk flags')
                if flags & _FLAG_END:
                    if flags & _FLAG_RAW or table_len or pad:
                        raise ValueError('corrupt file: malformed end marker')
                    if fin.read(1):
                        raise ValueError('corrupt file: data after end marker')
                    break
            elif flags & ~_FLAG_RAW:
                # v2 has no END marker: the only legal flag bit is RAW.
                raise ValueError('corrupt file: unknown chunk flags')
        if flags & _FLAG_RAW:
            raw_len = _DATA_HEADER.unpack(_read_exact(fin, _DATA_HEADER.size, 'data header'))[0]
            original = _read_bounded(fin, raw_len, 'raw chunk data', _MAX_RAW_LEN)
        else:
            table_blob = _read_bounded(fin, table_len, 'Huffman table', _MAX_TABLE_LEN)
            table = deserialize_table(table_blob)
            # A coded chunk the encoder could never write: pad_bits is the
            # padding inside the final encoded byte, so it is 0..7 by
            # construction, and a coded chunk always carries a non-empty
            # table (its bitstream is non-empty). Anything else is
            # malformed — an empty table in particular would make the
            # decoder skip the chunk's payload bytes without decoding
            # them, with only the CRC of b'' to satisfy.
            if pad > 7:
                raise ValueError('corrupt file: invalid pad bits')
            if not table:
                raise ValueError('corrupt file: empty Huffman table')
            encoded_len = _DATA_HEADER.unpack(_read_exact(fin, _DATA_HEADER.size, 'data header'))[0]
            encoded = _read_bounded(fin, encoded_len, 'chunk data', _MAX_ENCODED_LEN)
            original = lz77_decompress(huffman_decode(encoded, pad, table), max_out=_MAX_CHUNK_OUT)
        if (zlib.crc32(original) & 0xFFFFFFFF) != chk:
            raise ValueError('corrupt file: checksum mismatch')
        fout.write(original)
        done += len(original)
        _check_output_limit(done, max_output)
        if progress is not None:
            progress(done, total)


def _decompress_chunks_v3(fin, fout, progress, total, max_output):
    """v3 chunk loop: identical to v2, but the stream must end with an
    explicit END marker chunk. EOF without it means a truncated file."""
    _decompress_chunks(fin, fout, progress, total, max_output, _HEADER_V2, True)


def _decompress_chunks_v2(fin, fout, progress, total, max_output):
    _decompress_chunks(fin, fout, progress, total, max_output, _HEADER_V2, False)


def _decompress_chunks_v1(fin, fout, progress, total, max_output):
    _decompress_chunks(fin, fout, progress, total, max_output, _HEADER_V1, False)


def expected_output_path(path, mode):
    """Where compress/decompress writes its output for ``path``.

    Single source of truth shared by the CLI and the GUI (both used to
    carry their own copy of this naming rule): compress ->
    ``path + '.vzip'``; decompress -> ``'.restored'``, replacing a
    trailing ``'.vzip'`` when present. Mirrors the naming inside
    :func:`compress_file` / :func:`decompress_file` exactly.
    """
    if mode == 'compress':
        return path + '.vzip'
    if path.endswith('.vzip'):
        return path[: -len('.vzip')] + '.restored'
    return path + '.restored'


def compress_file(input_path, progress=None, overwrite=False):
    """Compress ``input_path`` to ``input_path + '.vzip'`` (format v3).

    ``progress`` is an optional callback ``(bytes_done, bytes_total)``
    invoked after each chunk.

    ``overwrite`` must be True to clobber an existing output file;
    otherwise a ``FileExistsError`` is raised. A symlink at the output
    path is never followed, on either path: non-overwrite raises
    ``FileExistsError``, overwrite aborts with ``OSError`` (ELOOP).

    If the input file changes while it is being read (concurrent writer,
    truncation, replacement), an ``IOError`` is raised instead of writing
    a torn archive that looks complete. The caller quarantines the partial
    output through its normal failure path.
    """
    output_path = input_path + '.vzip'
    if not overwrite and os.path.lexists(output_path):
        raise FileExistsError(
            f'refusing to overwrite existing output: {output_path} '
            f'(pass overwrite=True to allow it)'
        )
    total = os.path.getsize(input_path)
    fingerprint = _input_fingerprint(input_path)
    done = 0
    with open(input_path, 'rb') as fin, _output_writer(output_path, overwrite) as fout:
        fout.write(_MAGIC)
        while True:
            chunk = fin.read(_CHUNK)
            if not chunk:
                break
            _write_chunk_v2(fout, chunk)
            done += len(chunk)
            if progress is not None:
                progress(done, total)
        # End-of-stream marker: guarantees a truncated file can never
        # silently decompress to partial data.
        fout.write(_HEADER_V2.pack(0, 0, 0, _FLAG_END))
    if done != total or _input_fingerprint(input_path) != fingerprint:
        raise IOError(
            f'input file changed during compression: refusing to write '
            f'a torn archive for {input_path!r}'
        )
    if progress is not None:
        progress(total, total)
    return output_path


def decompress_file(
    input_path, progress=None, max_output_bytes=_DEFAULT_MAX_OUTPUT, overwrite=False
):
    """Decompress a ``.vzip`` file; returns the restored file path.

    Reads format v3 (magic ``VZP3``), v2 (magic ``VZP2``), and legacy
    format v1 files. The output never overwrites the input:
    ``'a.vzip'`` -> ``'a.restored'``, anything else -> ``input + '.restored'``.

    ``max_output_bytes`` caps the total decompressed output (default 8 GiB)
    as a last line of defense against decompression bombs; pass ``None``
    to disable.

    ``overwrite`` must be True to clobber an existing output file;
    otherwise a ``FileExistsError`` is raised. A symlink at the output
    path is never followed, on either path: non-overwrite raises
    ``FileExistsError``, overwrite aborts with ``OSError`` (ELOOP).
    """
    if input_path.endswith('.vzip'):
        output_path = input_path[: -len('.vzip')] + '.restored'
    else:
        output_path = input_path + '.restored'
    if os.path.abspath(output_path) == os.path.abspath(input_path):
        raise ValueError('refusing to overwrite the input file')
    if not overwrite and os.path.lexists(output_path):
        raise FileExistsError(
            f'refusing to overwrite existing output: {output_path} '
            f'(pass overwrite=True to allow it)'
        )
    if max_output_bytes is None:
        max_output_bytes = float('inf')
    total = os.path.getsize(input_path)
    with open(input_path, 'rb') as fin, _output_writer(output_path, overwrite) as fout:
        magic = fin.read(len(_MAGIC))
        if magic == _MAGIC:
            _decompress_chunks_v3(fin, fout, progress, total, max_output_bytes)
        elif magic == _MAGIC_V2:
            _decompress_chunks_v2(fin, fout, progress, total, max_output_bytes)
        elif not magic:
            # empty input -> empty output
            pass
        elif len(magic) < len(_MAGIC):
            raise ValueError('corrupt file: truncated chunk header')
        else:
            # Legacy v1 file: rewind and parse with the old header layout.
            fin.seek(0)
            _decompress_chunks_v1(fin, fout, progress, total, max_output_bytes)
    if progress is not None:
        progress(total, total)
    return output_path
