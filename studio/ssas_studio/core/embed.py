"""ArcFace embedder (InsightFace w600k_r50): aligned 112x112 face -> 512-d unit vector."""

from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np

from ..logs import get_logger

INPUT_MEAN = 127.5
INPUT_STD = 127.5
log = get_logger("embed")


class FaceEmbedder:
    """Turns aligned face crops into embeddings.

    ``pad_to``: always send batches of exactly this size (the last one is padded). GPU back ends are faster and
    safer with one fixed shape. Leave it ``None`` on the CPU, where padding would only waste time.
    ``cpu_fallback``: builds a CPU session. If the GPU session fails while running, it is used instead.
    """

    def __init__(
        self, session, batch_size: int = 32, pad_to: int | None = None, cpu_fallback: Callable[[], object] | None = None
    ):
        self.session = session
        self.input_name = session.get_inputs()[0].name
        self.output_name = session.get_outputs()[0].name
        self.batch_size = batch_size
        self.pad_to = pad_to
        self.cpu_fallback = cpu_fallback

    def embed(self, crops_bgr: list[np.ndarray] | np.ndarray) -> np.ndarray:
        """Embed aligned BGR crops. Returns an (N, 512) float32 array of unit vectors."""
        crops = list(crops_bgr)
        if not crops:
            return np.zeros((0, 512), dtype=np.float32)
        out = [self._embed_batch(crops[i : i + self.batch_size]) for i in range(0, len(crops), self.batch_size)]
        emb = np.concatenate(out).astype(np.float32)
        return emb / np.linalg.norm(emb, axis=1, keepdims=True).clip(min=1e-12)

    def _embed_batch(self, batch: list[np.ndarray]) -> np.ndarray:
        n = len(batch)
        padded = batch + [batch[-1]] * (self.pad_to - n) if self.pad_to and n < self.pad_to else batch
        blob = cv2.dnn.blobFromImages(padded, 1.0 / INPUT_STD, (112, 112), (INPUT_MEAN,) * 3, swapRB=True)
        try:
            return self.session.run([self.output_name], {self.input_name: blob})[0][:n]
        except Exception:
            if self.cpu_fallback is None:
                raise
            log.exception("The GPU failed while embedding faces; switching to the CPU")
            self.session = self.cpu_fallback()
            self.cpu_fallback = None
            self.pad_to = None
            return self._embed_batch(batch)
