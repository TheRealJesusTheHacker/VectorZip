#!/usr/bin/env python3
"""Fuzz VectorZip's decompressor using only the standard library.

Builds a seed corpus of valid .vzip files, then feeds mutated / truncated /
random bytes into ``decompress_file`` and asserts that:

  * no exception other than ValueError / MemoryError escapes, and
  * no single case hangs (per-case wall-clock timeout via SIGALRM on Unix).

Usage:
    python tests/fuzz_decompress.py [--seconds 300] [--seed 0] [--case-timeout 10]

Run from the repo root (imports ``src.compressor`` like the test suite).
Exit code 0 = clean, 1 = unexpected exception or hang found.
"""

import argparse
import os
import random
import signal
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.compressor import compress_file, decompress_file  # noqa: E402

# Small output cap keeps adversarial cases fast. The cap logic under test is
# the same code path as the 8 GiB default.
FUZZ_MAX_OUTPUT = 32 * 1024 * 1024

# These are the decompressor's documented failure modes for hostile input.
EXPECTED = (ValueError, MemoryError)


class CaseTimeout(Exception):
    """Raised when a single fuzz case exceeds its wall-clock budget."""


def _has_alarm():
    return hasattr(signal, "alarm")


def _on_alarm(signum, frame):
    raise CaseTimeout()


def _arm(timeout_s):
    if _has_alarm():
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(int(timeout_s))


def _disarm():
    if _has_alarm():
        signal.alarm(0)


def build_corpus(tmpdir, rng):
    """Compress sample payloads; return the resulting .vzip blobs."""
    payloads = [
        b"",
        b"\x00" * 4096,
        b"hello world, " * 2000,
        bytes(range(256)) * 40,
        bytes(rng.randrange(256) for _ in range(8192)),
        b"A" * 70000,  # spans multiple 64 KiB chunks
    ]
    seeds = []
    for n, payload in enumerate(payloads):
        src = os.path.join(tmpdir, f"seed{n}.bin")
        with open(src, "wb") as f:
            f.write(payload)
        try:
            out = compress_file(src, overwrite=True)
            with open(out, "rb") as f:
                seeds.append(f.read())
        except Exception as exc:  # noqa: BLE001 - corpus build must not die quietly
            print(f"WARNING: seed {n} failed to compress: {exc!r}")
    return seeds


def mutate(rng, seeds):
    """Return a mutated blob derived from the seed corpus (or pure random)."""
    seed = bytearray(rng.choice(seeds))
    choice = rng.random()
    if choice < 0.25 and len(seed) > 1:
        cut = rng.randrange(len(seed))
        return bytes(seed[:cut])
    if choice < 0.45:
        for _ in range(rng.randint(1, max(1, len(seed) // 16))):
            if seed:
                seed[rng.randrange(len(seed))] = rng.randrange(256)
        return bytes(seed)
    if choice < 0.60:
        other = rng.choice(seeds)
        at = rng.randrange(len(seed) + 1)
        return bytes(seed[:at] + other[: rng.randrange(len(other) + 1)] + seed[at:])
    if choice < 0.75:
        at = rng.randrange(len(seed) + 1)
        chunk = bytes(rng.randrange(256) for _ in range(rng.randint(1, 64)))
        return bytes(seed[:at] + chunk + seed[at:])
    if choice < 0.90:
        for i in range(min(len(seed), 24)):  # smash the header region
            if rng.random() < 0.7:
                seed[i] = rng.randrange(256)
        return bytes(seed)
    # pure random blob
    return bytes(rng.randrange(256) for _ in range(rng.randint(0, 70000)))


def run_case(blob, tmpdir, case_timeout):
    """Decompress one blob. Returns 'ok', 'expected', 'TIMEOUT', or the exception."""
    path = os.path.join(tmpdir, "fuzzcase.bin")
    with open(path, "wb") as f:
        f.write(blob)
    _arm(case_timeout)
    try:
        try:
            decompress_file(path, max_output_bytes=FUZZ_MAX_OUTPUT, overwrite=True)
        except EXPECTED:
            return "expected"
        return "ok"
    except CaseTimeout:
        return "TIMEOUT"
    except Exception as exc:  # noqa: BLE001 - any other escape is a bug
        return exc
    finally:
        _disarm()
        for suffix in (".restored",):
            try:
                os.unlink(path + suffix)
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description="Fuzz VectorZip's decompressor.")
    parser.add_argument("--seconds", type=float, default=300,
                        help="total fuzzing time budget")
    parser.add_argument("--seed", type=int, default=0,
                        help="PRNG seed for reproducibility")
    parser.add_argument("--case-timeout", type=float, default=10,
                        help="per-case wall-clock timeout in seconds (SIGALRM; Unix only)")
    args = parser.parse_args()
    rng = random.Random(args.seed)

    with tempfile.TemporaryDirectory() as tmpdir:
        seeds = build_corpus(tmpdir, rng)
        if not seeds:
            print("FATAL: could not build any seed corpus", flush=True)
            return 1
        print(f"seed corpus: {len(seeds)} files; budget {args.seconds}s", flush=True)

        fail_dir = os.path.join(os.getcwd(), "fuzz-failures")
        deadline = time.time() + args.seconds
        counts = {"ok": 0, "expected": 0}
        failures = []
        i = 0
        while time.time() < deadline and len(failures) < 5:
            i += 1
            blob = mutate(rng, seeds)
            result = run_case(blob, tmpdir, args.case_timeout)
            if result in counts:
                counts[result] += 1
            else:
                failures.append((i, blob, result))
                os.makedirs(fail_dir, exist_ok=True)
                with open(os.path.join(fail_dir, f"case-{i}.bin"), "wb") as f:
                    f.write(blob)
                print(f"\nFAILURE case {i}: {result!r}", flush=True)
                if isinstance(result, Exception):
                    traceback.print_exception(result)
            if i % 500 == 0:
                print(f"  ... {i} cases ({counts['ok']} ok, "
                      f"{counts['expected']} rejected, {len(failures)} failures)",
                      flush=True)

        print(f"\ndone: {i} cases — {counts['ok']} ok, "
              f"{counts['expected']} cleanly rejected, {len(failures)} failures",
              flush=True)
        if failures:
            print(f"repro inputs saved under {fail_dir}/", flush=True)
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
