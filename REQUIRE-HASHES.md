# Hash-verified installs (`--require-hashes`)

Fleet policy (owner, adopted 2026-10-25): **every dependency install —
local, build, CI — verifies hashes against a committed lock generated
from a known-good resolution, and fails loudly on any mismatch.** A
version bump is not landed until its hashes are locked. Exceptions
exist only as documented entries with evidence (bottom of this file).

The human-edited pin files stay the source of truth for *versions*;
each install set has a sibling *lock* carrying the full resolved set
(direct + transitive) with a `sha256` hash for every artifact:

| Source input | Lock | Used by |
|---|---|---|
| `requirements.txt` | `requirements.lock.txt` | CI (Windows compile + CLI round-trip), both release jobs, README |
| `requirements-dev.txt` | `requirements-dev.lock.txt` | CI test jobs (Linux + Windows), development setup |
| `requirements-build.txt` | `requirements-build.lock.txt` | PyInstaller installs: CI Windows test job, both release jobs |
| `requirements-lint.txt` | `requirements-lint.lock.txt` | CI lint job (ruff + black) |
| `requirements-publish.txt` | `requirements-publish.lock.txt` | PyPI publish workflow (`pip` upgrade + `build`) |

Install form, everywhere: `pip install --require-hashes -r <lock>`
(the publish workflow keeps its `python -m pip install --upgrade`
shape, with `--require-hashes -r requirements-publish.lock.txt`).

The three tooling inputs (`requirements-build.txt`,
`requirements-lint.txt`, `requirements-publish.txt`) exist because
those pins previously lived inline in workflow YAML
(`pip install pyinstaller==6.22.3`, `pip install "ruff==0.17.0"
"black==26.10.1"`, `pip install --upgrade "pip==25.3" "build==1.3.0"`).
The pins are unchanged — they moved into files so they can be locked.

## How the locks were generated (2026-10-25)

`pip-compile --generate-hashes --allow-unsafe` (pip-tools 7.6.2,
CPython 3.12, Linux) per input. Hashes cover every artifact the index
publishes per version, so the locks verify on Linux and Windows
alike. **No previously pinned version changed anywhere** — every
direct pin (tqdm 4.70.1, PyQt6 6.11.0, pytest 9.1.1, PyInstaller
6.22.3, ruff 0.17.0, black 26.10.1, pip 25.3, build 1.3.0) is locked
at exactly its pinned version, identical to a plain install of the
pin files on the same day. Transitives that used to float at install
time are now locked at that same day's resolution — among them
PyQt6-Qt6 6.11.2, PyQt6-sip 13.13.0, packaging 26.3, and (in the
build set) pyinstaller-hooks-contrib 2026.9 and setuptools 84.2.1.

**win32-only stanzas.** pip-compile on Linux silently drops
dependencies whose markers exclude Linux, but Windows installs still
need them with hashes. These stanzas were appended with *every*
artifact hash the index publishes for the version a Windows resolver
picks today, each cross-checked against the downloaded wheel:

* `colorama==0.4.6; sys_platform == "win32"` — in the runtime and
  dev locks (dependency of tqdm / pytest on Windows), the lint lock
  (via click), and the publish lock (via `build`, `os_name == "nt"`).
* `pefile==2024.8.26` and `pywin32-ctypes==0.2.3`, both
  `sys_platform == "win32"` — PyInstaller's Windows dependencies, in
  the build lock.

A plain recompile loses these stanzas — re-append them after
regenerating (this file is the checklist).

## Regenerating after a deliberate bump

1. Edit the pin in the source input file.
2. Re-run the pip-compile command for that input (see the lock's
   header for the exact command line).
3. Re-append the win32-only stanzas listed above that belong to the
   lock, if the compile dropped them.
4. Re-run the acceptance checks below before landing: a clean-venv
   `--require-hashes` install of the lock, the full suite, and a
   one-character tamper test that must fail.

## Verification record (2026-10-25, this rollout)

* Clean venvs: all five locks install with `--require-hashes` —
  runtime 4 packages, dev 9, build 5, lint 8, publish 4 (the publish
  lock upgrading the venv's pip 24.0 → 25.3 under hash verification).
* Test suite: **113 passed** before and after this change (dev-lock
  venv, `QT_QPA_PLATFORM=offscreen`) — unchanged.
* Lint job commands with the hash-installed tools: `ruff check` —
  all checks passed; `black --check` — 22 files unchanged.
* Release path: a venv installed from the runtime + build locks
  built the frozen app (`pyinstaller vectorzip.spec`) and the binary
  passed the CI-style offscreen start smoke (still running after
  12 s).
* Publish path: `python -m build` with the hash-installed publish
  tools built `vectorzip_py-1.2.10.tar.gz` and the wheel.
* Tamper test (scratch copy of `requirements.lock.txt`, one hex
  character corrupted in the PyQt6-Qt6 wheel hash, `--no-cache-dir`):
  the install failed with pip's `THESE PACKAGES DO NOT MATCH THE
  HASHES FROM THE REQUIREMENTS FILE` error, showing the corrupted
  expected hash against the genuine artifact hash. Note: the
  corrupted package must be one with no second usable artifact —
  corrupting only the *wheel* hash of a package that also publishes
  an sdist makes pip fall back to the (still hash-verified) sdist
  instead of failing, which is why wheel-only PyQt6-Qt6 was used.

## Exceptions

* **EX-V1 — build isolation's default backend.** This project
  declares no `[build-system]` table (it builds via `setup.py`), so
  `python -m build` and `pip install .` run build isolation with the
  PEP 518 default backend — current setuptools + wheel, unpinned by
  upstream design and fetched without hash verification. Bounded:
  the publish workflow's own tools (pip, build, and their
  dependencies) are hash-locked in `requirements-publish.lock.txt`,
  and the isolated backend only builds this package's own
  sdist/wheel — it ships no runtime code. Pinning a build backend
  would be a build-configuration change, not a lock.
* **EX-V2 — end-user direct installs.** `pip install .` /
  `pip install .[gui]` resolve `setup.py`'s dependencies straight
  from the index: exact pins (`tqdm==4.70.1`, `PyQt6==6.11.0`) but
  no hashes — a repository lock cannot travel with a package
  install. The README's hash-verified sequence (runtime lock, then
  `pip install --no-deps .`) is the documented reproducible path,
  and every project-controlled install uses the locks.

No lock needed, by construction: the fuzz workflow runs
`tests/fuzz_decompress.py`, which is standard-library only, and the
CodeQL workflow installs no Python packages. The CI `apt-get` Qt
system libraries are distribution packages, verified by the
Debian/Ubuntu archive signatures apt itself enforces — a different,
platform-native verification, not a PyPI hash.
