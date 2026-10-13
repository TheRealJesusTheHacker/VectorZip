"""LZ77 sliding-window compression with a fixed 4-byte token format.

Token layout (big-endian ``>HBB``):
    dist  (u16): match distance back into the output (1..32768).
                 0 marks a literal token.
    len   (u8):  match length (3..255). 0 on literal tokens.
    next  (u8):  the byte following the match, or the literal byte itself.

Decoding rule: a literal token appends ``next``; a match token copies
``len`` bytes from ``dist`` bytes back and then appends ``next``.
Every match token is guaranteed to carry a valid ``next`` byte, so the
stream decodes unambiguously with no end marker.
"""

import struct

_TOKEN = struct.Struct('>HBB')
_WINDOW = 32768
_MIN_MATCH = 3
_MAX_MATCH = 255


def lz77_compress(data):
    """Compress bytes -> bytes using LZ77 tokens. Lossless."""
    data = bytes(data)
    n = len(data)
    if n == 0:
        return b''
    result = bytearray()
    # Map 3-byte sequences to their most recent position (greedy, fast).
    hash_chain = {}
    i = 0
    while i < n:
        best_len = 0
        best_dist = 0
        if i + _MIN_MATCH <= n:
            seq = data[i : i + _MIN_MATCH]
            j = hash_chain.get(seq)
            if j is not None:
                dist = i - j
                if dist <= _WINDOW:
                    max_len = min(_MAX_MATCH, n - i)
                    match_len = _MIN_MATCH
                    while match_len < max_len and data[j + match_len] == data[i + match_len]:
                        match_len += 1
                    if i + match_len < n:
                        best_len, best_dist = match_len, dist
                    elif match_len > _MIN_MATCH:
                        # Match runs to end of input: shrink by one so the
                        # token still carries a valid trailing "next" byte.
                        best_len, best_dist = match_len - 1, dist
                    # else: too short once shrunk -> emit literal below
            hash_chain[seq] = i
        if best_len >= _MIN_MATCH:
            result.extend(_TOKEN.pack(best_dist, best_len, data[i + best_len]))
            i += best_len + 1
        else:
            result.extend(_TOKEN.pack(0, 0, data[i]))
            i += 1
    return bytes(result)


def lz77_decompress(data, max_out=None):
    """Decompress bytes produced by :func:`lz77_compress`. Lossless.

    ``max_out`` optionally caps the decoded output size in bytes; decoding
    raises ``ValueError`` as soon as it is exceeded. The container reader
    passes its per-chunk cap so a malicious chunk cannot force a huge
    in-memory expansion before the checksum is verified.
    """
    data = bytes(data)
    if len(data) % _TOKEN.size != 0:
        raise ValueError('corrupt LZ77 stream: truncated token')
    out = bytearray()
    for dist, length, nxt in _TOKEN.iter_unpack(data):
        if dist == 0:
            if length != 0:
                raise ValueError('corrupt LZ77 stream: bad literal token')
            out.append(nxt)
        else:
            if dist > len(out) or length < _MIN_MATCH:
                raise ValueError('corrupt LZ77 stream: bad match token')
            start = len(out) - dist
            if length <= dist:
                # Non-overlapping copy: one slice copy at C speed instead
                # of a byte-by-byte append loop.
                out += out[start : start + length]
            else:
                # Overlapping copy: the source grows as bytes are
                # appended, so the copied run is exactly the periodic
                # repetition of the ``dist`` bytes that end the output —
                # which is what the old byte-by-byte loop produced.
                pat = out[start:]
                out += (pat * (length // dist + 1))[:length]
            out.append(nxt)
        if max_out is not None and len(out) > max_out:
            raise ValueError('corrupt LZ77 stream: chunk output exceeds limit')
    return bytes(out)
