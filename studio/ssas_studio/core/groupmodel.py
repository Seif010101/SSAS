"""The model file of one group, read by the screen app (format "ssas.group-model", version 2; docs/data-format.md).

It holds one row of 512 numbers per person (the direction of that person's face in ArcFace space) and the
thresholds the screen uses to accept a match. No photos and no face pictures are in it."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np

FORMAT = "ssas.group-model"
VERSION = 2
FILE_NAME = "group-model.json"


def encode_matrix(m: np.ndarray) -> dict:
    m = np.ascontiguousarray(m, dtype="<f4")
    return {"dtype": "float32", "shape": list(m.shape), "data": base64.b64encode(m.tobytes()).decode("ascii")}


def decode_matrix(d: dict) -> np.ndarray:
    if d.get("dtype") != "float32":
        raise ValueError("Only float32 matrices are supported")
    return np.frombuffer(base64.b64decode(d["data"]), dtype="<f4").reshape(d["shape"]).copy()


def build(
    group_code: str,
    people: list[dict],
    weights: np.ndarray,
    thresholds: dict,
    metrics: dict,
    method: str,
    models: dict,
    created_at: str,
    studio_version: str,
) -> dict:
    if weights.shape[0] != len(people):
        raise ValueError("One weight row per person is required")
    return {
        "format": FORMAT,
        "version": VERSION,
        "group_code": group_code,
        "created_at": created_at,
        "studio_version": studio_version,
        "method": method,
        "models": models,  # {"detector": {"file", "sha256"}, "embedder": {...}}
        "people": people,  # [{"id", "name"}] in row order
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
        raise ValueError(f"{path} is not a group model file")
    if model.get("version", 0) > VERSION:
        raise ValueError("This group model was made by a newer SSAS Studio")
    if model.get("version", 0) < VERSION:
        raise ValueError("This group model was made by an older SSAS Studio: train the group again")
    return model


def from_v1(old: dict) -> dict:
    """A 0.1 class model ("ssas.class-model") as a group model: same weights, new words."""
    out = {"format": FORMAT, "version": VERSION, "group_code": old["class_code"]}
    for k, v in old.items():
        if k not in ("format", "version", "class_code"):
            out["people" if k == "students" else k] = v
    return out


def identify(model: dict, emb: np.ndarray) -> list[tuple[str | None, float]]:
    """Reference implementation of the screen's decision for one face (used in tests)."""
    w = decode_matrix(model["weights"])
    t = model["thresholds"]
    c = emb @ w.T
    out = []
    for row in c:
        order = np.argsort(-row)
        top = float(row[order[0]])
        second = float(row[order[1]]) if len(order) > 1 else -1.0
        if top >= t["accept"] and top - second >= t["margin"]:
            out.append((model["people"][order[0]]["id"], top))
        else:
            out.append((None, top))
    return out
