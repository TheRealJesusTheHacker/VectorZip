"""
VectorZip Engine
----------------
A high-performance hybrid compression library.
Combines LZ77 sliding window dictionary matching with Huffman entropy coding.

Usage:
    from vectorzip import compress_file, decompress_file

Attributes:
    __version__ (str): 1.0.0
"""

from .lz77 import lz77_compress, lz77_decompress
from .huffman import huffman_encode, huffman_decode
from .compressor import compress_file, decompress_file

# Public API Surface
__all__ = [
    'lz77_compress',
    'lz77_decompress',
    'huffman_encode',
    'huffman_decode',
    'compress_file',
    'decompress_file',
]

__version__ = '1.0.0'
