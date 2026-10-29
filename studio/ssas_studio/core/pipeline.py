"""From student photos on disk to a trained class model."""

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
from . import classmodel
from .align import norm_crop
from .augment import augment
from .detect import FaceDetector, detect_size_for
from .embed import FaceEmbedder
from .landmarks import LandmarkModel
from .models import MODELS, gpu_name, make_session, model_path, sha256_file
from .storage import School, now_iso
from .train import Cancelled, Dataset, TrainConfig, find_lookalikes, train_class

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
    student: str
    photo: str
    problem: str


def _photo_key(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        st = p.stat()
        h.update(f"{p.parent.name}/{p.name}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()


def build_class_embeddings(
    school: School,
    code: str,
    engine: FaceEngine,
    augment_per_photo: int,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
) -> tuple[Dataset, list[dict], list[PhotoProblem]]:
    """Detect, align, augment and embed every photo of the class (cached in model/embeddings.npz)."""
    c = school.load_class(code)
    students = [s for s in c.students if school.photos(code, s)]
    all_photos = [p for s in students for p in school.photos(code, s)]
    key = f"v{CACHE_VERSION}:{augment_per_photo}:{engine.model_info('embedder')['sha256']}:{_photo_key(all_photos)}"
    cache = school.model_dir(code) / "embeddings.npz"
    problems: list[PhotoProblem] = []
    student_rows = [{"id": s.id, "name": s.name} for s in students]

    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        if str(z["key"]) == key:
            ds = Dataset(z["emb"], z["label"], z["group"], len(students))
            probs = [PhotoProblem(*row) for row in z["problems"].tolist()] if "problems" in z else []
            return ds, student_rows, probs

    rng = np.random.default_rng(1234)
    embs, labels, groups, is_aug = [], [], [], []
    total = max(1, len(all_photos))
    done = 0
    gid = 0
    for si, s in enumerate(students):
        for photo in school.photos(code, s):
            if cancel and cancel():
                raise Cancelled()
            img = cv2.imdecode(np.fromfile(str(photo), dtype=np.uint8), cv2.IMREAD_COLOR)
            done += 1
            if img is None:
                problems.append(PhotoProblem(s.name, photo.name, "cannot read the file"))
                continue
            faces = engine.detect(img)
            if not faces:
                problems.append(PhotoProblem(s.name, photo.name, "no face found"))
                continue
            crop = norm_crop(img, faces[0].kps)
            crops = [crop] + [augment(crop, rng) for _ in range(augment_per_photo)]
            e = engine.embedder.embed(crops)
            embs.append(e)
            labels.extend([si] * len(crops))
            groups.extend([gid] * len(crops))
            is_aug.extend([0] + [1] * augment_per_photo)
            gid += 1
            if progress:
                progress(f"Reading photos of {s.name}", done / total)
    emb = np.concatenate(embs) if embs else np.zeros((0, 512), np.float32)
    ds = Dataset(emb.astype(np.float32), np.array(labels, np.int64), np.array(groups, np.int64), len(students))
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache,
        key=np.array(key),
        emb=ds.emb,
        label=ds.label,
        group=ds.group,
        aug=np.array(is_aug, np.int8),
        ids=np.array([s.id for s in students]),
        problems=np.array([[p.student, p.photo, p.problem] for p in problems] or np.zeros((0, 3)), dtype=str),
    )
    return ds, student_rows, problems


def stranger_embeddings(school: School, exclude: str, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Embeddings of students from the other classes (from their caches)."""
    embs, groups = [], []
    offset = 0
    for code in school.class_codes():
        if code == exclude:
            continue
        cache = school.model_dir(code) / "embeddings.npz"
        if not cache.exists():
            continue
        z = np.load(cache, allow_pickle=False)
        embs.append(z["emb"])
        groups.append(z["group"] + offset)
        offset += int(z["group"].max()) + 1 if len(z["group"]) else 0
    if not embs:
        return np.zeros((0, 512), np.float32), np.zeros((0,), np.int64)
    emb = np.concatenate(embs)
    grp = np.concatenate(groups)
    if len(emb) > MAX_STRANGERS:
        idx = rng.choice(len(emb), MAX_STRANGERS, replace=False)
        emb, grp = emb[idx], grp[idx]
    return emb.astype(np.float32), grp.astype(np.int64)


def school_centroids(school: School) -> dict[str, np.ndarray]:
    """Average face of every student who has cached embeddings (for the look-alike check)."""
    out = {}
    for code in school.class_codes():
        cache = school.model_dir(code) / "embeddings.npz"
        if not cache.exists():
            continue
        z = np.load(cache, allow_pickle=False)
        if "ids" not in z:
            continue
        ids, emb, label, aug = z["ids"], z["emb"], z["label"], z["aug"]
        names = {s.id: s.name for s in school.load_class(code).students}
        for i, sid in enumerate(ids.tolist()):
            sel = emb[(label == i) & (aug == 0)]
            if len(sel):
                out[f"{code} · {names.get(sid, sid)}"] = sel.mean(axis=0)
    return out


def train_and_save(
    school: School, code: str, engine: FaceEngine, progress: ProgressFn | None = None, cancel: CancelFn | None = None
) -> dict:
    """Build embeddings, train, and write model/class-model.json + model/report.json."""
    started = time.time()
    st = school.settings
    log.info("Training %s on %s", code, engine.device)
    cfg = TrainConfig(epochs=st.epochs, folds=st.folds, seeds=st.seeds, min_accuracy=st.min_accuracy)

    def sub(lo, hi):
        return (lambda msg, f: progress(msg, lo + (hi - lo) * f)) if progress else None

    ds, students, problems = build_class_embeddings(school, code, engine, st.augment_per_photo, sub(0.0, 0.4), cancel)
    if ds.num_students == 0 or len(ds.emb) == 0:
        raise ValueError("No usable photos in this class yet. Capture photos first.")
    if ds.num_students == 1:
        raise ValueError("At least two students with photos are needed to train a class model.")
    ds.neg, ds.neg_group = stranger_embeddings(school, code, np.random.default_rng(7))
    log.info("%s: %d students, %d samples, %d strangers", code, ds.num_students, len(ds.emb), len(ds.neg))
    result = train_class(ds, cfg, sub(0.4, 1.0), cancel)

    model = classmodel.build(
        class_code=code,
        students=students,
        weights=result.weights,
        thresholds={"accept": round(result.accept, 4), "strong": round(result.strong, 4), "margin": result.margin},
        metrics={k: v for k, v in result.metrics.items() if k != "method_scores"},
        method=result.method,
        models={"detector": engine.model_info("detector"), "embedder": engine.model_info("embedder")},
        created_at=now_iso(),
        studio_version=__version__,
    )
    classmodel.write(school.model_dir(code) / "class-model.json", model)

    photo_counts = {s["id"]: 0 for s in students}
    groups_per_student: dict[int, set] = {}
    for lbl, grp in zip(ds.label.tolist(), ds.group.tolist(), strict=True):
        groups_per_student.setdefault(lbl, set()).add(grp)
    for i, s in enumerate(students):
        photo_counts[s["id"]] = len(groups_per_student.get(i, ()))

    lookalikes = [
        {"a": a, "b": b, "similarity": round(sim, 3)} for a, b, sim in find_lookalikes(school_centroids(school))
    ]
    report = {
        "class_code": code,
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
        "students": [
            {
                "id": s["id"],
                "name": s["name"],
                "photos": photo_counts[s["id"]],
                "recall": round(result.per_student_recall[i], 4) if i < len(result.per_student_recall) else None,
            }
            for i, s in enumerate(students)
        ],
        "weak_students": [
            s["name"]
            for i, s in enumerate(students)
            if i < len(result.per_student_recall) and result.per_student_recall[i] < 0.9
        ],
        "photo_problems": [p.__dict__ for p in problems],
        "lookalikes": lookalikes,
        "strangers_used": int(len(ds.neg)),
        "passed": bool(result.metrics.get("passed")),
    }
    (school.model_dir(code) / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(
        "Trained %s: accuracy %.3f on %s in %.0f s",
        code,
        result.metrics["accuracy"],
        report["device"],
        report["duration_s"],
    )
    return report
