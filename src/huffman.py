"""Huffman entropy coding plus table (de)serialization for the file format."""

import heapq
import struct
from collections import Counter


def huffman_encode(data):
    """Encode bytes -> (packed_bytes, pad_bits, table).

    ``table`` maps each byte value to its bit-string code.
    """
    if not data:
        return b'', 0, {}
    freq = Counter(data)
    heap = [[weight, [symbol, '']] for symbol, weight in freq.items()]
    heapq.heapify(heap)
    while len(heap) > 1:
        lo, hi = heapq.heappop(heap), heapq.heappop(heap)
        for p in lo[1:]:
            p[1] = '0' + p[1]
        for p in hi[1:]:
            p[1] = '1' + p[1]
        heapq.heappush(heap, [lo[0] + hi[0]] + lo[1:] + hi[1:])
    table = dict(heapq.heappop(heap)[1:])
    if len(table) == 1:
        # Single distinct symbol: the heap never merged, so the code would
        # be '' and encode to zero bits. Assign a 1-bit code instead.
        sole = next(iter(table))
        table[sole] = '0'
    # Integer codes precomputed once per table instead of per input byte,
    # in parallel lists indexed by byte value (cheaper than a dict of
    # tuples in the per-byte loop).
    codes = [0] * 256
    clens = [0] * 256
    for sym, code in table.items():
        codes[sym] = int(code, 2) if code else 0
        clens[sym] = len(code)
    bits = bytearray()
    acc = 0
    nbits = 0
    for b in data:
        acc = (acc << clens[b]) | codes[b]
        nbits += clens[b]
        while nbits >= 8:
            nbits -= 8
            bits.append((acc >> nbits) & 0xFF)
        acc &= (1 << nbits) - 1  # drop emitted bits; keeps acc O(1) in size
    pad = (8 - nbits) % 8
    if nbits:
        bits.append((acc << pad) & 0xFF)
    return bytes(bits), pad, table


# Width (in bits) of the decode lookup table. A window of this many bits
# resolves most symbols in one list index instead of one tree step per
# bit. 9 keeps the table at 512 entries, so building it per call stays
# cheap next to the bitstream it accelerates.
_LUT_BITS = 9


def huffman_decode(encoded_data, padding, table):
    """Decode packed bytes using ``table`` (inverse of huffman_encode).

    Table-driven: the code table is compiled into a binary decode tree
    once, then the input is consumed through a bit accumulator. On top
    of the tree sits a lookup table keyed by the next ``_LUT_BITS``
    bits of the accumulator: each entry records the symbol the tree
    walk would emit and how many bits it consumes, the fact that the
    walk would hit a missing child (an invalid bitstream), or the tree
    node a longer code continues from. Codes longer than the window,
    and the final partial window, fall back to the same per-bit tree
    walk — so the emitted bytes and the ``ValueError`` behavior are
    exactly the tree walk's.
    Never materializes the bitstream as a string (the old implementation
    expanded every input byte into 8 characters).
    """
    if not table or not encoded_data:
        return b''
    # Padding is the number of unused bits in the final byte, so the
    # encoder only ever produces 0..7. The container reader validates
    # this before calling, but huffman_decode is also a public API:
    # an out-of-range value previously either crashed with IndexError
    # (negative) or silently returned truncated/empty output (too
    # large) instead of the ValueError corrupt-input contract the rest
    # of the format code uses.
    if not 0 <= padding <= 7:
        raise ValueError('corrupt file: invalid Huffman padding')
    # The table must really be prefix-free, as the encoder's always is:
    # a code that duplicates another, or that is a prefix of (or has as
    # a prefix) another code, makes the longer code unreachable or the
    # shorter one ambiguous, and used to be silently reinterpreted —
    # it is now refused up front with the corrupt-input contract.
    _check_prefix_free(table.values(), 'corrupt file: invalid Huffman code table')
    # Compile the prefix-free code table into a decode tree.
    # Internal nodes: {'0': child, '1': child}; leaves: {'sym': byte}.
    root = {}
    for symbol, code in table.items():
        node = root
        for bit in code:
            child = node.get(bit)
            if child is None:
                child = {}
                node[bit] = child
            node = child
        node['sym'] = symbol
    total_bits = len(encoded_data) * 8 - padding
    if total_bits <= 0:
        return b''
    width = min(_LUT_BITS, max(len(code) for code in table.values()))
    lut = None
    if width > 0:
        # Entry shapes: (symbol, depth) — emit symbol, consume depth
        # bits; (-1, depth) — the tree walk hits a missing child within
        # the window; (None, node) — no symbol within the window, so
        # continue the walk from node after consuming the whole window.
        lut = []
        for window in range(1 << width):
            node = root
            entry = None
            for depth in range(1, width + 1):
                bit = (window >> (width - depth)) & 1
                child = node.get('1' if bit else '0')
                if child is None:
                    entry = (-1, depth)
                    break
                node = child
                sym = node.get('sym')
                if sym is not None:
                    entry = (sym, depth)
                    break
            lut.append(entry if entry is not None else (None, node))
    mask = (1 << width) - 1
    decoded = bytearray()
    append = decoded.append
    acc = 0  # bit accumulator: the next bits to consume are its low accbits
    accbits = 0
    idx = 0  # next byte of encoded_data to feed into acc
    consumed = 0
    node = root
    while consumed < total_bits:
        if node is root and lut is not None and total_bits - consumed >= width:
            while accbits < width:
                acc = (acc << 8) | encoded_data[idx]
                idx += 1
                accbits += 8
            sym, extra = lut[(acc >> (accbits - width)) & mask]
            if sym is None:
                # Code longer than the window: continue from this node.
                node = extra
                accbits -= width
                consumed += width
            elif sym < 0:
                raise ValueError('corrupt file: invalid Huffman bitstream')
            else:
                append(sym)
                accbits -= extra
                consumed += extra
            acc &= (1 << accbits) - 1
            continue
        # Per-bit walk: finishing a long code, or fewer than ``width``
        # bits remain in the stream.
        if accbits == 0:
            acc = encoded_data[idx]
            idx += 1
            accbits = 8
        accbits -= 1
        bit = (acc >> accbits) & 1
        acc &= (1 << accbits) - 1
        consumed += 1
        try:
            node = node['1' if bit else '0']
        except KeyError:
            raise ValueError('corrupt file: invalid Huffman bitstream')
        sym = node.get('sym')
        if sym is not None:
            append(sym)
            node = root
    return bytes(decoded)


