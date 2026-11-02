"""The smart screen's attendance decision, in Python, for the Live demo tab.

These are the same rules as the screen app (board-app/core/.../Attendance.kt and FrameHealth.kt), so a demo on
the laptop decides exactly like a real screen. If you change a rule, change it in both places (tests on both sides).

    present       recognised in 2 frames, or once with a very confident ("strong") match
    absent        never recognised AND enough good frames AND nobody unexplained in the room
    needs_review  not recognised, but there were unknown faces, or too few good frames
    no_data       the camera gave no usable frame at all
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

STATUSES = ("present", "absent", "needs_review", "no_data")


@dataclass
class FrameObservation:
    """What one camera frame showed."""

    valid: bool
    recognised: dict[int, bool] = field(default_factory=dict)  # person index -> strong match
    unknown_faces: int = 0  # faces not matched to anyone in the group
    bodies: int = -1  # bodies found by the pose model, -1 = no pose model (the laptop demo has none)
    faces: int = 0
    suspicious: int = 0  # faces without a body (a photo or phone held up)


@dataclass
class AttendanceResult:
    statuses: list[str]
    best_score: list[float]
    valid_frames: int
    total_frames: int
    unknown_max: int
    suspicious_max: int


class AttendanceAggregator:
    """Collects the frames of one start-of-session capture and decides each person's status."""

    def __init__(self, num_people: int, min_valid_frames: int = 3):
        self.n = num_people
        self.min_valid_frames = min_valid_frames
        self.hits = [0] * num_people
        self.strong = [False] * num_people
        self.best = [-1.0] * num_people
        self.frames: list[FrameObservation] = []

    def add(self, frame: FrameObservation, scores: dict[int, float] | None = None) -> None:
        self.frames.append(frame)
        if not frame.valid:
            return
        for i, is_strong in frame.recognised.items():
            self.hits[i] += 1
            if is_strong:
                self.strong[i] = True
        for i, s in (scores or {}).items():
            self.best[i] = max(self.best[i], s)

    def is_present(self, i: int) -> bool:
        return self.hits[i] >= 2 or self.strong[i]

    def all_present(self) -> bool:
        return all(self.is_present(i) for i in range(self.n))

    @property
    def valid_frames(self) -> int:
        return sum(1 for f in self.frames if f.valid)

    def result(self) -> AttendanceResult:
        valid = [f for f in self.frames if f.valid]
        present = [self.is_present(i) for i in range(self.n)]
        # A frame is "unexplained" when it shows more people than the recognised people it contains,
        # beyond what present-but-not-visible people could explain.
        unexplained_frames = 0
        unknown_max = 0
        for f in valid:
            present_not_seen = sum(1 for i in range(self.n) if present[i] and i not in f.recognised)
            faceless_bodies = max(0, f.bodies - f.faces) if f.bodies >= 0 else 0
            unexplained = f.unknown_faces + max(0, faceless_bodies - present_not_seen)
            unknown_max = max(unknown_max, unexplained)
            if unexplained > 0:
                unexplained_frames += 1
        crowded = bool(valid) and unexplained_frames * 2 >= len(valid)

        def status(i: int) -> str:
            if present[i]:
                return "present"
            if not valid:
                return "no_data"
            if len(valid) < self.min_valid_frames or crowded:
                return "needs_review"
            return "absent"

        return AttendanceResult(
            [status(i) for i in range(self.n)],
            list(self.best),
            len(valid),
            len(self.frames),
            unknown_max,
            max((f.suspicious for f in self.frames), default=0),
        )


def frame_health(img_bgr: np.ndarray, previous_signature: int | None = None) -> tuple[bool, str | None, int]:
    """Cheap checks that tell a broken camera picture from a real room: (ok, reason, signature)."""
    h, w = img_bgr.shape[:2]
    step = max(1, min(w, h) // 90)
    sample = img_bgr[::step, ::step].astype(np.int32)
    gray = (sample[..., 2] * 299 + sample[..., 1] * 587 + sample[..., 0] * 114) // 1000
    mean, std = float(gray.mean()), float(gray.std())
    signature = hash(gray.tobytes())
    if mean < 15 and std < 5:
        reason = "black picture (camera covered or off)"
    elif std < 6:
        reason = "uniform picture (lens covered?)"
    elif previous_signature is not None and previous_signature == signature:
        reason = "frozen picture"
    else:
        reason = None
    return reason is None, reason, signature
