## What this changes

## Why

## How it was verified

- [ ] `python -m pytest tests/ -q` — all 34 tests pass
- [ ] `ruff check src main.py gui_launcher.py gui tests` — clean
- [ ] `black --check --skip-string-normalization -l 100 src main.py gui_launcher.py gui tests` — clean
- [ ] CLI round-trip: `python main.py compress` then `python main.py decompress`, outputs byte-identical

## Compatibility notes

Does this change the `.vzip` format, the CLI flags, or the library API
(`compress_file`/`decompress_file`)? If yes, describe the impact on
existing archives and callers. Legacy format v1/v2 files must still
decompress.

## Checklist

- [ ] No feature was stripped or neutered; no function signatures or CLI contracts changed
- [ ] `==` pins in `setup.py` / `requirements.txt` are untouched
- [ ] Security-sensitive paths (overwrite handling, output caps, chunk parsing) got a second look
- [ ] CHANGELOG.md updated if this is a user-facing change
