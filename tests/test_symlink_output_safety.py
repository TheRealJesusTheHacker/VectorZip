"""Regression tests: a planted symlink at the output path must never be
followed — on either the fresh-create path or the overwrite path.

History: the no-overwrite path always used O_CREAT|O_EXCL|O_NOFOLLOW,
but the overwrite path (--force / GUI overwrite) used a plain
``open(path, 'wb')``, so a pre-planted symlink at the output path
redirected the write and silently clobbered the link's target —
an arbitrary-file-overwrite primitive for anyone who can plant a
symlink in the output directory. The fix routes overwrite opens
through O_NOFOLLOW|O_TRUNC as well and raises a clear ELOOP error.

These tests reproduce the planted-symlink attack for both compress
and decompress, in both modes, and assert the victim file is never
touched. POSIX-only: they rely on os.O_NOFOLLOW and symlink creation.
"""

import errno
import os
import tempfile
import unittest

from src.compressor import compress_file, decompress_file

VICTIM_BYTES = b'PRECIOUS - must never be overwritten'


@unittest.skipUnless(
    hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'symlink'),
    'requires POSIX O_NOFOLLOW and symlink support',
)
class TestPlantedSymlinkAttack(unittest.TestCase):
    def _victim(self, tmp):
        victim = os.path.join(tmp, 'victim.txt')
        with open(victim, 'wb') as f:
            f.write(VICTIM_BYTES)
        return victim

    def _assert_victim_intact(self, victim):
        with open(victim, 'rb') as f:
            self.assertEqual(f.read(), VICTIM_BYTES)

    def _archive(self, tmp):
        src = os.path.join(tmp, 'data.txt')
        with open(src, 'wb') as f:
            f.write(b'hello world ' * 1000)
        return src, compress_file(src)

    def test_decompress_overwrite_refuses_planted_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = self._victim(tmp)
            _src, archive = self._archive(tmp)
            restored = archive[: -len('.vzip')] + '.restored'
            os.symlink(victim, restored)
            with self.assertRaises(OSError) as cm:
                decompress_file(archive, overwrite=True)
            self.assertEqual(cm.exception.errno, errno.ELOOP)
            self._assert_victim_intact(victim)
            self.assertTrue(os.path.islink(restored))

    def test_compress_overwrite_refuses_planted_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = self._victim(tmp)
            src = os.path.join(tmp, 'evil.txt')
            with open(src, 'wb') as f:
                f.write(b'x' * 5000)
            os.symlink(victim, src + '.vzip')
            with self.assertRaises(OSError) as cm:
                compress_file(src, overwrite=True)
            self.assertEqual(cm.exception.errno, errno.ELOOP)
            self._assert_victim_intact(victim)
            self.assertTrue(os.path.islink(src + '.vzip'))

    def test_overwrite_refuses_dangling_symlink(self):
        # A symlink whose target does not exist yet: following it would
        # CREATE the target file. That must be refused too.
        with tempfile.TemporaryDirectory() as tmp:
            _src, archive = self._archive(tmp)
            restored = archive[: -len('.vzip')] + '.restored'
            target = os.path.join(tmp, 'not-yet-created.txt')
            os.symlink(target, restored)
            with self.assertRaises(OSError) as cm:
                decompress_file(archive, overwrite=True)
            self.assertEqual(cm.exception.errno, errno.ELOOP)
            self.assertFalse(os.path.exists(target))

    def test_no_overwrite_refuses_planted_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = self._victim(tmp)
            _src, archive = self._archive(tmp)
            restored = archive[: -len('.vzip')] + '.restored'
            os.symlink(victim, restored)
            with self.assertRaises(FileExistsError):
                decompress_file(archive)
            self._assert_victim_intact(victim)
            self.assertTrue(os.path.islink(restored))

    def test_overwrite_real_file_still_works(self):
        # The fix must not break the legitimate --force path: a real
        # file at the output path is clobbered as before.
        with tempfile.TemporaryDirectory() as tmp:
            src, archive = self._archive(tmp)
            restored = archive[: -len('.vzip')] + '.restored'
            with open(restored, 'wb') as f:
                f.write(b'old contents')
            out = decompress_file(archive, overwrite=True)
            self.assertEqual(out, restored)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), b'hello world ' * 1000)
            self.assertFalse(os.path.islink(restored))


if __name__ == '__main__':
    unittest.main()
