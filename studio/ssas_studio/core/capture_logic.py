"""The Face-ID-like capture flow, independent of the GUI so it can be tested.

The student looks straight first, then moves their head toward ring segments
shown in a random order (so a printed photo or a video cannot follow), and must
blink once. Photos are saved only when exactly one person is in front of the
camera and the picture quality is good.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

RING_SEGMENTS = 12
RING_RADIUS_DEG = 18.0
MATCH_TOLERANCE_DEG = 9.0
FRONT_TOLERANCE_DEG = 8.0
SECOND_FACE_RATIO = 0.35  # another face at least this big (vs the main one) = a second person
BLINK_CLOSED = 0.55  # eye openness below this fraction of the student's normal = closed
BLINK_OPEN = 0.8


@dataclass
class Feedback:
    message: str
    save: bool = False
    target: int | None = None  # ring segment to highlight (None = look straight)
    blocked: bool = False  # something is wrong (e.g. two people)


@dataclass
class CaptureSession:
    photos_per_segment: int = 6
    front_photos: int = 8
    require_blink: bool = True
    seed: int | None = None
    order: list[int] = field(default_factory=list)
    filled: list[int] = field(default_factory=lambda: [0] * RING_SEGMENTS)
    front_saved: int = 0
    blink_done: bool = False
    _eye_samples: list[float] = field(default_factory=list)
    _eye_closed: bool = False

    def __post_init__(self):
        rnd = random.Random(self.seed)
        self.order = list(range(RING_SEGMENTS))
        rnd.shuffle(self.order)

    # ----- progress -----
    @property
    def total_photos(self) -> int:
        return self.front_photos + RING_SEGMENTS * self.photos_per_segment

    @property
    def saved_photos(self) -> int:
        return self.front_saved + sum(self.filled)

    @property
    def segments_done(self) -> int:
        return sum(1 for n in self.filled if n >= self.photos_per_segment)

    @property
    def current_target(self) -> int | None:
        if self.front_saved < self.front_photos:
            return None
        for seg in self.order:
            if self.filled[seg] < self.photos_per_segment:
                return seg
        return None

    @property
    def finished(self) -> bool:
        photos_done = self.front_saved >= self.front_photos and self.segments_done == RING_SEGMENTS
        return photos_done and (self.blink_done or not self.require_blink)

    @staticmethod
    def segment_vector(seg: int) -> tuple[float, float]:
        """Target (yaw, pitch) in *display* space (preview is mirrored like a selfie)."""
        theta = 2 * math.pi * seg / RING_SEGMENTS
        return RING_RADIUS_DEG * math.cos(theta), RING_RADIUS_DEG * math.sin(theta)

    # ----- blink -----
    def _update_blink(self, openness: float | None) -> None:
        if openness is None or self.blink_done:
            return
        if len(self._eye_samples) < 15:
            self._eye_samples.append(openness)
            return
        normal = sorted(self._eye_samples)[len(self._eye_samples) // 2]
        if normal <= 0:
            return
        if openness < BLINK_CLOSED * normal:
            self._eye_closed = True
        elif self._eye_closed and openness > BLINK_OPEN * normal:
            self.blink_done = True

    # ----- main step -----
    def update(self, face_widths: list[float], yaw: float | None, pitch: float | None,
               openness: float | None, quality_problem: str | None) -> Feedback:
        """Call once per camera frame. ``yaw`` is in camera space (positive = nose to image right)."""
        if not face_widths:
            return Feedback("Look at the camera", target=self.current_target, blocked=True)
        main = max(face_widths)
        if sum(1 for w in face_widths if w >= SECOND_FACE_RATIO * main) > 1:
            return Feedback("Only one person in front of the camera, please", blocked=True)
        if yaw is None or pitch is None:
            return Feedback("Look at the camera", target=self.current_target, blocked=True)

        self._update_blink(openness)

        if self.finished:
            return Feedback("Done — all photos saved")
        if quality_problem:
            return Feedback(quality_problem, target=self.current_target, blocked=True)

        dyaw, dpitch = -yaw, pitch  # display space
        target = self.current_target
        if target is None and self.front_saved < self.front_photos:
            if abs(dyaw) <= FRONT_TOLERANCE_DEG and abs(dpitch) <= FRONT_TOLERANCE_DEG:
                self.front_saved += 1
                return Feedback("Hold still — looking straight", save=True)
            return Feedback("Look straight at the camera")
        if target is None:
            # All photos done, only the blink is missing.
            return Feedback("Now blink once, please")
        ty, tp = self.segment_vector(target)
        if math.hypot(dyaw - ty, dpitch - tp) <= MATCH_TOLERANCE_DEG:
            self.filled[target] += 1
            msg = "Good — hold it"
            if not self.blink_done and self.require_blink and self.segments_done == RING_SEGMENTS:
                msg = "Now blink once, please"
            return Feedback(msg, save=True, target=target)
        return Feedback("Slowly move your nose toward the green part of the circle", target=target)
