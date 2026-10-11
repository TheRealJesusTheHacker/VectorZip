"""VectorZip desktop GUI — sleek, modern, professional.

Batch compress/decompress with drag-and-drop, live progress,
per-file statistics and a color-coded activity log.
"""

import errno
import os
import shutil
import sys
import time
import html
import traceback

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from vectorzip.compressor import compress_file, decompress_file
    from vectorzip import __version__
except ImportError:  # running from the repo root
    from src.compressor import compress_file, decompress_file
    from src import __version__

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

BG = "#0f141b"
PANEL = "#161d27"
PANEL_LIGHT = "#1c2431"
BORDER = "#2a3444"
TEXT = "#e8eef5"
TEXT_DIM = "#93a1b5"
ACCENT = "#38bdf8"  # electric cyan
ACCENT_DARK = "#0e7490"
SUCCESS = "#4ade80"
WARNING = "#fbbf24"
ERROR = "#f87171"
MONO = "Consolas, 'SF Mono', Menlo, monospace"

STYLESHEET = f"""
* {{ font-family: 'Segoe UI', 'Inter', system-ui, sans-serif; }}
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}
QMainWindow::separator {{ background: {BORDER}; }}

/* Header */
#brand {{ font-size: 22px; font-weight: 800; letter-spacing: 0.5px; }}
#brandAccent {{ color: {ACCENT}; }}
#tagline {{ color: {TEXT_DIM}; font-size: 12px; }}
#versionBadge {{
    background: {PANEL_LIGHT}; color: {ACCENT};
    border: 1px solid {BORDER}; border-radius: 10px;
    padding: 3px 10px; font-size: 11px; font-weight: 600;
}}

/* Section cards */
QGroupBox {{
    background: {PANEL}; border: 1px solid {BORDER};
    border-radius: 10px; margin-top: 14px; padding-top: 8px;
    font-weight: 700; font-size: 12px; color: {TEXT_DIM};
    text-transform: uppercase; letter-spacing: 1px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}

/* Buttons */
QPushButton {{
    background: {PANEL_LIGHT}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 16px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #232d3d; }}
QPushButton:disabled {{ color: #5b6a7e; border-color: #232d3d; }}
#primaryBtn {{
    background: {ACCENT}; color: #06202b; border: none;
    font-size: 14px; padding: 10px 22px;
}}
#primaryBtn:hover {{ background: #7dd3fc; }}
#primaryBtn:disabled {{ background: #274b5c; color: #7b8fa3; }}
#dangerBtn {{ border-color: #5c2b2b; color: {ERROR}; }}
#dangerBtn:hover {{ background: #3a1d1d; border-color: {ERROR}; }}

/* Inputs */
QLineEdit, QComboBox {{
    background: {PANEL_LIGHT}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 7px 10px; color: {TEXT};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {PANEL_LIGHT}; selection-background: {ACCENT_DARK}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {BORDER}; background: {PANEL_LIGHT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* Queue table */
QTableWidget {{
    background: {PANEL}; border: 1px solid {BORDER};
    border-radius: 10px; gridline-color: {BORDER};
    alternate-background-color: #131924; selection-background: #1e3a4c;
}}
QTableWidget::item {{ padding: 6px; }}
QHeaderView::section {{
    background: {PANEL_LIGHT}; color: {TEXT_DIM}; border: none;
    padding: 8px; font-weight: 700; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.8px;
}}

/* Drop zone */
#dropZone {{
    border: 2px dashed #33506a; border-radius: 10px;
    color: {TEXT_DIM}; font-size: 13px; padding: 18px;
}}
#dropZone[dragOver="true"] {{ border-color: {ACCENT}; color: {ACCENT}; background: #12222e; }}

/* Progress */
QProgressBar {{
    background: {PANEL_LIGHT}; border: 1px solid {BORDER};
    border-radius: 8px; height: 22px; text-align: center; color: {TEXT};
}}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_DARK}, stop:1 {ACCENT}); border-radius: 7px; }}

/* Stat cards */
#statCard {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
#statValue {{ font-size: 20px; font-weight: 800; color: {TEXT}; }}
#statValueAccent {{ font-size: 20px; font-weight: 800; color: {ACCENT}; }}
#statLabel {{ font-size: 10px; color: {TEXT_DIM}; text-transform: uppercase; letter-spacing: 1px; }}

/* Log */
QPlainTextEdit {{
    background: #0b0f15; border: 1px solid {BORDER};
    border-radius: 10px; font-family: {MONO}; font-size: 12px;
    padding: 8px;
}}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 10px; background: {PANEL}; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_DIM};
    padding: 8px 18px; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QStatusBar {{ color: {TEXT_DIM}; font-size: 11px; }}
"""


