"""From the photos of a group's people on disk to a trained group model."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .. import __version__
from ..logs import get_logger
from . import groupmodel
from .align import norm_crop
from .augment import augment
from .detect import FaceDetector, detect_size_for
from .embed import FaceEmbedder
from .landmarks import LandmarkModel
from .models import MODELS, gpu_name, make_session, model_path, sha256_file
from .storage import Organisation, now_iso
from .train import Cancelled, Dataset, TrainConfig, find_lookalikes, train_group

log = get_logger("pipeline")
ProgressFn = Callable[[str, float], None]
CancelFn = Callable[[], bool]

CACHE_VERSION = 2
MAX_STRANGERS = 40_000


class FaceEngine:
    """Loads the ONNX models once and offers detect / align / embed."""

    def __init__(self, models_dir: Path, prefer_gpu: bool = True, with_landmarks: bool = True):
        self.models_dir = Path(models_dir)
        embedder_path = model_path(self.models_dir, "embedder")
        det_s = make_session(model_path(self.models_dir, "detector"), prefer_gpu=False)
        emb_s = make_session(embedder_path, prefer_gpu=prefer_gpu)
        on_gpu = gpu_name(emb_s) != "CPU"
        self.detector = FaceDetector(det_s)
        self.embedder = FaceEmbedder(
            emb_s,
            pad_to=32 if on_gpu else None,
            cpu_fallback=(lambda: make_session(embedder_path, prefer_gpu=False)) if on_gpu else None,
        )
        self.landmarks = (
            LandmarkModel(make_session(model_path(self.models_dir, "landmarks"), prefer_gpu=False))
            if with_landmarks and model_path(self.models_dir, "landmarks").exists()
            else None
        )
        self._sha: dict[str, str] = {}
        log.info("Face models loaded; recognition runs on: %s", self.device)

    @property
    def device(self) -> str:
        """Where the embedder runs now ("CPU", "GPU (DirectML)"...). Changes if the GPU fails and we fall back."""
        return gpu_name(self.embedder.session)

    def model_info(self, key: str) -> dict:
        if key not in self._sha:
            self._sha[key] = sha256_file(model_path(self.models_dir, key))
        return {"file": MODELS[key].filename, "sha256": self._sha[key]}

    def detect(self, img_bgr: np.ndarray, long_side: int = 640):
        return self.detector.detect(img_bgr, detect_size_for(img_bgr.shape, long_side))


@dataclass
class PhotoProblem:
    person: str
    photo: str
    problem: str


def _photo_key(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        st = p.stat()
        h.update(f"{p.parent.name}/{p.name}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()


def build_group_embeddings(
    org: Organisation,
    code: str,
    engine: FaceEngine,
    augment_per_photo: int,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
) -> tuple[Dataset, list[dict], list[PhotoProblem]]:
    """Detect, align, augment and embed every photo of the group (cached in model/embeddings.npz)."""
    g = org.load_group(code)
    people = [p for p in g.people if org.photos(code, p)]
    all_photos = [photo for p in people for photo in org.photos(code, p)]
    key = f"v{CACHE_VERSION}:{augment_per_photo}:{engine.model_info('embedder')['sha256']}:{_photo_key(all_photos)}"
    cache = org.model_dir(code) / "embeddings.npz"
    problems: list[PhotoProblem] = []
    person_rows = [{"id": p.id, "name": p.name} for p in people]

    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        if str(z["key"]) == key:
            ds = Dataset(z["emb"], z["label"], z["group"], len(people))
            probs = [PhotoProblem(*row) for row in z["problems"].tolist()] if "problems" in z else []
            return ds, person_rows, probs

    rng = np.random.default_rng(1234)
    embs, labels, photo_ids, is_aug = [], [], [], []
    total = max(1, len(all_photos))
    done = 0
    photo_id = 0
    for pi, person in enumerate(people):
        for photo in org.photos(code, person):
            if cancel and cancel():
                raise Cancelled()
            img = cv2.imdecode(np.fromfile(str(photo), dtype=np.uint8), cv2.IMREAD_COLOR)
            done += 1
            if img is None:
                problems.append(PhotoProblem(person.name, photo.name, "cannot read the file"))
                continue
            faces = engine.detect(img)
            if not faces:
                problems.append(PhotoProblem(person.name, photo.name, "no face found"))
                continue
            crop = norm_crop(img, faces[0].kps)
            crops = [crop] + [augment(crop, rng) for _ in range(augment_per_photo)]
            e = engine.embedder.embed(crops)
            embs.append(e)
            labels.extend([pi] * len(crops))
            photo_ids.extend([photo_id] * len(crops))
            is_aug.extend([0] + [1] * augment_per_photo)
            photo_id += 1
            if progress:
                progress(f"Reading photos of {person.name}", done / total)
    emb = np.concatenate(embs) if embs else np.zeros((0, 512), np.float32)
    ds = Dataset(emb.astype(np.float32), np.array(labels, np.int64), np.array(photo_ids, np.int64), len(people))
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache,
        key=np.array(key),
        emb=ds.emb,
        label=ds.label,
        group=ds.photo,  # the key keeps its 0.1 name so existing caches stay valid
        aug=np.array(is_aug, np.int8),
        ids=np.array([p.id for p in people]),
        problems=np.array([[p.person, p.photo, p.problem] for p in problems] or np.zeros((0, 3)), dtype=str),
    )
    return ds, person_rows, problems


def stranger_embeddings(org: Organisation, exclude: str, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Embeddings of the people of the other groups (from their caches), with their photo ids."""
    embs, photo_ids = [], []
    offset = 0
    for code in org.group_codes():
        if code == exclude:
            continue
        cache = org.model_dir(code) / "embeddings.npz"
        if not cache.exists():
            continue
        z = np.load(cache, allow_pickle=False)
        embs.append(z["emb"])
        photo_ids.append(z["group"] + offset)
        offset += int(z["group"].max()) + 1 if len(z["group"]) else 0
    if not embs:
        return np.zeros((0, 512), np.float32), np.zeros((0,), np.int64)
    emb = np.concatenate(embs)
    photo = np.concatenate(photo_ids)
    if len(emb) > MAX_STRANGERS:
        idx = rng.choice(len(emb), MAX_STRANGERS, replace=False)
        emb, photo = emb[idx], photo[idx]
    return emb.astype(np.float32), photo.astype(np.int64)


