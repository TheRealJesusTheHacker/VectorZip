"""Pass-2 audit tests: concurrency & edge-case fixes.

Covers: torn-input detection on compress, unknown chunk-flag rejection,
CLI/GUI quarantine semantics on overwrite refusal, the GUI worker's atomic
no-clobber move, batch duplicate-output planning, and cancel-mid-job.

The GUI tests import ``gui.main_window`` with a minimal PyQt6 stub, because
the worker and the filesystem helpers under test never touch a widget —
only ``QtCore.QObject`` / ``pyqtSignal``.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

from src.compressor import compress_file, decompress_file
from src import compressor


def _load_gui_module():
    import types

    if 'PyQt6' not in sys.modules:
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


class TestTornInputDetection(unittest.TestCase):
    def test_compress_rejects_torn_input(self):
        # Simulate the input changing mid-job: the fingerprint taken after
        # the write no longer matches, so compress must fail loudly instead
        # of handing back a torn archive that looks complete.
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'input.bin')
            with open(src, 'wb') as f:
                f.write(b'torn input test data. ' * 5000)
            real = compressor._input_fingerprint(src)
            forged = (real[0], real[1], real[2] + 1)  # mtime moved mid-job
            with mock.patch.object(compressor, '_input_fingerprint', side_effect=[real, forged]):
                with self.assertRaises(IOError):
                    compressor.compress_file(src)
            # The torn archive is left for the caller to quarantine through
            # its normal failure path (CLI/GUI), not silently deleted.
            self.assertTrue(os.path.exists(src + '.vzip'))
            self.assertFalse(os.path.exists(src + '.vzip.partial'))

    def test_compress_stable_input_still_works(self):
        # The fingerprint check must not false-positive on a quiet file.
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'input.bin')
            data = b'stable input. ' * 20000
            with open(src, 'wb') as f:
                f.write(data)
            vp = compress_file(src)
            restored = decompress_file(vp)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), data)


class TestUnknownChunkFlags(unittest.TestCase):
    def _archive_with_flags(self, tmp, name, magic, flags):
        import struct

        vp = os.path.join(tmp, name)
        with open(vp, 'wb') as f:
            f.write(magic)
            f.write(struct.pack('>IHBB', 0, 0, 0, flags))
        return vp

    def test_v3_unknown_data_flags_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            vp = self._archive_with_flags(tmp, 'f.vzip', b'VZP3', 0x40)
            with self.assertRaises(ValueError):
                decompress_file(vp)

    def test_v3_end_marker_with_unknown_flags_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            vp = self._archive_with_flags(tmp, 'f.vzip', b'VZP3', 0xC0)
            with self.assertRaises(ValueError):
                decompress_file(vp)

    def test_v2_end_bit_rejected(self):
        # v2 never had an END marker: 0x80 there is a foreign flag.
        with tempfile.TemporaryDirectory() as tmp:
            vp = self._archive_with_flags(tmp, 'f.vzip', b'VZP2', 0x80)
            with self.assertRaises(ValueError):
                decompress_file(vp)

    def test_v2_unknown_data_flags_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            vp = self._archive_with_flags(tmp, 'f.vzip', b'VZP2', 0x40)
            with self.assertRaises(ValueError):
                decompress_file(vp)


class TestCliQuarantineSemantics(unittest.TestCase):
    def _run_cli(self, argv):
        import main as cli

        with mock.patch.object(sys, 'argv', argv):
            with self.assertRaises(SystemExit) as cm:
                cli.main()
        return cm.exception.code

    def test_refusal_leaves_existing_output_alone(self):
        # Overwrite refusal must NOT quarantine: the pre-existing output
        # was never touched, so renaming it to .partial would destroy a
        # good file.
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'data.bin')
            with open(src, 'wb') as f:
                f.write(b'data' * 1000)
            vp = compress_file(src)
            restored = vp[: -len('.vzip')] + '.restored'
            with open(restored, 'wb') as f:
                f.write(b'PRIOR GOOD OUTPUT')
            code = self._run_cli(['vzip', 'decompress', vp])
            self.assertEqual(code, 1)
            with open(restored, 'rb') as f:
                self.assertEqual(f.read(), b'PRIOR GOOD OUTPUT')
            self.assertFalse(os.path.exists(restored + '.partial'))

    def test_real_failure_still_quarantines(self):
        # A genuine mid-write failure must still quarantine the partial.
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'data.bin')
            with open(src, 'wb') as f:
                f.write(b'quarantine me ' * 5000)
            vp = compress_file(src)
            with open(vp, 'rb') as f:
                blob = f.read()
            cut = os.path.join(tmp, 'cut.vzip')
            with open(cut, 'wb') as f:
                f.write(blob[:-8])  # strip the END marker: fails after writing
            expected = cut[: -len('.vzip')] + '.restored'
            code = self._run_cli(['vzip', 'decompress', cut])
            self.assertEqual(code, 1)
            self.assertFalse(os.path.exists(expected))
            self.assertTrue(os.path.exists(expected + '.partial'))


class TestGuiWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load_gui_module()

    def _run_worker(self, jobs, mode, out_dir, overwrite):
        g = self.g
        w = g.JobWorker(jobs, mode, out_dir, overwrite)
        for sig in (w.progress, w.file_done, w.finished):
            sig._slots.clear()  # stub signals are class-level: isolate tests
        events = []
        w.file_done.connect(lambda p, ok, det, i, o: events.append((p, ok, det)))
        finished = []
        w.finished.connect(lambda: finished.append(True))
        w.run()
        self.assertTrue(finished)
        return events

    def _two_same_name(self, tmp):
        d1 = os.path.join(tmp, 'd1')
        d2 = os.path.join(tmp, 'd2')
        out = os.path.join(tmp, 'out')
        os.makedirs(d1)
        os.makedirs(d2)
        os.makedirs(out)
        p1 = os.path.join(d1, 'a.txt')
        p2 = os.path.join(d2, 'a.txt')
        with open(p1, 'wb') as f:
            f.write(b'one' * 1000)
        with open(p2, 'wb') as f:
            f.write(b'two' * 1000)
        return p1, p2, out

    def test_expected_output_probe(self):
        g = self.g
        self.assertEqual(g._expected_output('/x/a.txt', 'compress'), '/x/a.txt.vzip')
        self.assertEqual(g._expected_output('/x/a.txt.vzip', 'decompress'), '/x/a.txt.restored')
        self.assertEqual(g._expected_output('/x/a.dat', 'decompress'), '/x/a.dat.restored')

    def test_plan_jobs_duplicate_basename(self):
        g = self.g
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, out = self._two_same_name(tmp)
            run, skipped = g._plan_jobs([p1, p2], 'compress', out, False)
            self.assertEqual(run, [p1])
            self.assertEqual(skipped, [(p2, 'Duplicate output in batch')])

    def test_plan_jobs_existing_output(self):
        g = self.g
        with tempfile.TemporaryDirectory() as tmp:
            p1, _, out = self._two_same_name(tmp)
            with open(os.path.join(out, 'a.txt.vzip'), 'wb') as f:
                f.write(b'x')
            run, skipped = g._plan_jobs([p1], 'compress', out, False)
            self.assertEqual(run, [])
            self.assertEqual(skipped, [(p1, 'Output exists')])
            run, skipped = g._plan_jobs([p1], 'compress', out, True)
            self.assertEqual(run, [p1])
            self.assertEqual(skipped, [])

    def test_plan_jobs_no_outdir_distinct_dirs(self):
        # Same basename but no shared out_dir: different destinations, no clash.
        g = self.g
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, _ = self._two_same_name(tmp)
            run, skipped = g._plan_jobs([p1, p2], 'compress', None, False)
            self.assertEqual(run, [p1, p2])
            self.assertEqual(skipped, [])

    def test_move_noclobber(self):
        g = self.g
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = os.path.join(tmp, 'd')
            os.makedirs(dest_dir)
            src = os.path.join(tmp, 's.vzip')
            dest = os.path.join(dest_dir, 's.vzip')
            with open(src, 'wb') as f:
                f.write(b'data')
            g._move_noclobber(src, dest, False)
            self.assertFalse(os.path.exists(src))
            with open(dest, 'rb') as f:
                self.assertEqual(f.read(), b'data')
            # Refusal is atomic: the racy file is untouched, source kept.
            src2 = os.path.join(tmp, 's2.vzip')
            with open(src2, 'wb') as f:
                f.write(b'new')
            with self.assertRaises(FileExistsError):
                g._move_noclobber(src2, dest, False)
            with open(dest, 'rb') as f:
                self.assertEqual(f.read(), b'data')
            self.assertTrue(os.path.exists(src2))
            # overwrite=True replaces atomically.
            g._move_noclobber(src2, dest, True)
            with open(dest, 'rb') as f:
                self.assertEqual(f.read(), b'new')
            self.assertFalse(os.path.exists(src2))

    def test_worker_refusal_does_not_quarantine(self):
        # Same-basename batch, shared out_dir, no overwrite: job1 delivers,
        # job2 is refused — and must NOT quarantine job1's good output.
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2, out = self._two_same_name(tmp)
            events = self._run_worker([p1, p2], 'compress', out, False)
            self.assertEqual(len(events), 2)
            self.assertTrue(events[0][1])  # job1 ok
            self.assertFalse(events[1][1])  # job2 refused
            good = os.path.join(out, 'a.txt.vzip')
            self.assertTrue(os.path.exists(good))  # job1's output intact...
            self.assertFalse(os.path.exists(good + '.partial'))  # ...not quarantined
            # job2's own complete output stays put (it is complete, not partial)
            own = os.path.join(os.path.dirname(p2), 'a.txt.vzip')
            self.assertTrue(os.path.exists(own))
            self.assertFalse(os.path.exists(own + '.partial'))

    def test_worker_corrupt_job_quarantines(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'in.bin')
            with open(src, 'wb') as f:
                f.write(b'quarantine me ' * 5000)
            vp = compress_file(src)
            with open(vp, 'rb') as f:
                blob = f.read()
            cut = os.path.join(tmp, 'cut.vzip')
            with open(cut, 'wb') as f:
                f.write(blob[:-8])  # strip END marker: fails after writing
            events = self._run_worker([cut], 'decompress', None, False)
            self.assertEqual(len(events), 1)
            self.assertFalse(events[0][1])
            self.assertFalse(os.path.exists(cut[: -len('.vzip')] + '.restored'))
            self.assertTrue(os.path.exists(cut[: -len('.vzip')] + '.restored.partial'))

    def test_worker_cancel_mid_job(self):
        g = self.g
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'big.bin')
            with open(src, 'wb') as f:
                f.write(os.urandom(300000))  # multi-chunk: progress fires
            w = g.JobWorker([src], 'compress', None, False)
            for sig in (w.progress, w.file_done, w.finished):
                sig._slots.clear()
            events = []
            w.file_done.connect(lambda p, ok, det, i, o: events.append((ok, det)))
            finished = []
            w.finished.connect(lambda: finished.append(True))
            orig_cb = w._progress_cb

            def cancelling_cb(label):
                inner = orig_cb(label)

                def _cb(done, total):
                    w.cancelled = True
                    return inner(done, total)

                return _cb

            w._progress_cb = cancelling_cb
            w.run()
            self.assertTrue(finished)
            self.assertEqual(events, [(False, 'Cancelled')])
            self.assertFalse(os.path.exists(src + '.vzip'))
            self.assertTrue(os.path.exists(src + '.vzip.partial'))


if __name__ == '__main__':
    unittest.main()
