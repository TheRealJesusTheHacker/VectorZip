"""Regression tests: a planted HARD link at the output path must never
let an overwrite (``--force`` / ``overwrite=True``) clobber the file
sharing the inode.

History: the planted-symlink attack was closed with ``O_NOFOLLOW``,
but hard links have no equivalent open flag, so the overwrite path's
plain ``O_TRUNC`` open still truncated whatever inode the output name
pointed at:

* ``data.txt.vzip`` hard-linked to a victim file -> compressing with
  overwrite destroyed the victim's bytes.
* the restored path hard-linked to the *archive itself* -> decompress
  with overwrite truncated the input while it was being read,
  destroying the archive and producing garbage.

The fix inspects the already-open output fd: a multiply-linked file
is unlinked and replaced with a fresh file at the same path (the
output path still receives the new content; the other link keeps its
bytes), while a singly-linked file is truncated in place exactly as
before. These tests plant real hard links and assert both halves of
that contract, for compress and decompress.
"""

import os
import tempfile
import unittest
from unittest import mock

from src.compressor import compress_file, decompress_file

VICTIM_BYTES = b'PRECIOUS - must never be overwritten'
PAYLOAD = b'hello world ' * 1000


@unittest.skipUnless(hasattr(os, 'link'), 'requires hard link support')
class TestPlantedHardlinkAttack(unittest.TestCase):
    def _victim(self, tmp):
        victim = os.path.join(tmp, 'victim.txt')
        with open(victim, 'wb') as f:
            f.write(VICTIM_BYTES)
        return victim

    def _assert_victim_intact(self, victim):
        with open(victim, 'rb') as f:
            self.assertEqual(f.read(), VICTIM_BYTES)

    def _source(self, tmp, name='data.txt'):
        src = os.path.join(tmp, name)
        with open(src, 'wb') as f:
            f.write(PAYLOAD)
        return src

    def test_compress_overwrite_does_not_clobber_hardlink_victim(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = self._victim(tmp)
            src = self._source(tmp)
            os.link(victim, src + '.vzip')
            out = compress_file(src, overwrite=True)
            self._assert_victim_intact(victim)
            # The output path holds a valid archive of the payload...
            self.assertFalse(os.path.samefile(out, victim))
            restored = decompress_file(out)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), PAYLOAD)

    def test_decompress_overwrite_does_not_clobber_hardlink_victim(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = self._victim(tmp)
            archive = compress_file(self._source(tmp))
            restored = archive[: -len('.vzip')] + '.restored'
            os.link(victim, restored)
            out = decompress_file(archive, overwrite=True)
            self.assertEqual(out, restored)
            self._assert_victim_intact(victim)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), PAYLOAD)

    def test_decompress_output_hardlinked_to_input_preserves_input(self):
        # The nastiest plant: the output name is a second name for the
        # input archive itself. O_TRUNC would destroy the archive
        # mid-read; the fix must leave the archive byte-identical and
        # still produce the restored payload at the output path.
        with tempfile.TemporaryDirectory() as tmp:
            archive = compress_file(self._source(tmp))
            with open(archive, 'rb') as f:
                archive_bytes = f.read()
            restored = archive[: -len('.vzip')] + '.restored'
            os.link(archive, restored)
            out = decompress_file(archive, overwrite=True)
            self.assertEqual(out, restored)
            with open(archive, 'rb') as f:
                self.assertEqual(f.read(), archive_bytes)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), PAYLOAD)

    def test_compress_output_hardlinked_to_input_preserves_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._source(tmp)
            with open(src, 'rb') as f:
                src_bytes = f.read()
            os.link(src, src + '.vzip')
            out = compress_file(src, overwrite=True)
            with open(src, 'rb') as f:
                self.assertEqual(f.read(), src_bytes)
            restored = decompress_file(out)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), PAYLOAD)

    def test_overwrite_singly_linked_file_still_truncates_in_place(self):
        # The legitimate --force path is unchanged for a normal file:
        # same path, new content.
        with tempfile.TemporaryDirectory() as tmp:
            archive = compress_file(self._source(tmp))
            restored = archive[: -len('.vzip')] + '.restored'
            with open(restored, 'wb') as f:
                f.write(b'old contents')
            out = decompress_file(archive, overwrite=True)
            self.assertEqual(out, restored)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), PAYLOAD)


class TestCliQuarantineReplace(unittest.TestCase):
    """The CLI quarantine used os.rename, which refuses to replace an
    existing destination on Windows — a leftover .partial from an
    earlier failed run left the half-written output under its
    good-looking name (the GUI worker got the os.replace fix in the
    previous sweep; the CLI did not). Simulated here by making
    os.rename fail the way it does on Windows."""

    def test_quarantine_replaces_leftover_partial(self):
        import main as cli_main

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'out.vzip')
            with open(path, 'wb') as f:
                f.write(b'half-written')
            with open(path + '.partial', 'wb') as f:
                f.write(b'leftover from an earlier failure')
            with mock.patch('os.rename', side_effect=OSError('destination exists')):
                cli_main._quarantine_partial(path)
            self.assertFalse(os.path.exists(path))
            with open(path + '.partial', 'rb') as f:
                self.assertEqual(f.read(), b'half-written')


if __name__ == '__main__':
    unittest.main()