def org_centroids(org: Organisation) -> dict[str, np.ndarray]:
    """Average face of every person who has cached embeddings (for the look-alike check)."""
    out = {}
    for code in org.group_codes():
        cache = org.model_dir(code) / "embeddings.npz"
        if not cache.exists():
            continue
        z = np.load(cache, allow_pickle=False)
        if "ids" not in z:
            continue
        ids, emb, label, aug = z["ids"], z["emb"], z["label"], z["aug"]
        names = {p.id: p.name for p in org.load_group(code).people}
        for i, pid in enumerate(ids.tolist()):
            sel = emb[(label == i) & (aug == 0)]
            if len(sel):
                out[f"{code} · {names.get(pid, pid)}"] = sel.mean(axis=0)
    return out


def train_and_save(
    org: Organisation, code: str, engine: FaceEngine, progress: ProgressFn | None = None, cancel: CancelFn | None = None
) -> dict:
    """Build embeddings, train, and write model/group-model.json + model/report.json."""
    started = time.time()
    st = org.settings
    log.info("Training %s on %s", code, engine.device)
    cfg = TrainConfig(epochs=st.epochs, folds=st.folds, seeds=st.seeds, min_accuracy=st.min_accuracy)

    def sub(lo, hi):
        return (lambda msg, f: progress(msg, lo + (hi - lo) * f)) if progress else None

    ds, people, problems = build_group_embeddings(org, code, engine, st.augment_per_photo, sub(0.0, 0.4), cancel)
    if ds.num_people == 0 or len(ds.emb) == 0:
        raise ValueError("No usable photos in this group yet. Capture photos first.")
    if ds.num_people == 1:
        raise ValueError("At least two people with photos are needed to train a group model.")
    ds.neg, ds.neg_photo = stranger_embeddings(org, code, np.random.default_rng(7))
    log.info("%s: %d people, %d samples, %d strangers", code, ds.num_people, len(ds.emb), len(ds.neg))
    result = train_group(ds, cfg, sub(0.4, 1.0), cancel)

    model = groupmodel.build(
        group_code=code,
        people=people,
        weights=result.weights,
        thresholds={"accept": round(result.accept, 4), "strong": round(result.strong, 4), "margin": result.margin},
        metrics={k: v for k, v in result.metrics.items() if k != "method_scores"},
        method=result.method,
        models={"detector": engine.model_info("detector"), "embedder": engine.model_info("embedder")},
        created_at=now_iso(),
        studio_version=__version__,
    )
    groupmodel.write(org.model_dir(code) / groupmodel.FILE_NAME, model)

    photo_counts = {p["id"]: 0 for p in people}
    photos_per_person: dict[int, set] = {}
    for lbl, photo in zip(ds.label.tolist(), ds.photo.tolist(), strict=True):
        photos_per_person.setdefault(lbl, set()).add(photo)
    for i, p in enumerate(people):
        photo_counts[p["id"]] = len(photos_per_person.get(i, ()))

    lookalikes = [{"a": a, "b": b, "similarity": round(sim, 3)} for a, b, sim in find_lookalikes(org_centroids(org))]
    report = {
        "group_code": code,
        "created_at": now_iso(),
        "duration_s": round(time.time() - started, 1),
        "device": engine.device,
        "method": result.method,
        "epochs": cfg.epochs,
        "folds": cfg.folds,
        "seeds": cfg.seeds,
        "augment_per_photo": st.augment_per_photo,
        "thresholds": model["thresholds"],
        "metrics": result.metrics,
        "people": [
            {
                "id": p["id"],
                "name": p["name"],
                "photos": photo_counts[p["id"]],
                "recall": round(result.per_person_recall[i], 4) if i < len(result.per_person_recall) else None,
            }
            for i, p in enumerate(people)
        ],
        "weak_people": [
            p["name"]
            for i, p in enumerate(people)
            if i < len(result.per_person_recall) and result.per_person_recall[i] < 0.9
        ],
        "photo_problems": [p.__dict__ for p in problems],
        "lookalikes": lookalikes,
        "strangers_used": int(len(ds.neg)),
        "passed": bool(result.metrics.get("passed")),
    }
    (org.model_dir(code) / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(
        "Trained %s: accuracy %.3f on %s in %.0f s",
        code,
        result.metrics["accuracy"],
        report["device"],
        report["duration_s"],
    )
    return report
