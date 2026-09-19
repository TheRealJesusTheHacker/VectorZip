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
    bits = ''.join(table[b] for b in data)
    pad = (8 - (len(bits) % 8)) % 8
    bits += '0' * pad
    arr = bytearray(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    return bytes(arr), pad, table


def huffman_decode(encoded_data, padding, table):
    """Decode packed bytes using ``table`` (inverse of huffman_encode)."""
    reverse_table = {v: k for k, v in table.items()}
    bits = ''.join(bin(b)[2:].zfill(8) for b in encoded_data)
    if padding > 0:
        bits = bits[:-padding]
    decoded, buffer = bytearray(), ""
    for bit in bits:
        buffer += bit
        if buffer in reverse_table:
            decoded.append(reverse_table[buffer])
            buffer = ""
    return bytes(decoded)


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


def deserialize_table(buf):
    """Inverse of :func:`serialize_table`."""
    table = {}
    i, n = 0, len(buf)
    while i < n:
        if i + 2 > n:
            raise ValueError('corrupt Huffman table: truncated entry')
        symbol, bitlen = struct.unpack('>BB', buf[i:i + 2])
        i += 2
        nbytes = (bitlen + 7) // 8
        if i + nbytes > n:
            raise ValueError('corrupt Huffman table: truncated code')
        val = int.from_bytes(buf[i:i + nbytes], 'big')
        i += nbytes
        table[symbol] = bin(val)[2:].zfill(bitlen) if bitlen else ''
    return table
