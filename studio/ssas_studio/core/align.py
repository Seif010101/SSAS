"""Face alignment to the standard 112x112 ArcFace template.

The same maths is implemented in the board app (board-app/core/.../Align.kt);
keep the two in sync.
"""

from __future__ import annotations

import cv2
import numpy as np

ARCFACE_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float64,
)


def similarity_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares similarity transform (Umeyama, no reflection). Returns a 2x3 matrix."""
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    n = src.shape[0]
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_c = src - src_mean
    dst_c = dst - dst_mean
    cov = dst_c.T @ src_c / n
    u, s, vt = np.linalg.svd(cov)
    d = np.ones(2)
    if np.linalg.det(cov) < 0:
        d[1] = -1
    r = u @ np.diag(d) @ vt
    var_src = (src_c**2).sum() / n
    scale = (s * d).sum() / var_src
    t = dst_mean - scale * r @ src_mean
    m = np.zeros((2, 3), dtype=np.float64)
    m[:, :2] = scale * r
    m[:, 2] = t
    return m


def estimate_norm(kps: np.ndarray, size: int = 112) -> np.ndarray:
    return similarity_transform(kps, ARCFACE_DST * (size / 112.0))


def norm_crop(img: np.ndarray, kps: np.ndarray, size: int = 112) -> np.ndarray:
    """Warp the face to a ``size`` x ``size`` aligned crop (bilinear, black border)."""
    m = estimate_norm(kps, size)
    return cv2.warpAffine(img, m, (size, size), flags=cv2.INTER_LINEAR, borderValue=0.0)


def centered_transform(center: tuple[float, float], out_size: int, scale: float) -> np.ndarray:
    """Scale around ``center`` and place it in the middle of an ``out_size`` square (no rotation)."""
    cx, cy = center[0] * scale, center[1] * scale
    return np.array([[scale, 0.0, out_size / 2 - cx], [0.0, scale, out_size / 2 - cy]], dtype=np.float64)
