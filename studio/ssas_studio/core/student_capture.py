"""Hands-free capture of a whole class: wait for each student, capture, show "Done", move on.

No camera or window code here, so the whole flow can be tested. ``CaptureSession`` (in ``capture_logic``) decides
what counts as a photo; this module decides when a student starts and ends.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from .capture_logic import SECOND_FACE_RATIO, CaptureSession


@dataclass
class AutoStart:
    """Decides when to begin capturing the next student: one clear face, held steady for a moment.

    After a student is finished the previous face has to leave the picture first, so the same
    person is not captured twice by accident.
    """

    hold_s: float = 1.0
    absent_s: float = 0.5
    min_face_px: float = 110.0
    need_absence: bool = False
    _since: float | None = None
    _gone_since: float | None = None

    def rearm(self) -> None:
        self.need_absence = True
        self._since = None
        self._gone_since = None

    def update(self, face_widths: list[float], now: float) -> tuple[float, bool]:
        """Returns (how far the hold is, 0..1, ready to start)."""
        if not face_widths:
            self._since = None
            if self.need_absence:
                if self._gone_since is None:
                    self._gone_since = now
                elif now - self._gone_since >= self.absent_s:
                    self.need_absence = False
            return 0.0, False
        self._gone_since = None
        main = max(face_widths)
        crowded = sum(1 for w in face_widths if w >= SECOND_FACE_RATIO * main) > 1
        if self.need_absence or crowded or main < self.min_face_px:
            self._since = None
            return 0.0, False
        if self._since is None:
            self._since = now
        frac = 1.0 if self.hold_s <= 0 else min(1.0, (now - self._since) / self.hold_s)
        return frac, frac >= 1.0


@dataclass
class Measurement:
    """What the camera loop measured on the main face of one frame (only needed while capturing)."""

    yaw: float | None
    pitch: float | None
    eye_openness: float | None
    quality_problem: str | None  # "Too dark — add light", "Move your face into the circle"... or None when good


@dataclass
class FrameResult:
    """What to show and do for one camera frame."""

    state: str  # "idle" (no student chosen), "waiting" (for the student to step in), "capturing" or "done"
    message: str
    name: str = ""  # the student whose turn it is
    blocked: bool = False  # something is wrong (second person, too dark...): shown in red
    hold: float = 0.0  # 0..1, how long the face has been steady (waiting state)
    target: int = -1  # ring part to highlight
    save_as: str | None = None  # save this frame's face under this file name
    student_done: bool = False  # this frame finished the student
    phase: str = ""  # "front", "ring", "blink", "done" while capturing
    filled: list[float] = field(default_factory=list)  # 0..1 per ring part
    saved: int = 0
    total: int = 0


class StudentCapture:
    """Hands-free capture for a whole class, without any camera or window code (so it can be tested).

    ``set_student`` says whose turn it is. ``step`` is called for every camera frame and answers what to show
    and whether to save the face. Flow: wait until one face is steady (``AutoStart``), capture the 8+8 poses,
    show "Done" for a moment, then wait for the next student.
    """

    def __init__(
        self,
        new_session: Callable[[], CaptureSession],
        save_interval_s: float = 0.18,
        done_shown_s: float = 2.0,
        give_up_s: float = 12.0,
        auto_start: AutoStart | None = None,
        stamp: Callable[[], str] = lambda: datetime.now().strftime("%Y%m%d-%H%M%S"),
    ):
        self.new_session = new_session
        self.save_interval_s = save_interval_s
        self.done_shown_s = done_shown_s
        self.give_up_s = give_up_s
        self.gate = auto_start or AutoStart()
        self.stamp = stamp
        self.name: str | None = None
        self.session: CaptureSession | None = None
        self._stamp = ""
        self._photo_no = 0
        self._last_save = float("-inf")
        self._last_face = 0.0
        self._done_until = 0.0
        self._done_name = ""
        self._skip = False

    @property
    def capturing(self) -> bool:
        return self.session is not None

    def set_student(self, name: str | None) -> None:
        """Whose turn it is (None: nobody). Changing it in the middle of a capture abandons that capture."""
        if name != self.name and self.session is not None:
            self._stop_session()
        self.name = name

    def skip(self) -> None:
        """Give up on the current student (the next frame goes back to waiting)."""
        self._skip = True

    def step(self, face_widths: list[float], now: float, measure: Callable[[], Measurement]) -> FrameResult:
        """``measure()`` is only called while capturing, because it is the slow part."""
        if face_widths:
            self._last_face = now
        if now < self._done_until:
            self.gate.update(face_widths, now)  # counts how long the last student's face has been gone
            return FrameResult("done", f"Done ✓   {self._done_name}")
        if self.name is None:
            return FrameResult("idle", "Choose a student in the list")
        if self._skip:
            self._skip = False
            self._stop_session()

        if self.session is None:
            hold, ready = self.gate.update(face_widths, now)
            if not ready:
                return FrameResult("waiting", self._waiting_message(face_widths, hold), name=self.name, hold=hold)
            self._start_session(now)
        if now - self._last_face > self.give_up_s:  # the student walked away
            self._stop_session()
            return FrameResult("waiting", self._waiting_message([], 0.0), name=self.name)
        return self._capture_step(face_widths, now, measure())

    # ----- internals -----
    def _waiting_message(self, widths: list[float], hold: float) -> str:
        if not widths or self.gate.need_absence:
            return f"Next: {self.name} — step in front of the camera"
        return f"Ready: {self.name} — hold still" if hold > 0 else "One person at a time, a bit closer"

    def _start_session(self, now: float) -> None:
        self.session = self.new_session()
        self._stamp, self._photo_no, self._last_save = self.stamp(), 0, float("-inf")

    def _stop_session(self) -> None:
        self.session = None
        self.gate.rearm()

    def _capture_step(self, widths: list[float], now: float, m: Measurement) -> FrameResult:
        session = self.session
        fb = session.update(widths, m.yaw, m.pitch, m.eye_openness, m.quality_problem)
        save_as = None
        if fb.save:
            if now - self._last_save >= self.save_interval_s:
                self._photo_no += 1
                tag = "front" if fb.target is None else f"seg{fb.target:02d}"
                save_as = f"{self._stamp}-{self._photo_no:03d}-{tag}.jpg"
                self._last_save = now
            elif fb.target is None:  # too soon after the last photo: undo the count so the session stays in sync
                session.front_saved -= 1
            else:
                session.filled[fb.target] -= 1
        result = FrameResult(
            "capturing",
            fb.message,
            name=self.name,
            blocked=fb.blocked,
            save_as=save_as,
            target=fb.target if fb.target is not None else -1,
            phase=session.phase,
            filled=[min(1.0, n / session.photos_per_segment) for n in session.filled],
            saved=session.saved_photos,
            total=session.total_photos,
        )
        if session.finished:
            self._done_name, self._done_until = self.name, now + self.done_shown_s
            result.state, result.message, result.student_done = "done", f"Done ✓   {self.name}", True
            self.name = None
            self._stop_session()
        return result
