"""Simple photo quality checks used while capturing."""

from __future__ import annotations

import cv2
import numpy as np


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian (higher = sharper)."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def brightness(gray: np.ndarray) -> float:
    return float(gray.mean())


def face_region(img_bgr: np.ndarray, box: np.ndarray) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in box[:4]]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    return img_bgr[y1:y2, x1:x2]


def check_face(img_bgr: np.ndarray, box: np.ndarray, min_face_px: int = 120,
               min_sharpness: float = 40.0, brightness_range: tuple[float, float] = (60.0, 210.0)) -> str | None:
    """Return a short problem description, or None when the face is good to save."""
    width = float(box[2] - box[0])
    if width < min_face_px:
        return "Come closer to the camera"
    region = face_region(img_bgr, box)
    if region.size == 0:
        return "Face is outside the picture"
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    b = brightness(gray)
    if b < brightness_range[0]:
        return "Too dark — add light"
    if b > brightness_range[1]:
        return "Too bright"
    if sharpness(gray) < min_sharpness:
        return "Hold still (picture is blurry)"
    return None


def crop_for_storage(img_bgr: np.ndarray, box: np.ndarray, expand: float = 2.0, max_side: int = 512) -> np.ndarray:
    """Square crop around the face (``expand`` x the face size) for saving to disk."""
    h, w = img_bgr.shape[:2]
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    side = max(box[2] - box[0], box[3] - box[1]) * expand
    x1, y1 = int(round(cx - side / 2)), int(round(cy - side / 2))
    x2, y2 = int(round(cx + side / 2)), int(round(cy + side / 2))
    pad = max(0, -x1, -y1, x2 - w, y2 - h)
    if pad:
        img_bgr = cv2.copyMakeBorder(img_bgr, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        x1, y1, x2, y2 = x1 + pad, y1 + pad, x2 + pad, y2 + pad
    crop = img_bgr[y1:y2, x1:x2]
    if crop.shape[0] > max_side:
        crop = cv2.resize(crop, (max_side, max_side), interpolation=cv2.INTER_AREA)
    return crop
