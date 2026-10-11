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


def _run_with_progress(label, func, path, **kwargs):
    total = os.path.getsize(path)
    with tqdm(total=total, unit='B', unit_scale=True, desc=label) as pbar:

        def _cb(done, _total):
            pbar.update(done - pbar.n)

        return func(path, progress=_cb, **kwargs)


def _expected_output(action, path):
    if action == 'compress':
        return path + '.vzip'
    if path.endswith('.vzip'):
        return path[: -len('.vzip')] + '.restored'
    return path + '.restored'


def _quarantine_partial(path):
    """Rename a half-written output to .partial so it can't be mistaken
    for a good result (mirrors the GUI worker)."""
    if os.path.exists(path):
        try:
            os.rename(path, path + '.partial')
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="VectorZip: a lossless, chunked-processing compression utility."
    )
    parser.add_argument("action", choices=["compress", "decompress"], help="Action to perform")
    parser.add_argument("file", help="Path to the target file")
    parser.add_argument(
        "--max-output-gb",
        type=float,
        default=None,
        metavar="GB",
        help="Decompression safety cap in GiB (default: 8)",
    )
    parser.add_argument(
        "--no-output-limit",
        action="store_true",
        help="Disable the decompression output safety cap entirely",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files")

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print("Error: file not found: {}".format(args.file))
        sys.exit(1)

    if args.max_output_gb is not None and args.max_output_gb <= 0:
        parser.error("--max-output-gb must be positive")

    expected = _expected_output(args.action, args.file)
    try:
        if args.action == "compress":
            output = _run_with_progress(
                "Compressing", compress_file, args.file, overwrite=args.force
            )
            print("Success! Created: {}".format(output))
        else:
            kwargs = {"overwrite": args.force}
            if args.no_output_limit:
                kwargs["max_output_bytes"] = None
            elif args.max_output_gb is not None:
                kwargs["max_output_bytes"] = int(args.max_output_gb * 1024**3)
            output = _run_with_progress("Decompressing", decompress_file, args.file, **kwargs)
            print("Success! Extracted: {}".format(output))
    except KeyboardInterrupt:
        _quarantine_partial(expected)
        print("\nCancelled — partial output quarantined")
        sys.exit(130)
    except MemoryError:
        # MemoryError inherits BaseException, not Exception, so it needs
        # its own handler — otherwise a decompression bomb kills the CLI
        # with a raw traceback instead of a clean error.
        _quarantine_partial(expected)
        print("Error: out of memory — the input file may be corrupt or " "a decompression bomb")
        sys.exit(1)
    except Exception as e:
        print("Error: Operation failed - {}".format(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
