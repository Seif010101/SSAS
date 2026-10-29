"""The Face-ID-like capture flow, independent of the GUI so it can be tested.

The student looks straight first, then slowly turns their head around a circle.
By default each of the 8 ring parts fills wherever the nose points ("free sweep").
In strict mode the parts must be followed in a random order instead, so a printed
photo or a video cannot follow. The student must also blink once, at any time.
Photos are saved only when exactly one person is in front of the camera and the
picture quality is good.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

RING_SEGMENTS = 8
RING_RADIUS_DEG = 18.0
MATCH_TOLERANCE_DEG = 12.0  # strict mode: how close to the prompted part
FREE_MIN_DEG = 9.0  # free sweep: the head must be turned at least this far from straight
FREE_MAX_DEG = 45.0
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
    photos_per_segment: int = 4
    front_photos: int = 8
    require_blink: bool = True
    strict_order: bool = False
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
        """The part to follow in strict mode (None while looking straight, or in free sweep)."""
        if not self.strict_order or self.front_saved < self.front_photos:
            return None
        for seg in self.order:
            if self.filled[seg] < self.photos_per_segment:
                return seg
        return None

    @property
    def phase(self) -> str:
        if self.finished:
            return "done"
        if self.front_saved < self.front_photos:
            return "front"
        if self.segments_done < RING_SEGMENTS:
            return "ring"
        return "blink"

    @staticmethod
    def segment_at(dyaw: float, dpitch: float) -> int | None:
        """Which ring part the head is pointing at (display space), None when too close to straight or too far."""
        r = math.hypot(dyaw, dpitch)
        if r < FREE_MIN_DEG or r > FREE_MAX_DEG:
            return None
        theta = math.atan2(dpitch, dyaw) % (2 * math.pi)
        return round(theta / (2 * math.pi / RING_SEGMENTS)) % RING_SEGMENTS

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
    def update(
        self,
        face_widths: list[float],
        yaw: float | None,
        pitch: float | None,
        openness: float | None,
        quality_problem: str | None,
    ) -> Feedback:
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
            return Feedback("Done ✓")
        if quality_problem:
            return Feedback(quality_problem, target=self.current_target, blocked=True)

        dyaw, dpitch = -yaw, pitch  # display space
        if self.front_saved < self.front_photos:
            if abs(dyaw) <= FRONT_TOLERANCE_DEG and abs(dpitch) <= FRONT_TOLERANCE_DEG:
                self.front_saved += 1
                return Feedback("Hold still — looking straight", save=True)
            return Feedback("Look straight at the camera")
        if self.segments_done == RING_SEGMENTS:
            return Feedback("Now blink once, please")

        if self.strict_order:
            target = self.current_target
            ty, tp = self.segment_vector(target)
            if math.hypot(dyaw - ty, dpitch - tp) <= MATCH_TOLERANCE_DEG:
                self.filled[target] += 1
                return Feedback(self._ring_message(), save=True, target=target)
            return Feedback("Slowly move your nose toward the green part of the circle", target=target)

        seg = self.segment_at(dyaw, dpitch)
        if seg is None:
            return Feedback("Turn your head slowly in a circle")
        if self.filled[seg] >= self.photos_per_segment:
            return Feedback("Keep turning — fill the grey parts")
        self.filled[seg] += 1
        return Feedback(self._ring_message(), save=True, target=seg)

    def _ring_message(self) -> str:
        if self.segments_done == RING_SEGMENTS - 1 and self.require_blink and not self.blink_done:
            return "Good — and blink once"
        return "Good — keep turning"
