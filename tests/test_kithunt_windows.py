"""Kit-hunt (2026-10-20) regression pins for Windows-shaped defects that
the Linux-only test gate could not see:

1. Planted-symlink overwrite on platforms WITHOUT ``os.O_NOFOLLOW``
   (Windows): the overwrite open used ``getattr(os, 'O_NOFOLLOW', 0)``,
   so on Windows there was no flag at all and the write silently
   followed a pre-planted symlink at the output path, clobbering its
   target. Simulated here by patching ``O_NOFOLLOW`` to 0 (its Windows
   value-by-absence) while planting a real symlink.

2. Raw-fd output opens without ``O_BINARY``: every archive byte flows
   through ``os.open`` file descriptors in the engine (fresh-create
   and overwrite) and in the GUI worker's no-clobber move fallback.
   On Windows an fd opened without ``O_BINARY`` is text-mode, the
   exact class that corrupted Argus's vault key on a physical Windows
   test (0x0A written as CRLF). Simulated here by patching a fake
   ``O_BINARY`` value into ``os`` and capturing the flags each
   ``os.open`` is called with.

3. GUI worker signals declared with 32-bit Qt ``int``: byte counts
   past 2 GiB wrap to negative values on the receiving side, so a
   multi-gigabyte job (a headline engine feature) reports negative
   progress and corrupted batch statistics. Proven with a live
   subprocess probe against real PyQt6 — a stub cannot wrap, so this
   test skips when PyQt6 is not installed.
"""

import errno
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

from src.compressor import compress_file, decompress_file

VICTIM_BYTES = b'PRECIOUS - must never be overwritten'
PAYLOAD = b'hello world \n' * 1000  # newline-rich: text-mode poison


def _load_gui_module():
    if 'gui.main_window' in sys.modules:
        return sys.modules['gui.main_window']
    if 'PyQt6' not in sys.modules:
        import types

        m = types.ModuleType('PyQt6')
        core = types.ModuleType('PyQt6.QtCore')
        gui_ = types.ModuleType('PyQt6.QtGui')
        widgets = types.ModuleType('PyQt6.QtWidgets')

        class _Signal:
            def __init__(self, *a, **k):
                self._slots = []

            def connect(self, slot):
                self._slots.append(slot)

            def emit(self, *a, **k):
                for s in list(self._slots):
                    s(*a, **k)

        class _QObject:
            def __init__(self, *a, **k):
                pass

            def moveToThread(self, *a, **k):
                pass

            def deleteLater(self):
                pass

        core.pyqtSignal = _Signal
        core.QObject = _QObject
        widgets.QMainWindow = type('QMainWindow', (_QObject,), {})
        m.QtCore, m.QtGui, m.QtWidgets = core, gui_, widgets
        sys.modules['PyQt6'] = m
        sys.modules['PyQt6.QtCore'] = core
        sys.modules['PyQt6.QtGui'] = gui_
        sys.modules['PyQt6.QtWidgets'] = widgets
    from gui import main_window

    return main_window