def _check_prefix_free(codes, message):
    """Raise ``ValueError(message)`` unless ``codes`` is prefix-free.

    Every code must be a non-empty string of '0'/'1' bits, no code may
    duplicate another, and no code may be a prefix of another. Checked
    with interval arithmetic: left-aligned in a field as wide as the
    longest code, each code covers the range of field values it is a
    prefix of, and two codes conflict exactly when their ranges
    overlap — one sort (C speed) plus one pass over at most 256 ranges,
    so valid tables pay almost nothing for the check.
    """
    codes = list(codes)
    for code in codes:
        if not isinstance(code, str) or not code or code.strip('01'):
            raise ValueError(message)
    if len(codes) < 2:
        return
    width = max(len(code) for code in codes)
    ranges = sorted(
        (int(code, 2) << (width - len(code)), (int(code, 2) + 1) << (width - len(code)))
        for code in codes
    )
    for (_, end), (start, _) in zip(ranges, ranges[1:]):
        if start < end:
            raise ValueError(message)


def serialize_table(table):
    """Serialize a Huffman table to bytes.

    Per entry: symbol (u8), code length in bits (u8), then the code bits
    packed MSB-first into ceil(bitlen / 8) bytes.
    """
    buf = bytearray()
    for symbol, code in table.items():
        bitlen = len(code)
        buf.extend(struct.pack('>BB', symbol, bitlen))
        nbytes = (bitlen + 7) // 8
        val = int(code, 2) if code else 0
        buf.extend(val.to_bytes(nbytes, 'big'))
    return bytes(buf)


# Deepest code the encoder can legitimately produce. Huffman depth is
# bounded by the Fibonacci growth of symbol weights (a depth-d code needs
# total weight >= Fib(d+2)), so a 64 KiB chunk tops out near 26 bits and
# even a GiB-scale in-memory stream near 45. 64 leaves wide margin while
# keeping a hostile table from forcing a decode tree hundreds of levels
# deep out of a 64 KiB blob.
_MAX_CODE_BITS = 64


def deserialize_table(buf):
    """Inverse of :func:`serialize_table`.

    Strict on purpose: the table bytes come straight from the (possibly
    hostile) input file, so entries :func:`serialize_table` could never
    have written — a zero-length code, a code longer than
    ``_MAX_CODE_BITS``, a code value that does not fit in its declared
    bit length, a symbol listed twice, or a code that duplicates or
    prefix-conflicts with another entry's code (the encoder's tables
    are always prefix-free) — are rejected with ``ValueError`` instead
    of being silently reinterpreted.
    """
    table = {}
    i, n = 0, len(buf)
    while i < n:
        if i + 2 > n:
            raise ValueError('corrupt Huffman table: truncated entry')
        symbol, bitlen = struct.unpack('>BB', buf[i : i + 2])
        i += 2
        if bitlen == 0 or bitlen > _MAX_CODE_BITS:
            raise ValueError('corrupt Huffman table: invalid code length')
        nbytes = (bitlen + 7) // 8
        if i + nbytes > n:
            raise ValueError('corrupt Huffman table: truncated code')
        val = int.from_bytes(buf[i : i + nbytes], 'big')
        i += nbytes
        if val >= (1 << bitlen):
            raise ValueError('corrupt Huffman table: code exceeds its bit length')
        if symbol in table:
            raise ValueError('corrupt Huffman table: duplicate symbol')
        table[symbol] = bin(val)[2:].zfill(bitlen)
    _check_prefix_free(
        table.values(), 'corrupt Huffman table: duplicate or prefix-conflicting code'
    )
    return table
