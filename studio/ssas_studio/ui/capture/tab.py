"""Capture tab: the camera stays on for the whole group and the people step in one after another."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.person_capture import FrameResult
from .. import theme
from ..common import GroupPicker, confirm, danger, error, info, muted, primary, title
from ..context import AppContext
from .ring_view import RingView
from .worker import CameraProbe, CameraWorker, log

SIDE_PANEL_WIDTH = 350
COMPLETE_ROLE = Qt.UserRole + 1  # list item data: does this person already have all the photos?
STOPPED_NORMALLY = "Camera stopped"


class CaptureTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.worker: CameraWorker | None = None
        self.probe: CameraProbe | None = None
        self._probed = False
        self._sid: str | None = None  # the person whose turn it is
        self._capturing = False  # a person is being photographed right now
        self._stop_reason = STOPPED_NORMALLY
        self._all_done = False

        root = QHBoxLayout(self)
        self.view = RingView()
        root.addWidget(self.view, 1)
        root.addWidget(self._build_side_panel())

        for key, action in ((Qt.Key_Space, self.toggle), (Qt.Key_Return, self.skip), (Qt.Key_Enter, self.skip)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)

        ctx.photos_changed.connect(self._on_photos_changed)
        self.refresh_people()

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(SIDE_PANEL_WIDTH)
        side = QVBoxLayout(panel)
        side.setContentsMargins(0, 0, 0, 0)
        side.addWidget(title("Capture photos"))
        side.addWidget(
            muted(
                "The camera stays on for the whole group. Each person steps in alone, looks at the camera, "
                "then slowly turns their head in a circle and blinks once. It takes about 20 seconds."
            )
        )

        cameras = QHBoxLayout()
        self.camera_box = QComboBox()
        saved = int(self.ctx.qsettings.value("camera_index", 0))
        self.camera_box.addItem(f"Camera {saved}", saved)
        self.refresh_cams = QPushButton("Refresh")
        self.refresh_cams.setMinimumWidth(84)
        self.refresh_cams.clicked.connect(self.find_cameras)
        cameras.addWidget(self.camera_box, 1)
        cameras.addWidget(self.refresh_cams)
        side.addLayout(cameras)

        self.group_box = GroupPicker(self.ctx)
        self.group_box.changed.connect(self.refresh_people)
        side.addWidget(self.group_box)

        people = QGroupBox("People")
        sl = QVBoxLayout(people)
        sl.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.on_pick)
        self.group_label = muted("")
        sl.addWidget(self.list)
        sl.addWidget(self.group_label)
        side.addWidget(people, 1)

        self.start_btn = primary("Start camera   (Space)")
        self.start_btn.setFocusPolicy(Qt.NoFocus)
        self.start_btn.clicked.connect(self.toggle)
        side.addWidget(self.start_btn)

        self.bar = QProgressBar()
        self.bar.setFormat("%v / %m photos")
        self.bar.setRange(0, 1)
        side.addWidget(self.bar)

        buttons = QHBoxLayout()
        self.skip_btn = QPushButton("Skip person   (Enter)")
        self.skip_btn.setFocusPolicy(Qt.NoFocus)
        self.skip_btn.clicked.connect(self.skip)
        self.retake_btn = danger("Retake…")
        self.retake_btn.setToolTip("Delete the photos of the selected person")
        self.retake_btn.clicked.connect(self.retake)
        buttons.addWidget(self.skip_btn, 1)
        buttons.addWidget(self.retake_btn)
        side.addLayout(buttons)
        return panel

    # ----- cameras -----
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self.worker:
            self.refresh_people()  # photos may have been deleted or added elsewhere
        if not self._probed:
            self._probed = True
            self.find_cameras()

    def find_cameras(self) -> None:
        if self.worker or (self.probe and self.probe.isRunning()):
            return
        self.refresh_cams.setEnabled(False)
        self.probe = CameraProbe()
        self.probe.found.connect(self._on_cameras_found)
        self.probe.start()

    def _on_cameras_found(self, cameras: list) -> None:
        self.refresh_cams.setEnabled(True)
        if not cameras:
            return
        wanted = self.camera_box.currentData()
        self.camera_box.clear()
        for number, label in cameras:
            self.camera_box.addItem(label, number)
        self.camera_box.setCurrentIndex(max(0, self.camera_box.findData(wanted)))

    # ----- the person list -----
    def _photos_wanted(self) -> int:
        return self.ctx.org.settings.photos_per_person

    def _on_photos_changed(self, _code: str) -> None:
        self.refresh_people()

    def refresh_people(self, _code: str = "") -> None:
        code = self.group_box.code
        keep = self._sid
        self.list.blockSignals(True)
        self.list.clear()
        done = 0
        if code:
            org, wanted = self.ctx.org, self._photos_wanted()
            for s in org.load_group(code).people:
                n = len(org.photos(code, s))
                complete = n >= wanted
                done += complete
                item = QListWidgetItem(self._item_text(s.name, n, wanted))
                item.setForeground(QColor(theme.OK if complete else theme.WARN if n else theme.MUTED))
                item.setData(Qt.UserRole, s.id)
                item.setData(COMPLETE_ROLE, complete)
                self.list.addItem(item)
            self.group_label.setText(f"{done} of {self.list.count()} people done")
        self.list.blockSignals(False)
        if keep and self._row_of(keep) >= 0:
            self._select(keep, notify=False)
        elif self.list.count():
            self._select_next(None, notify=False)
        else:
            self._sid = None

    @staticmethod
    def _item_text(name: str, photos: int, wanted: int) -> str:
        if photos >= wanted:
            return f"✓  {name}"
        return f"•  {name}   ({photos}/{wanted})" if photos else f"○  {name}"

    def _row_of(self, person_id: str) -> int:
        return next((r for r in range(self.list.count()) if self.list.item(r).data(Qt.UserRole) == person_id), -1)

    def _select(self, person_id: str | None, notify: bool = True) -> None:
        row = self._row_of(person_id) if person_id else -1
        self.list.blockSignals(True)
        self.list.setCurrentRow(row)
        self.list.blockSignals(False)
        self._sid = person_id if row >= 0 else None
        if notify:
            self._tell_worker()

    def _select_next(self, after: str | None, notify: bool = True) -> bool:
        """Select the next person who still needs photos (after ``after``, wrapping around). False if nobody does."""
        count = self.list.count()
        start = self._row_of(after) + 1 if after else 0
        for k in range(count):
            row = (start + k) % count
            if not self.list.item(row).data(COMPLETE_ROLE):
                self._select(self.list.item(row).data(Qt.UserRole), notify)
                return True
        return False

    def on_pick(self, row: int) -> None:
        if row < 0:
            return
        if self._capturing:  # not in the middle of a person
            self._select(self._sid, notify=False)
            return
        self._sid = self.list.item(row).data(Qt.UserRole)
        self._tell_worker()

    def _person(self):
        code = self.group_box.code
        if not (code and self._sid):
            return code, None
        return code, next((s for s in self.ctx.org.load_group(code).people if s.id == self._sid), None)

    def _tell_worker(self) -> None:
        if not self.worker:
            return
        code, person = self._person()
        if person is None:
            self.worker.set_person(None)
        else:
            self.worker.set_person(person.id, person.name, self.ctx.org.person_dir(code, person))

    # ----- starting and stopping the camera -----
    def toggle(self) -> None:
        if self.worker:
            self.worker.stop()
            return
        if not self.ctx.models_ready:
            return error(
                self, "The face models are not downloaded yet. Open the Settings tab and click “Download models”."
            )
        if not self._choose_person_to_start():
            return
        number = self.camera_box.currentData() or 0
        self.ctx.qsettings.setValue("camera_index", number)
        self._stop_reason, self._all_done, self._capturing = STOPPED_NORMALLY, False, False
        self.worker = CameraWorker(self.ctx, number)
        self.worker.frame.connect(self.on_frame)
        self.worker.person_done.connect(self.on_person_done)
        self.worker.stopped.connect(self._on_stopped)
        self.worker.finished.connect(self._on_worker_finished)  # the thread has really ended
        self._tell_worker()
        self.worker.start()
        self.start_btn.setText("Stop camera   (Space)")
        self._set_controls_enabled(False)

    def _choose_person_to_start(self) -> bool:
        """Make sure a person who still needs photos is selected. Shows a message and returns False if none."""
        row = self._row_of(self._sid) if self._sid else -1
        if row >= 0 and not self.list.item(row).data(COMPLETE_ROLE):
            return True
        if self._select_next(self._sid, notify=False):
            return True
        if self.list.count() == 0:
            error(self, "Add a group and its people first (Groups tab).")
        else:
            error(
                self,
                "Every person in this group already has all the photos. "
                "Pick a person in the list and press Retake to take them again.",
            )
        return False

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (self.group_box, self.camera_box, self.refresh_cams, self.retake_btn):
            widget.setEnabled(enabled)

    def on_frame(self, picture: QImage, result: FrameResult, boxes: list) -> None:
        self.view.show_frame(picture, result, boxes)
        self._capturing = result.state == "capturing"
        if self._capturing:
            self.bar.setRange(0, result.total)
            self.bar.setValue(result.saved)
        elif result.state != "done":
            self.bar.setValue(0)

    def on_person_done(self, person_id: str) -> None:
        QApplication.beep()
        self.ctx.photos_changed.emit(self.group_box.code)  # refreshes this list and the Groups tab
        if not self._select_next(person_id):
            self._all_done = True
            if self.worker:
                self.worker.stop()  # the message is shown once the camera thread has really finished

    def skip(self) -> None:
        if self.worker and self._sid:
            current = self._sid
            self.worker.skip()
            self._select_next(current)

    def _on_stopped(self, reason: str) -> None:
        self._stop_reason = reason

    def _on_worker_finished(self) -> None:
        """Only now is it safe to let go of the worker thread."""
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.wait()  # returns at once; after this the thread object can be released safely
        self.start_btn.setText("Start camera   (Space)")
        self._set_controls_enabled(True)
        self._capturing = False
        self.bar.setValue(0)
        self.view.clear()
        self.refresh_people()
        if self._stop_reason != STOPPED_NORMALLY:
            error(self, self._stop_reason)
        elif self._all_done:
            info(self, f"All people of {self.group_box.code} are done ✓")

    def retake(self) -> None:
        code, person = self._person()
        if person and confirm(self, f"Delete all photos of {person.name} and take them again?"):
            self.ctx.org.clear_photos(code, person)
            self.ctx.photos_changed.emit(code)

    def shutdown(self) -> None:
        """Called when the window closes."""
        if self.worker:
            self.worker.stop()
            if not self.worker.wait(5000):
                log.warning("The camera thread did not stop within 5 s")
        if self.probe:
            self.probe.wait(5000)
