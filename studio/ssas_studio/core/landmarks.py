"""106-point face landmarks (InsightFace 2d106det) and simple head-pose / blink measures.

Used only on the laptop while capturing (the Face-ID-like ring and the blink check).
"""

from __future__ import annotations

import cv2
import numpy as np

from .align import centered_transform

INPUT_SIZE = 192

# Contour points of each eye in the 106-point layout (found by testing on real faces).
LEFT_EYE = list(range(33, 43))
RIGHT_EYE = list(range(87, 97))


class LandmarkModel:
    def __init__(self, session):
        self.session = session
        self.input_name = session.get_inputs()[0].name
        self.output_name = session.get_outputs()[0].name

    def predict(self, img_bgr: np.ndarray, box: np.ndarray) -> np.ndarray:
        """Return (106, 2) landmark coordinates in image pixels."""
        x1, y1, x2, y2 = [float(v) for v in box[:4]]
        w, h = x2 - x1, y2 - y1
        center = ((x1 + x2) / 2, (y1 + y2) / 2)
        scale = INPUT_SIZE / (max(w, h) * 1.5)
        m = centered_transform(center, INPUT_SIZE, scale)
        crop = cv2.warpAffine(img_bgr, m, (INPUT_SIZE, INPUT_SIZE), borderValue=0.0)
        # The model normalises the input itself (mean 0, std 1).
        blob = cv2.dnn.blobFromImage(crop, 1.0, (INPUT_SIZE, INPUT_SIZE), (0, 0, 0), swapRB=True)
        pred = self.session.run([self.output_name], {self.input_name: blob})[0][0].reshape(-1, 2)
        pred = (pred + 1) * (INPUT_SIZE // 2)
        im = cv2.invertAffineTransform(m)
        pts = np.hstack([pred, np.ones((pred.shape[0], 1))]) @ im.T
        return pts.astype(np.float32)


def eye_openness(pts: np.ndarray) -> float:
    """Average height/width ratio of both eye contours (small when the eyes are closed)."""
    vals = []
    for idx in (LEFT_EYE, RIGHT_EYE):
        e = pts[idx]
        w = e[:, 0].max() - e[:, 0].min()
        h = e[:, 1].max() - e[:, 1].min()
        if w > 1e-6:
            vals.append(h / w)
    return float(np.mean(vals)) if vals else 0.0


def head_pose(kps: np.ndarray) -> tuple[float, float]:
    """Rough (yaw, pitch) in degrees from the 5 detector landmarks.

    Positive yaw = the student turned to *their* left (face moves to the right of
    the image); positive pitch = looking up. Good enough to drive the capture ring.
    """
    le, re, nose, lm, rm = kps.astype(np.float64)
    eye_mid = (le + re) / 2
    mouth_mid = (lm + rm) / 2
    iod = np.linalg.norm(re - le)
    if iod < 1e-6:
        return 0.0, 0.0
    # Horizontal nose offset relative to the eye line.
    dx = (nose[0] - eye_mid[0]) / iod
    yaw = float(np.degrees(np.arcsin(np.clip(dx * 1.6, -1, 1))))
    # Vertical nose position between eyes (0) and mouth (1); about 0.5 when frontal.
    face_h = mouth_mid[1] - eye_mid[1]
    if abs(face_h) < 1e-6:
        return yaw, 0.0
    ry = (nose[1] - eye_mid[1]) / face_h
    pitch = float((0.5 - ry) * 120.0)
    return yaw, pitch
