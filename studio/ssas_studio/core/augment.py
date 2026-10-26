"""Augmentations that make laptop photos look like a classroom board camera.

They work on aligned 112x112 crops: the face is made small (like a student in
the back row), blurred, compressed, re-lit, slightly rotated or partly covered.
"""

from __future__ import annotations

import cv2
import numpy as np


def _low_res(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    side = int(rng.integers(18, 57))  # face width on the board camera, in pixels
    small = cv2.resize(img, (side, side), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (112, 112), interpolation=cv2.INTER_LINEAR)


def _geometry(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    angle = float(rng.uniform(-8, 8))
    scale = float(rng.uniform(0.95, 1.05))
    m = cv2.getRotationMatrix2D((56, 56), angle, scale)
    m[:, 2] += rng.uniform(-3, 3, size=2)
    return cv2.warpAffine(img, m, (112, 112), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _photometric(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    f = img.astype(np.float32)
    gain = rng.uniform(0.6, 1.4)
    bias = rng.uniform(-30, 30)
    f = f * gain + bias
    f *= rng.uniform(0.85, 1.15, size=3)  # colour temperature of the camera
    f = np.clip(f, 0, 255)
    gamma = rng.uniform(0.7, 1.5)
    f = 255.0 * (f / 255.0) ** gamma
    return np.clip(f, 0, 255).astype(np.uint8)


def _occlude(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = img.copy()
    area = rng.uniform(0.08, 0.22) * 112 * 112
    ratio = rng.uniform(0.5, 2.0)
    w = int(min(110, np.sqrt(area * ratio)))
    h = int(min(110, area / max(w, 1)))
    x = int(rng.integers(0, 112 - w))
    y = int(rng.integers(0, 112 - h))
    out[y : y + h, x : x + w] = int(rng.integers(0, 120))
    return out


def augment(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """One random classroom-like variant of an aligned 112x112 BGR face."""
    out = img
    if rng.random() < 0.5:
        out = cv2.flip(out, 1)
    if rng.random() < 0.7:
        out = _geometry(out, rng)
    if rng.random() < 0.9:
        out = _photometric(out, rng)
    if rng.random() < 0.15:
        out = _occlude(out, rng)
    if rng.random() < 0.65:
        out = _low_res(out, rng)
    if rng.random() < 0.3:
        out = cv2.GaussianBlur(out, (0, 0), float(rng.uniform(0.3, 1.4)))
    if rng.random() < 0.5:
        noise = rng.normal(0, rng.uniform(2, 8), out.shape)
        out = np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    if rng.random() < 0.6:
        q = int(rng.integers(30, 86))
        ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, q])
        if ok:
            out = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return out
