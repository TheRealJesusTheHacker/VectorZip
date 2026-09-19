"""VectorZip command-line interface: compress/decompress files."""
import os
import sys
import argparse

from tqdm import tqdm

try:
    # Installed package layout
    from vectorzip.compressor import compress_file, decompress_file
except ImportError:
    # Running from the repo root
    from src.compressor import compress_file, decompress_file


def _run_with_progress(label, func, path):
    total = os.path.getsize(path)
    with tqdm(total=total, unit='B', unit_scale=True, desc=label) as pbar:
        def _cb(done, _total):
            pbar.update(done - pbar.n)
        return func(path, progress=_cb)


def main():
    parser = argparse.ArgumentParser(
        description="VectorZip: a lossless, chunked-processing compression utility."
    )
    parser.add_argument("action", choices=["compress", "decompress"],
                        help="Action to perform")
    parser.add_argument("file", help="Path to the target file")

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print("Error: file not found: {}".format(args.file))
        sys.exit(1)

    try:
        if args.action == "compress":
            output = _run_with_progress("Compressing", compress_file, args.file)
            print("Success! Created: {}".format(output))
        else:
            output = _run_with_progress("Decompressing", decompress_file, args.file)
            print("Success! Extracted: {}".format(output))
    except Exception as e:
        print("Error: Operation failed - {}".format(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
