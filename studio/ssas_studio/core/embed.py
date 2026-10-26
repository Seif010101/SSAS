"""ArcFace embedder (InsightFace w600k_r50): aligned 112x112 face -> 512-d unit vector."""

from __future__ import annotations

import cv2
import numpy as np

INPUT_MEAN = 127.5
INPUT_STD = 127.5


class FaceEmbedder:
    def __init__(self, session, batch_size: int = 32):
        self.session = session
        self.input_name = session.get_inputs()[0].name
        self.output_name = session.get_outputs()[0].name
        self.batch_size = batch_size

    def embed(self, crops_bgr: list[np.ndarray] | np.ndarray) -> np.ndarray:
        """Embed aligned BGR crops. Returns an (N, 512) float32 array of unit vectors."""
        crops = list(crops_bgr)
        if not crops:
            return np.zeros((0, 512), dtype=np.float32)
        out = []
        for start in range(0, len(crops), self.batch_size):
            batch = crops[start : start + self.batch_size]
            blob = cv2.dnn.blobFromImages(batch, 1.0 / INPUT_STD, (112, 112), (INPUT_MEAN,) * 3, swapRB=True)
            feats = self.session.run([self.output_name], {self.input_name: blob})[0]
            out.append(feats)
        emb = np.concatenate(out).astype(np.float32)
        return emb / np.linalg.norm(emb, axis=1, keepdims=True).clip(min=1e-12)
