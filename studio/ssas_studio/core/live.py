"""The smart screen's job, done on the laptop for the Live demo tab: recognise the people of one group in a camera
picture, decide attendance like a screen, and build the text result a screen would send.

The matching rule is the same as the screen app's (board-app/core/.../GroupModel.kt and FramePipeline.kt).
Nothing here saves a picture.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from .. import __version__
from . import groupmodel
from .align import norm_crop
from .attendance import AttendanceResult, FrameObservation

DEMO_SHOTS_S = [0, 2, 4, 6, 8, 10, 12, 15]  # the quick demo: about 15 seconds instead of the screen's 4 minutes


@dataclass
class SeenFace:
    box: list[float]  # x1, y1, x2, y2 in the camera picture
    person: int | None  # index in the group model, None = unknown
    name: str
    score: float
    strong: bool


class GroupMatcher:
    """One group's trained model: which person, if anyone, a face belongs to."""

    def __init__(self, model: dict):
        self.model = model
        self.people = model["people"]
        self.weights = groupmodel.decode_matrix(model["weights"])
        t = model["thresholds"]
        self.accept, self.strong, self.margin = t["accept"], t["strong"], t["margin"]

    def match(self, embeddings: np.ndarray) -> list[tuple[int | None, float, bool]]:
        """For each embedding: (person index or None, best score, strong)."""
        out = []
        for row in embeddings @ self.weights.T:
            order = np.argsort(-row)
            top = float(row[order[0]])
            second = float(row[order[1]]) if len(order) > 1 else -2.0
            accepted = top >= self.accept and top - second >= self.margin
            out.append((int(order[0]) if accepted else None, top, accepted and top >= self.strong))
        return out


def analyse(engine, matcher: GroupMatcher, img_bgr: np.ndarray, long_side: int = 960, min_face_px: float = 12):
    """Find and recognise the faces in one picture. Returns (FrameObservation, best scores, faces to draw)."""
    faces = [f for f in engine.detect(img_bgr, long_side) if f.width >= min_face_px]
    embeddings = engine.embedder.embed([norm_crop(img_bgr, f.kps) for f in faces])
    recognised: dict[int, bool] = {}
    scores: dict[int, float] = {}
    seen: list[SeenFace] = []
    unknown = 0
    for face, (idx, score, strong) in zip(faces, matcher.match(embeddings), strict=True):
        box = [float(v) for v in face.box]
        if idx is not None and idx in scores:
            # One person can only be one face: a second face matching the same person counts as unknown.
            unknown += 1
            if score <= scores[idx]:
                seen.append(SeenFace(box, None, "?", score, False))
                continue
            for s in seen:  # the earlier, weaker face becomes the unknown one
                if s.person == idx:
                    s.person, s.name, s.strong = None, "?", False
        if idx is None:
            unknown += 1
            seen.append(SeenFace(box, None, "?", score, False))
            continue
        recognised[idx], scores[idx] = strong, score
        seen.append(SeenFace(box, idx, matcher.people[idx]["name"], score, strong))
    obs = FrameObservation(valid=True, recognised=recognised, unknown_faces=unknown, bodies=-1, faces=len(faces))
    return obs, scores, seen


def result_payload(matcher: GroupMatcher, group_code: str, result: AttendanceResult, started: datetime) -> dict:
    """The text a screen would send to the server for this session (format ssas.result, version 2)."""
    return {
        "format": "ssas.result",
        "version": 2,
        "board_code": "LAPTOP-DEMO",
        "group_code": group_code,
        "date": started.date().isoformat(),
        "session": 0,
        "session_start": started.isoformat(timespec="minutes"),
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "frames": result.total_frames,
        "valid_frames": result.valid_frames,
        "unknown_max": result.unknown_max,
        "suspicious_max": result.suspicious_max,
        "camera_problem": None if result.valid_frames else "no usable picture",
        "model_created_at": matcher.model.get("created_at", ""),
        "app_version": f"studio-{__version__}",
        "people": [
            {"id": p["id"], "name": p["name"], "status": s, **({"score": round(b, 4)} if b > -1 else {})}
            for p, s, b in zip(matcher.people, result.statuses, result.best_score, strict=True)
        ],
    }


def payload_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