def fmt_bytes(num):
    """Human-readable byte count."""
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


# ---------------------------------------------------------------------------
# Filesystem helpers (shared by the worker and the pre-flight planner)
# ---------------------------------------------------------------------------


def _expected_output(path, mode):
    """Where compress/decompress writes its output for ``path``.

    Single source of truth for the worker, the quarantine logic, and the
    pre-flight planner — mirrors compress_file/decompress_file naming
    exactly.
    """
    if mode == 'compress':
        return path + '.vzip'
    if path.endswith('.vzip'):
        return path[: -len('.vzip')] + '.restored'
    return path + '.restored'


def _move_noclobber(src, dest, overwrite):
    """Move ``src`` to ``dest``.

    With ``overwrite=False`` the refusal is atomic: the destination is
    claimed with a hard link (an ``O_EXCL``-claimed copy across
    filesystems), so no check-then-move race can silently replace a file
    that appeared in between. With ``overwrite=True`` the replacement is
    a single atomic ``os.replace`` (which, unlike ``os.rename``, also
    replaces on Windows). A symlink at ``dest`` is never followed.
    """
    if os.path.isdir(dest) and not os.path.islink(dest):
        raise IsADirectoryError(f'output destination is a directory: {dest}')
    if overwrite:
        os.replace(src, dest)
        return
    try:
        os.link(src, dest)
    except OSError as e:
        if e.errno == errno.EEXIST:
            raise FileExistsError(f'output exists: {os.path.basename(dest)}')
        if e.errno != errno.EXDEV:
            raise
        # Cross-filesystem: claim dest atomically, then copy into it.
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            with os.fdopen(fd, 'wb') as fout, open(src, 'rb') as fin:
                shutil.copyfileobj(fin, fout)
        except BaseException:
            try:
                os.unlink(dest)
            except OSError:
                pass
            raise
        os.unlink(src)
        return
    os.unlink(src)


def _plan_jobs(jobs, mode, out_dir, overwrite):
    """Pre-flight planner: which jobs to run, which to skip and why.

    Returns ``(run, skipped)`` where ``skipped`` is a list of
    ``(path, reason)``. A job is skipped when its planned output already
    exists (unless ``overwrite``) or when its output name collides with
    another job in the same batch — otherwise a later job would silently
    replace an earlier job's good output (or, on refusal, quarantine it).
    Pure function: no Qt involved, fully unit-testable.
    """
    run, skipped = [], []
    seen = set()
    for p in jobs:
        dest_dir = out_dir or os.path.dirname(os.path.abspath(p))
        dest_path = os.path.join(dest_dir, os.path.basename(_expected_output(p, mode)))
        key = os.path.normcase(os.path.normpath(dest_path))
        if os.path.lexists(dest_path) and not overwrite:
            skipped.append((p, 'Output exists'))
            continue
        if key in seen:
            skipped.append((p, 'Duplicate output in batch'))
            continue
        seen.add(key)
        run.append(p)
    return run, skipped


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


