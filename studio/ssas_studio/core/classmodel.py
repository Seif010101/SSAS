"""The per-class model file shared with the board app (see docs/data-format.md)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np

FORMAT = "ssas.class-model"
VERSION = 1


def encode_matrix(m: np.ndarray) -> dict:
    m = np.ascontiguousarray(m, dtype="<f4")
    return {"dtype": "float32", "shape": list(m.shape), "data": base64.b64encode(m.tobytes()).decode("ascii")}


def decode_matrix(d: dict) -> np.ndarray:
    if d.get("dtype") != "float32":
        raise ValueError("Only float32 matrices are supported")
    return np.frombuffer(base64.b64decode(d["data"]), dtype="<f4").reshape(d["shape"]).copy()


def build(class_code: str, students: list[dict], weights: np.ndarray, thresholds: dict, metrics: dict,
          method: str, models: dict, created_at: str, studio_version: str) -> dict:
    if weights.shape[0] != len(students):
        raise ValueError("One weight row per student is required")
    return {
        "format": FORMAT,
        "version": VERSION,
        "class_code": class_code,
        "created_at": created_at,
        "studio_version": studio_version,
        "method": method,
        "models": models,  # {"detector": {"file", "sha256"}, "embedder": {...}}
        "students": students,  # [{"id", "name"}] in row order
        "weights": encode_matrix(weights),
        "thresholds": thresholds,  # {"accept", "strong", "margin"}
        "metrics": metrics,
    }


def write(path: Path, model: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def read(path: Path) -> dict:
    model = json.loads(Path(path).read_text(encoding="utf-8"))
    if model.get("format") != FORMAT:
        raise ValueError(f"{path} is not a class model file")
    if model.get("version", 0) > VERSION:
        raise ValueError("This class model was made by a newer SSAS Studio")
    return model


def identify(model: dict, emb: np.ndarray) -> list[tuple[str | None, float]]:
    """Reference implementation of the board's decision for one face (used in tests)."""
    w = decode_matrix(model["weights"])
    t = model["thresholds"]
    c = emb @ w.T
    out = []
    for row in c:
        order = np.argsort(-row)
        top = float(row[order[0]])
        second = float(row[order[1]]) if len(order) > 1 else -1.0
        if top >= t["accept"] and top - second >= t["margin"]:
            out.append((model["students"][order[0]]["id"], top))
        else:
            out.append((None, top))
    return out
