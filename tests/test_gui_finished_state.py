"""GUI completion-state honesty (sweep 2026-10-21).

Two shipped misreports in the desktop app:

1. A cancelled batch still landed on the "Finished" state — the
   progress bar jumped to 100% and the label said "Finished in …"
   even when the user had cancelled and little or nothing ran.
   Completion after a cancel request must read as cancelled and
   must not claim a full bar.

2. When a finished file could not be moved into the chosen output
   folder because a file with that name already existed there, the
   worker reported a bare "Output exists" — unlike every other
   move failure, it never said the finished file was kept, or
   where. The refusal now names the kept location.

The probes run in a subprocess with real PyQt6 (the same pattern
as tests/test_kithunt_windows.py's signal-width probe): importing
PyQt6 in this process would defeat the PyQt6 stub that
tests/test_audit2_concurrency.py loads gui.main_window with, and
a stub cannot prove widget state anyway. Skips when PyQt6 is not
installed.
"""

import os
import subprocess
import sys
import textwrap
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")

_PROBE = textwrap.dedent(
    """
    import os, sys, time
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, {root!r})
    from PyQt6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from gui.main_window import VectorZipWindow, JobWorker

    mode = sys.argv[1]
    if mode == "cancelled":
        win = VectorZipWindow()
        win.bar.setValue(37)
        win._start_time = time.time() - 2
        win._cancel_requested = True
        win._on_finished()
        assert "Cancelled" in win.prog_label.text(), win.prog_label.text()
        assert win.bar.value() != 100, win.bar.value()
        win.close()
    elif mode == "completed":
        win = VectorZipWindow()
        win.bar.setValue(37)
        win._start_time = time.time() - 2
        win._cancel_requested = False
        win._on_finished()
        assert "Finished" in win.prog_label.text(), win.prog_label.text()
        assert win.bar.value() == 100, win.bar.value()
        win.close()
    elif mode == "move-refusal":
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "data.txt")
            with open(src, "wb") as fh:
                fh.write(b"hello world " * 100)
            out_dir = os.path.join(td, "out")
            os.mkdir(out_dir)
            with open(os.path.join(out_dir, "data.txt.vzip"), "wb") as fh:
                fh.write(b"someone else's file")
            events = []
            worker = JobWorker([src], "compress", out_dir, False)
            worker.file_done.connect(lambda *a: events.append(a))
            worker.run()
            assert len(events) == 1, events
            _path, ok, detail, _in, _out = events[0]
            assert not ok, events
            assert "kept at" in detail, detail
            assert (src + ".vzip") in detail, detail
            assert os.path.exists(src + ".vzip")
    print("PROBE OK")
    """
)


def _qt_available():
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import PyQt6"],
            capture_output=True,
            timeout=60,
        )
        return r.returncode == 0
    except Exception:
        return False


@unittest.skipUnless(_qt_available(), "PyQt6 not installed")
class TestFinishedState(unittest.TestCase):
    def _probe(self, mode):
        code = _PROBE.format(root=os.path.abspath(REPO_ROOT))
        r = subprocess.run(
            [sys.executable, "-c", code, mode],
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PROBE OK", r.stdout)

    def test_cancelled_batch_does_not_report_finished_100(self):
        self._probe("cancelled")

    def test_completed_batch_still_reports_finished_100(self):
        self._probe("completed")

    def test_move_refusal_says_where_the_finished_file_was_kept(self):
        self._probe("move-refusal")


if __name__ == "__main__":
    unittest.main()