class JobWorker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int, str)  # done, total, label
    file_done = QtCore.pyqtSignal(str, bool, str, int, int)  # path, ok, detail, in_size, out_size
    finished = QtCore.pyqtSignal()

    def __init__(self, jobs, mode, out_dir, overwrite):
        super().__init__()
        self.jobs = jobs
        self.mode = mode
        self.out_dir = out_dir
        self.overwrite = overwrite
        self.cancelled = False

    def _progress_cb(self, label):
        last = {"done": 0}

        def _cb(done, total):
            if self.cancelled:
                raise InterruptedError("cancelled")
            last["done"] = done
            self.progress.emit(done, total, label)

        return _cb

    def _quarantine_partial(self, path):
        """Rename a half-written output to .partial so a cancelled or
        OOM-killed job can't leave something that looks like a good result."""
        partial = _expected_output(path, self.mode)
        if os.path.exists(partial):
            try:
                os.rename(partial, partial + ".partial")
            except OSError:
                pass

    def run(self):
        try:
            for path in self.jobs:
                if self.cancelled:
                    break
                label = os.path.basename(path)
                try:
                    in_size = os.path.getsize(path)
                    func = compress_file if self.mode == "compress" else decompress_file
                    out = func(path, progress=self._progress_cb(label), overwrite=self.overwrite)
                    if self.out_dir and os.path.dirname(os.path.abspath(out)) != os.path.abspath(
                        self.out_dir
                    ):
                        dest = os.path.join(self.out_dir, os.path.basename(out))
                        _move_noclobber(out, dest, self.overwrite)
                        out = dest
                    out_size = os.path.getsize(out)
                    detail = f"{fmt_bytes(in_size)} → {fmt_bytes(out_size)}"
                    self.file_done.emit(path, True, detail, in_size, out_size)
                except InterruptedError:
                    self._quarantine_partial(path)
                    self.file_done.emit(path, False, "Cancelled", 0, 0)
                    break
                except MemoryError:
                    # MemoryError inherits BaseException, not Exception —
                    # without this the worker thread dies on a raw traceback.
                    self._quarantine_partial(path)
                    self.file_done.emit(path, False, "Out of memory — file may be corrupt", 0, 0)
                except FileExistsError:
                    # Overwrite refusal, not a mid-write failure: the
                    # existing output was never touched, so there is
                    # nothing to quarantine.
                    self.file_done.emit(path, False, "Output exists (not overwritten)", 0, 0)
                except Exception:
                    # A corrupt archive fails mid-write: quarantine the
                    # half-written output so it can't look like a good result.
                    self._quarantine_partial(path)
                    self.file_done.emit(
                        path, False, traceback.format_exc(limit=1).strip().splitlines()[-1], 0, 0
                    )
        finally:
            self.finished.emit()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class VectorZipWindow(QtWidgets.QMainWindow):
    COL_FILE, COL_SIZE, COL_STATUS, COL_RESULT = range(4)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"VectorZip {__version__} — Lossless Compression")
        self.setMinimumSize(980, 720)
        self.resize(1080, 780)
        self._jobs = []  # list of file paths in queue order
        self._row_for = {}  # path -> row
        self._thread = None
        self._worker = None
        self._start_time = None
        self._closing = False
        self._stats = {"files": 0, "in": 0, "out": 0}

        self._build_ui()
        self.setStyleSheet(STYLESHEET)
        self._log("VectorZip ready — drop files in to compress or decompress.", "info")

    # -- UI construction ----------------------------------------------------

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        # Header
        header = QtWidgets.QHBoxLayout()
        brand = QtWidgets.QLabel()
        brand.setObjectName("brand")
        brand.setText('Vector<span id="brandAccent">Zip</span>')
        brand.setTextFormat(QtCore.Qt.TextFormat.RichText)
        tagline = QtWidgets.QLabel("Lossless compression, perfected.")
        tagline.setObjectName("tagline")
        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(0)
        title_box.addWidget(brand)
        title_box.addWidget(tagline)
        header.addLayout(title_box)
        header.addStretch(1)
        badge = QtWidgets.QLabel(f"v{__version__}")
        badge.setObjectName("versionBadge")
        header.addWidget(badge, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        # Queue card
        queue_box = QtWidgets.QGroupBox("File queue")
        ql = QtWidgets.QVBoxLayout(queue_box)

        self.drop_zone = QtWidgets.QLabel("Drag & drop files here — or use Add files")
        self.drop_zone.setObjectName("dropZone")
        self.drop_zone.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.drop_zone.setAcceptDrops(True)
        self.drop_zone.installEventFilter(self)
        ql.addWidget(self.drop_zone)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["File", "Size", "Status", "Result"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(self.COL_FILE, QtWidgets.QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(self.COL_SIZE, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(self.COL_STATUS, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(self.COL_RESULT, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        ql.addWidget(self.table, stretch=1)

        qbtns = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton("＋ Add files")
        self.add_btn.clicked.connect(self._add_files)
        self.remove_btn = QtWidgets.QPushButton("Remove selected")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn = QtWidgets.QPushButton("Clear queue")
        self.clear_btn.clicked.connect(self._clear_queue)
        for b in (self.add_btn, self.remove_btn, self.clear_btn):
            qbtns.addWidget(b)
        qbtns.addStretch(1)
        ql.addLayout(qbtns)
        layout.addWidget(queue_box, stretch=3)

        # Options + actions
        opts_box = QtWidgets.QGroupBox("Options & actions")
        ol = QtWidgets.QGridLayout(opts_box)
        ol.addWidget(QtWidgets.QLabel("Mode:"), 0, 0)
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["Compress", "Decompress"])
        self.mode_combo.currentTextChanged.connect(self._mode_changed)
        ol.addWidget(self.mode_combo, 0, 1)

        ol.addWidget(QtWidgets.QLabel("Output folder:"), 0, 2)
        self.out_edit = QtWidgets.QLineEdit()
        self.out_edit.setPlaceholderText("Same folder as original (default)")
        self.out_edit.setReadOnly(True)
        ol.addWidget(self.out_edit, 0, 3)
        self.browse_btn = QtWidgets.QPushButton("Browse…")
        self.browse_btn.clicked.connect(self._browse_out)
        ol.addWidget(self.browse_btn, 0, 4)
        self.default_out_btn = QtWidgets.QPushButton("Reset")
        self.default_out_btn.clicked.connect(lambda: self.out_edit.clear())
        ol.addWidget(self.default_out_btn, 0, 5)

        self.overwrite_chk = QtWidgets.QCheckBox("Overwrite existing outputs")
        self.overwrite_chk.setChecked(False)
        ol.addWidget(self.overwrite_chk, 1, 0, 1, 3)

        self.start_btn = QtWidgets.QPushButton("▶  Start")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.clicked.connect(self._start)
        self.cancel_btn = QtWidgets.QPushButton("■ Cancel")
        self.cancel_btn.setObjectName("dangerBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        ol.addWidget(self.start_btn, 1, 4)
        ol.addWidget(self.cancel_btn, 1, 5)
        layout.addWidget(opts_box)

        # Progress
        prog_row = QtWidgets.QHBoxLayout()
        self.prog_label = QtWidgets.QLabel("Idle")
        self.prog_label.setStyleSheet(f"color: {TEXT_DIM};")
        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        prog_row.addWidget(self.prog_label, stretch=1)
        prog_row.addWidget(self.bar, stretch=3)
        layout.addLayout(prog_row)

        # Stat cards
        stats_row = QtWidgets.QHBoxLayout()
        self.stat_files_v = self._stat_card(stats_row, "Files done", "0", False)
        self.stat_in_v = self._stat_card(stats_row, "Original size", "—", False)
        self.stat_out_v = self._stat_card(stats_row, "Output size", "—", False)
        self.stat_ratio_v = self._stat_card(stats_row, "Space saved", "—", True)
        layout.addLayout(stats_row)

        # Tabs: log
        self.tabs = QtWidgets.QTabWidget()
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.tabs.addTab(self.log, "Activity log")
        layout.addWidget(self.tabs, stretch=2)

        self.statusBar().showMessage("Ready")

    def _stat_card(self, row, label, initial, accent):
        card = QtWidgets.QFrame()
        card.setObjectName("statCard")
        vl = QtWidgets.QVBoxLayout(card)
        vl.setContentsMargins(14, 10, 14, 10)
        val = QtWidgets.QLabel(initial)
        val.setObjectName("statValueAccent" if accent else "statValue")
        lab = QtWidgets.QLabel(label)
        lab.setObjectName("statLabel")
        vl.addWidget(val)
        vl.addWidget(lab)
        row.addWidget(card, stretch=1)
        return val

    # -- Drag & drop --------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self.drop_zone:
            if event.type() == QtCore.QEvent.Type.DragEnter:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    self.drop_zone.setProperty("dragOver", "true")
                    self.drop_zone.style().unpolish(self.drop_zone)
                    self.drop_zone.style().polish(self.drop_zone)
                return True
            if event.type() == QtCore.QEvent.Type.DragLeave:
                self.drop_zone.setProperty("dragOver", "false")
                self.drop_zone.style().unpolish(self.drop_zone)
                self.drop_zone.style().polish(self.drop_zone)
                return True
            if event.type() == QtCore.QEvent.Type.Drop:
                paths = [u.toLocalFile() for u in event.mimeData().urls()]
                self._enqueue(paths)
                self.drop_zone.setProperty("dragOver", "false")
                self.drop_zone.style().unpolish(self.drop_zone)
                self.drop_zone.style().polish(self.drop_zone)
                event.acceptProposedAction()
                return True
        return super().eventFilter(obj, event)

    # -- Queue management ---------------------------------------------------

    def _enqueue(self, paths):
        added = 0
        mode = self.mode_combo.currentText().lower()
        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        added += self._enqueue_one(os.path.join(root, f), mode)
            else:
                added += self._enqueue_one(p, mode)
        if added:
            self._log(f"Added {added} file(s) to the queue.", "info")
        self._refresh_buttons()

    def _enqueue_one(self, path, mode):
        if not os.path.isfile(path) or path in self._row_for:
            return 0
        if mode == "decompress" and not path.lower().endswith(".vzip"):
            return 0
        try:
            size = os.path.getsize(path)
        except OSError:
            # Vanished (or became unreadable) between the dialog/drop and here.
            self._log(f"Skipped unreadable file: {path}", "warn")
            return 0
        row = self.table.rowCount()
        self.table.insertRow(row)
        name_item = QtWidgets.QTableWidgetItem(os.path.basename(path))
        name_item.setToolTip(path)
        font = QtGui.QFont("Consolas", 10)
        name_item.setFont(font)
        self.table.setItem(row, self.COL_FILE, name_item)
        self.table.setItem(row, self.COL_SIZE, QtWidgets.QTableWidgetItem(fmt_bytes(size)))
        self.table.setItem(row, self.COL_STATUS, self._status_item("Queued", TEXT_DIM))
        self.table.setItem(row, self.COL_RESULT, QtWidgets.QTableWidgetItem("—"))
        self._jobs.append(path)
        self._row_for[path] = row
        return 1

    @staticmethod
    def _status_item(text, color):
        item = QtWidgets.QTableWidgetItem(text)
        item.setForeground(QtGui.QColor(color))
        f = item.font()
        f.setBold(True)
        item.setFont(f)
        return item

    def _add_files(self):
        mode = self.mode_combo.currentText().lower()
        filt = (
            "VectorZip archives (*.vzip);;All files (*.*)"
            if mode == "decompress"
            else "All files (*.*)"
        )
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Add files", "", filt)
        if paths:
            self._enqueue(paths)

    def _remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            path = self._jobs.pop(r)
            del self._row_for[path]
            self.table.removeRow(r)
        self._row_for = {p: i for i, p in enumerate(self._jobs)}
        self._refresh_buttons()

    def _clear_queue(self):
        self._jobs.clear()
        self._row_for.clear()
        self.table.setRowCount(0)
        self._refresh_buttons()

    def _mode_changed(self, text):
        self._clear_queue()
        self._log(f"Mode switched to {text.lower()} — queue cleared.", "info")

    def _browse_out(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose output folder")
        if d:
            self.out_edit.setText(d)

    # -- Run control ----------------------------------------------------------

    def _refresh_buttons(self):
        running = self._thread is not None and self._thread.isRunning()
        has_jobs = bool(self._jobs)
        self.start_btn.setEnabled(has_jobs and not running)
        self.cancel_btn.setEnabled(running)
        self.add_btn.setEnabled(not running)
        self.remove_btn.setEnabled(not running and has_jobs)
        self.clear_btn.setEnabled(not running and has_jobs)
        self.mode_combo.setEnabled(not running)

    def _start(self):
        if not self._jobs:
            return
        mode = self.mode_combo.currentText().lower()
        out_dir = self.out_edit.text().strip() or None
        if out_dir and not os.path.isdir(out_dir):
            QtWidgets.QMessageBox.warning(
                self, "Output folder", "That output folder does not exist."
            )
            return
        # Pre-flight: drop jobs whose output already exists (unless
        # overwrite), and drop jobs whose output name collides with another
        # job in this batch — otherwise a later job would silently replace
        # an earlier job's good output (or, on refusal, quarantine it).
        jobs, skipped = _plan_jobs(self._jobs, mode, out_dir, self.overwrite_chk.isChecked())
        for p, reason in skipped:
            self._mark_skipped(p, reason)
            self._log(
                f"Skipped ({reason.lower()}): {os.path.basename(_expected_output(p, mode))}",
                "warn",
            )
        if not jobs:
            self._log("Nothing to do — all outputs already exist.", "warn")
            self._refresh_buttons()
            return
        for p in jobs:
            self.table.setItem(
                self._row_for[p], self.COL_STATUS, self._status_item("Queued", TEXT_DIM)
            )

        self._stats = {"files": 0, "in": 0, "out": 0}
        self._update_stats()
        self._start_time = time.time()
        self._log(f"Starting {mode}ion of {len(jobs)} file(s)…", "info")
        self.statusBar().showMessage(f"Working — {mode}ing {len(jobs)} file(s)")

        self._thread = QtCore.QThread(self)
        self._worker = JobWorker(jobs, mode, out_dir, self.overwrite_chk.isChecked())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._deferred_close)
        self._thread.start()
        self._refresh_buttons()

    def _mark_skipped(self, path, reason):
        self.table.setItem(
            self._row_for[path], self.COL_STATUS, self._status_item("Skipped", WARNING)
        )
        self.table.setItem(self._row_for[path], self.COL_RESULT, QtWidgets.QTableWidgetItem(reason))

    def closeEvent(self, event):
        # Never destroy a running worker thread with the window: that is a
        # hard Qt crash ("QThread: Destroyed while thread is still running").
        # Cancel instead and finish the close once the thread has exited.
        if self._thread is not None and self._thread.isRunning():
            self._log("Cancelling running jobs before exit…", "warn")
            if self._worker is not None:
                self._worker.cancelled = True
            self._closing = True
            event.ignore()
            return
        event.accept()

    def _deferred_close(self):
        if self._closing:
            self.close()

    def _cancel(self):
        if self._worker:
            self._worker.cancelled = True
            self._log("Cancelling…", "warn")

    def _on_progress(self, done, total, label):
        pct = int(done / total * 100) if total else 0
        self.bar.setValue(pct)
        self.prog_label.setText(f"{label} — {fmt_bytes(done)} / {fmt_bytes(total)}")

    def _on_file_done(self, path, ok, detail, in_size, out_size):
        row = self._row_for.get(path)
        if row is None:
            return
        if ok:
            self.table.setItem(row, self.COL_STATUS, self._status_item("Done", SUCCESS))
            ratio = ""
            if in_size > 0:
                saved = (1 - out_size / in_size) * 100
                ratio = f"{saved:+.1f}%"
                self.table.setItem(
                    row, self.COL_RESULT, QtWidgets.QTableWidgetItem(f"{detail}  ({ratio})")
                )
            else:
                self.table.setItem(row, self.COL_RESULT, QtWidgets.QTableWidgetItem(detail))
            self._stats["files"] += 1
            self._stats["in"] += in_size
            self._stats["out"] += out_size
            self._log(f"✓ {os.path.basename(path)} — {detail}", "ok")
        else:
            self.table.setItem(row, self.COL_STATUS, self._status_item("Failed", ERROR))
            self.table.setItem(row, self.COL_RESULT, QtWidgets.QTableWidgetItem(detail))
            self._log(f"✗ {os.path.basename(path)} — {detail}", "err")
        self._update_stats()

    def _on_finished(self):
        elapsed = time.time() - (self._start_time or time.time())
        self.bar.setValue(100)
        self.prog_label.setText(f"Finished in {elapsed:.1f}s")
        self._log(f"Batch finished in {elapsed:.1f}s — {self._stats['files']} file(s) OK.", "info")
        self.statusBar().showMessage("Ready")
        self._thread = None
        self._worker = None
        self._refresh_buttons()

    def _update_stats(self):
        s = self._stats
        self.stat_files_v.setText(str(s["files"]))
        self.stat_in_v.setText(fmt_bytes(s["in"]) if s["files"] else "—")
        self.stat_out_v.setText(fmt_bytes(s["out"]) if s["files"] else "—")
        if s["files"] and s["in"] > 0:
            saved = (1 - s["out"] / s["in"]) * 100
            self.stat_ratio_v.setText(f"{saved:.1f}%")
        else:
            self.stat_ratio_v.setText("—")

    # -- Log ------------------------------------------------------------------

    def _log(self, message, kind="info"):
        colors = {"info": TEXT_DIM, "ok": SUCCESS, "warn": WARNING, "err": ERROR}
        stamp = time.strftime("%H:%M:%S")
        cursor = self.log.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        block_fmt = QtGui.QTextBlockFormat()
        cursor.setBlockFormat(block_fmt)
        # Filenames flow into log messages — escape before insertHtml so a
        # file named "<b>..." can't inject markup into the activity log.
        safe = html.escape(message)
        cursor.insertHtml(
            f'<span style="color:#5b6a7e">[{stamp}]</span> '
            f'<span style="color:{colors.get(kind, TEXT_DIM)}">{safe}</span><br>'
        )
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("VectorZip")
    app.setOrganizationName("VectorZip")
    win = VectorZipWindow()
    win.show()
    sys.exit(app.exec())
