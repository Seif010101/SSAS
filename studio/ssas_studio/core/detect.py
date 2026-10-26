"""SCRFD face detector (InsightFace det_10g) — boxes, scores and 5 landmarks.

Ported from insightface/python-package/insightface/model_zoo/scrfd.py.
The board app has a Kotlin port with the same maths (Scrfd.kt).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

STRIDES = (8, 16, 32)
NUM_ANCHORS = 2
INPUT_MEAN = 127.5
INPUT_STD = 128.0


@dataclass
class Face:
    box: np.ndarray  # x1, y1, x2, y2
    score: float
    kps: np.ndarray  # (5, 2): left eye, right eye, nose, left mouth, right mouth

    @property
    def width(self) -> float:
        return float(self.box[2] - self.box[0])

    @property
    def height(self) -> float:
        return float(self.box[3] - self.box[1])


def nms(boxes: np.ndarray, scores: np.ndarray, thresh: float) -> list[int]:
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(ovr <= thresh)[0] + 1]
    return keep


class FaceDetector:
    def __init__(self, session, score_threshold: float = 0.5, nms_threshold: float = 0.4):
        self.session = session
        self.input_name = session.get_inputs()[0].name
        self.output_names = [o.name for o in session.get_outputs()]
        if len(self.output_names) != 9:
            raise ValueError("Unexpected detector model: expected 9 outputs (scores, boxes, landmarks x 3 strides).")
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self._anchor_cache: dict[tuple[int, int, int], np.ndarray] = {}

    def _anchors(self, h: int, w: int, stride: int) -> np.ndarray:
        key = (h, w, stride)
        if key not in self._anchor_cache:
            centers = np.stack(np.mgrid[:h, :w][::-1], axis=-1).astype(np.float32)
            centers = (centers * stride).reshape((-1, 2))
            centers = np.stack([centers] * NUM_ANCHORS, axis=1).reshape((-1, 2))
            self._anchor_cache[key] = centers
        return self._anchor_cache[key]

    def detect(self, img_bgr: np.ndarray, input_size: tuple[int, int] = (640, 640), max_faces: int = 0) -> list[Face]:
        """Detect faces in a BGR image. ``input_size`` is (width, height), multiples of 32."""
        in_w, in_h = input_size
        img_h, img_w = img_bgr.shape[:2]
        if img_h / img_w > in_h / in_w:
            new_h = in_h
            new_w = int(new_h * img_w / img_h)
        else:
            new_w = in_w
            new_h = int(new_w * img_h / img_w)
        scale = new_h / img_h
        resized = cv2.resize(img_bgr, (new_w, new_h))
        canvas = np.zeros((in_h, in_w, 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = resized

        blob = cv2.dnn.blobFromImage(canvas, 1.0 / INPUT_STD, (in_w, in_h), (INPUT_MEAN,) * 3, swapRB=True)
        outs = self.session.run(self.output_names, {self.input_name: blob})

        scores_all, boxes_all, kps_all = [], [], []
        for i, stride in enumerate(STRIDES):
            scores = outs[i].reshape(-1)
            box_pred = outs[i + 3] * stride
            kps_pred = outs[i + 6] * stride
            anchors = self._anchors(in_h // stride, in_w // stride, stride)
            pos = np.where(scores >= self.score_threshold)[0]
            if pos.size == 0:
                continue
            a = anchors[pos]
            b = box_pred[pos]
            boxes = np.stack([a[:, 0] - b[:, 0], a[:, 1] - b[:, 1], a[:, 0] + b[:, 2], a[:, 1] + b[:, 3]], axis=-1)
            k = kps_pred[pos].reshape(-1, 5, 2) + a[:, None, :]
            scores_all.append(scores[pos])
            boxes_all.append(boxes)
            kps_all.append(k)
        if not scores_all:
            return []
        scores = np.concatenate(scores_all)
        boxes = np.concatenate(boxes_all) / scale
        kps = np.concatenate(kps_all) / scale
        keep = nms(boxes, scores, self.nms_threshold)
        faces = [Face(boxes[i].astype(np.float32), float(scores[i]), kps[i].astype(np.float32)) for i in keep]
        faces.sort(key=lambda f: f.width * f.height, reverse=True)
        if max_faces > 0:
            faces = faces[:max_faces]
        return faces


def detect_size_for(img_shape: tuple[int, ...], long_side: int = 640) -> tuple[int, int]:
    """A detector input size (multiple of 32) that keeps the image aspect ratio."""
    h, w = img_shape[:2]
    if w >= h:
        in_w = long_side
        in_h = max(32, int(round(long_side * h / w / 32.0)) * 32)
    else:
        in_h = long_side
        in_w = max(32, int(round(long_side * w / h / 32.0)) * 32)
    return in_w, in_h
