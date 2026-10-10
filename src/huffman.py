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
    bits = bytearray()
    acc = 0
    nbits = 0
    for b in data:
        code = table[b]
        acc = (acc << len(code)) | int(code, 2)
        nbits += len(code)
        while nbits >= 8:
            nbits -= 8
            bits.append((acc >> nbits) & 0xFF)
        acc &= (1 << nbits) - 1  # drop emitted bits; keeps acc O(1) in size
    pad = (8 - nbits) % 8
    if nbits:
        bits.append((acc << pad) & 0xFF)
    return bytes(bits), pad, table


def huffman_decode(encoded_data, padding, table):
    """Decode packed bytes using ``table`` (inverse of huffman_encode).

    Table-driven: the code table is compiled into a binary decode tree
    once, then the input is consumed byte-at-a-time through a bit cursor.
    Never materializes the bitstream as a string (the old implementation
    expanded every input byte into 8 characters).
    """
    if not table or not encoded_data:
        return b''
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
    decoded = bytearray()
    node = root
    seen = 0
    for byte in encoded_data:
        remaining = total_bits - seen
        if remaining <= 0:
            break
        take = 8 if remaining >= 8 else remaining
        # Consume `take` bits MSB-first.
        for shift in range(7, 7 - take, -1):
            try:
                node = node['1' if (byte >> shift) & 1 else '0']
            except KeyError:
                raise ValueError('corrupt file: invalid Huffman bitstream')
            sym = node.get('sym')
            if sym is not None:
                decoded.append(sym)
                node = root
        seen += take
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