@unittest.skipUnless(hasattr(os, 'symlink'), 'requires symlink creation')
class TestSymlinkOverwriteWithoutNofollow(unittest.TestCase):
    """Windows shape: no O_NOFOLLOW, so the flag contributes 0."""

    def _victim(self, tmp):
        victim = os.path.join(tmp, 'victim.txt')
        with open(victim, 'wb') as f:
            f.write(VICTIM_BYTES)
        return victim

    def _archive(self, tmp):
        src = os.path.join(tmp, 'data.txt')
        with open(src, 'wb') as f:
            f.write(PAYLOAD)
        return src, compress_file(src)

    def test_decompress_overwrite_refuses_symlink_without_nofollow(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = self._victim(tmp)
            _src, archive = self._archive(tmp)
            restored = archive[: -len('.vzip')] + '.restored'
            os.symlink(victim, restored)
            with mock.patch.object(os, 'O_NOFOLLOW', 0, create=True):
                with self.assertRaises(OSError) as cm:
                    decompress_file(archive, overwrite=True)
            self.assertEqual(cm.exception.errno, errno.ELOOP)
            with open(victim, 'rb') as f:
                self.assertEqual(f.read(), VICTIM_BYTES)
            self.assertTrue(os.path.islink(restored))

    def test_compress_overwrite_refuses_symlink_without_nofollow(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = self._victim(tmp)
            src = os.path.join(tmp, 'evil.txt')
            with open(src, 'wb') as f:
                f.write(PAYLOAD)
            os.symlink(victim, src + '.vzip')
            with mock.patch.object(os, 'O_NOFOLLOW', 0, create=True):
                with self.assertRaises(OSError) as cm:
                    compress_file(src, overwrite=True)
            self.assertEqual(cm.exception.errno, errno.ELOOP)
            with open(victim, 'rb') as f:
                self.assertEqual(f.read(), VICTIM_BYTES)
            self.assertTrue(os.path.islink(src + '.vzip'))

    def test_decompress_overwrite_refuses_dangling_symlink_without_nofollow(self):
        with tempfile.TemporaryDirectory() as tmp:
            _src, archive = self._archive(tmp)
            restored = archive[: -len('.vzip')] + '.restored'
            target = os.path.join(tmp, 'not-yet-created.txt')
            os.symlink(target, restored)
            with mock.patch.object(os, 'O_NOFOLLOW', 0, create=True):
                with self.assertRaises(OSError) as cm:
                    decompress_file(archive, overwrite=True)
            self.assertEqual(cm.exception.errno, errno.ELOOP)
            self.assertFalse(os.path.exists(target))


_FAKE_BINARY = 1 << 30  # stand-in for Windows O_BINARY; stripped before real opens


class _FlagCapture:
    """Patch os.open, recording flags and stripping the fake binary bit."""

    def __init__(self):
        self.seen = []
        self._real_open = os.open

    def __call__(self, path, flags, *a, **k):
        self.seen.append(flags)
        return self._real_open(path, flags & ~_FAKE_BINARY, *a, **k)

    def assert_binary_seen(self, test):
        test.assertTrue(self.seen, 'no os.open call was captured')
        for flags in self.seen:
            test.assertTrue(
                flags & _FAKE_BINARY,
                'os.open called without O_BINARY (flags=%#x)' % flags,
            )


class TestBinaryModeFlags(unittest.TestCase):
    def test_compress_output_open_requests_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'data.bin')
            with open(src, 'wb') as f:
                f.write(PAYLOAD)
            cap = _FlagCapture()
            with mock.patch.object(os, 'O_BINARY', _FAKE_BINARY, create=True):
                with mock.patch.object(os, 'open', cap):
                    out = compress_file(src)
            cap.assert_binary_seen(self)
            restored = decompress_file(out)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), PAYLOAD)

    def test_decompress_overwrite_open_requests_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'data.bin')
            with open(src, 'wb') as f:
                f.write(PAYLOAD)
            archive = compress_file(src)
            restored = archive[: -len('.vzip')] + '.restored'
            with open(restored, 'wb') as f:
                f.write(b'old contents')
            cap = _FlagCapture()
            with mock.patch.object(os, 'O_BINARY', _FAKE_BINARY, create=True):
                with mock.patch.object(os, 'open', cap):
                    decompress_file(archive, overwrite=True)
            cap.assert_binary_seen(self)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), PAYLOAD)

    def test_gui_move_fallback_copy_requests_binary(self):
        g = _load_gui_module()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 's.vzip')
            dest = os.path.join(tmp, 'd.vzip')
            with open(src, 'wb') as f:
                f.write(PAYLOAD)
            cap = _FlagCapture()
            with mock.patch.object(os, 'O_BINARY', _FAKE_BINARY, create=True):
                with mock.patch.object(os, 'open', cap):
                    # Force the fallback: hard links unavailable (cross-volume).
                    with mock.patch.object(
                        os, 'link', side_effect=OSError(errno.EXDEV, 'cross-device')
                    ):
                        g._move_noclobber(src, dest, False)
            cap.assert_binary_seen(self)
            with open(dest, 'rb') as f:
                self.assertEqual(f.read(), PAYLOAD)
            self.assertFalse(os.path.exists(src))


_LIVE_SIGNAL_PROBE = textwrap.dedent('''
    import os, sys
    try:
        from PyQt6 import QtCore
        sys.path.insert(0, os.getcwd())
        from gui.main_window import JobWorker
    except ImportError:
        # PyQt6 absent, or its system libraries (libEGL etc.) missing:
        # the probe cannot run here — skip rather than false-fail.
        sys.exit(42)

    app = QtCore.QCoreApplication(sys.argv)
    worker = JobWorker([], 'compress', None, False)
    got = {}
    worker.progress.connect(lambda d, t, label: got.update(progress=(d, t)))
    worker.file_done.connect(
        lambda p, ok, detail, i, o: got.update(file_done=(i, o))
    )
    worker.progress.emit(3000000000, 4000000000, 'big.bin')
    worker.file_done.emit('big.bin', True, 'done', 3000000000, 5000000000)
    assert got.get('progress') == (3000000000, 4000000000), got
    assert got.get('file_done') == (3000000000, 5000000000), got
    print('signal widths OK', got)
    ''')


class TestGuiSignalWidthsLive(unittest.TestCase):
    def test_worker_signals_carry_64_bit_byte_counts(self):
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        proc = subprocess.run(
            [sys.executable, '-c', _LIVE_SIGNAL_PROBE],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode == 42:
            self.skipTest('PyQt6 not installed in this interpreter')
        self.assertEqual(
            proc.returncode,
            0,
            'live signal probe failed:\n%s\n%s' % (proc.stdout, proc.stderr),
        )


if __name__ == '__main__':
    unittest.main()
