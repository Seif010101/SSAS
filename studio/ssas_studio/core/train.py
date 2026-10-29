"""Train one recognition model per class.

The face embedder (ArcFace) is fixed. What we train for each class is a small
"head": one direction per student in the 512-d embedding space, learned with a
margin loss over thousands of augmented photos for many epochs, while photos of
students from *other* classes are pushed away so the board rejects strangers.

Quality is measured with grouped K-fold cross-validation (all variants of one
photo stay in the same fold) repeated with several random seeds, and the
acceptance threshold is calibrated so strangers are accepted at most
``far_target`` of the time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

ProgressFn = Callable[[str, float], None]
CancelFn = Callable[[], bool]


class Cancelled(Exception):
    pass


@dataclass
class TrainConfig:
    epochs: int = 200
    folds: int = 5
    seeds: int = 3
    scale: float = 30.0
    margin: float = 0.2
    lr: float = 0.01
    batch: int = 1024
    neg_weight: float = 1.0
    neg_target: float = 0.25
    far_target: float = 0.001
    decision_margin: float = 0.05
    min_accuracy: float = 0.98


@dataclass
class Dataset:
    emb: np.ndarray  # (N, 512) unit vectors
    label: np.ndarray  # (N,) student index
    group: np.ndarray  # (N,) photo id — augmentations of one photo share it
    num_students: int
    neg: np.ndarray = field(default_factory=lambda: np.zeros((0, 512), np.float32))  # strangers
    neg_group: np.ndarray = field(default_factory=lambda: np.zeros((0,), np.int64))


@dataclass
class TrainResult:
    method: str  # "head" or "prototype"
    weights: np.ndarray  # (S, 512) unit vectors, row i = student i
    accept: float
    strong: float
    margin: float
    metrics: dict
    per_student_recall: list[float]


def _normalize(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=-1, keepdims=True).clip(min=1e-12)


def class_means(emb: np.ndarray, label: np.ndarray, s: int) -> np.ndarray:
    w = np.zeros((s, emb.shape[1]), np.float64)
    for i in range(s):
        sel = emb[label == i]
        if len(sel):
            w[i] = sel.mean(axis=0)
    return _normalize(w).astype(np.float32)


def train_head(
    x: np.ndarray,
    y: np.ndarray,
    s: int,
    neg: np.ndarray,
    cfg: TrainConfig,
    seed: int,
    tick: Callable[[], None] | None = None,
) -> np.ndarray:
    """Cosine classifier with additive margin (CosFace) + a stranger-rejection term. Adam, numpy only."""
    rng = np.random.default_rng(seed)
    x = x.astype(np.float32)
    w = class_means(x, y, s).astype(np.float64) + rng.normal(0, 0.01, (s, x.shape[1]))
    m_t = np.zeros_like(w)
    v_t = np.zeros_like(w)
    b1, b2, eps = 0.9, 0.999, 1e-8
    step = 0
    n = len(x)
    batch = min(cfg.batch, n)
    eye = np.eye(s, dtype=np.float32)
    for _epoch in range(cfg.epochs):
        perm = rng.permutation(n)
        for start in range(0, n, batch):
            idx = perm[start : start + batch]
            xb, yb = x[idx], y[idx]
            norm = np.linalg.norm(w, axis=1, keepdims=True).clip(min=1e-12)
            wn = (w / norm).astype(np.float32)

            c = xb @ wn.T
            logits = cfg.scale * c
            logits[np.arange(len(yb)), yb] -= cfg.scale * cfg.margin
            logits -= logits.max(axis=1, keepdims=True)
            p = np.exp(logits)
            p /= p.sum(axis=1, keepdims=True)
            d_c = cfg.scale * (p - eye[yb]) / len(yb)
            d_wn = d_c.T @ xb

            if len(neg) and cfg.neg_weight > 0:
                nb = neg[rng.integers(0, len(neg), size=min(len(neg), batch))]
                cn = nb @ wn.T
                j = cn.argmax(axis=1)
                viol = np.maximum(0.0, cn[np.arange(len(nb)), j] - cfg.neg_target)
                if viol.any():
                    d_cn = np.zeros_like(cn)
                    d_cn[np.arange(len(nb)), j] = 2 * cfg.neg_weight * viol / len(nb)
                    d_wn += d_cn.T @ nb

            d_wn = d_wn.astype(np.float64)
            wn64 = wn.astype(np.float64)
            g = (d_wn - wn64 * (d_wn * wn64).sum(axis=1, keepdims=True)) / norm

            step += 1
            m_t = b1 * m_t + (1 - b1) * g
            v_t = b2 * v_t + (1 - b2) * g * g
            m_hat = m_t / (1 - b1**step)
            v_hat = v_t / (1 - b2**step)
            w -= cfg.lr * m_hat / (np.sqrt(v_hat) + eps)
        if tick:
            tick()
    return _normalize(w).astype(np.float32)


def _scores(w: np.ndarray, x: np.ndarray) -> np.ndarray:
    return x @ w.T


def _top2(c: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    order = np.argsort(-c, axis=1)
    top_i = order[:, 0]
    top = c[np.arange(len(c)), top_i]
    second = c[np.arange(len(c)), order[:, 1]] if c.shape[1] > 1 else np.full(len(c), -1.0)
    return top_i, top, second


def _grouped_folds(group: np.ndarray, k: int, seed: int) -> list[np.ndarray]:
    uniq = np.unique(group)
    rng = np.random.default_rng(seed)
    rng.shuffle(uniq)
    fold_of = {g: i % k for i, g in enumerate(uniq)}
    f = np.array([fold_of[g] for g in group])
    return [np.where(f == i)[0] for i in range(k)]


@dataclass
class _Pooled:
    genuine: list = field(default_factory=list)  # score of the true student
    within: list = field(default_factory=list)  # best wrong-student score (same class)
    stranger: list = field(default_factory=list)  # best score for a stranger photo
    top_i: list = field(default_factory=list)
    top: list = field(default_factory=list)
    second: list = field(default_factory=list)
    label: list = field(default_factory=list)

    def add(self, w, xv, yv, negv):
        c = _scores(w, xv)
        ti, top, second = _top2(c)
        self.genuine.append(c[np.arange(len(yv)), yv])
        masked = c.copy()
        masked[np.arange(len(yv)), yv] = -np.inf
        self.within.append(masked.max(axis=1) if c.shape[1] > 1 else np.full(len(yv), -1.0))
        if len(negv):
            self.stranger.append(_scores(w, negv).max(axis=1))
        self.top_i.append(ti)
        self.top.append(top)
        self.second.append(second)
        self.label.append(yv)

    def cat(self, name):
        parts = getattr(self, name)
        return np.concatenate(parts) if parts else np.zeros((0,))


def _calibrate(pooled: _Pooled, cfg: TrainConfig) -> tuple[float, float, dict, list[float]]:
    within = pooled.cat("within")
    stranger = pooled.cat("stranger")
    impostor = np.concatenate([within, stranger]) if len(stranger) else within
    accept = float(np.quantile(impostor, 1 - cfg.far_target)) if len(impostor) else 0.3
    accept = max(accept, 0.2)
    strong = float(max(impostor.max() if len(impostor) else 0.4, accept) + 0.02)

    ti, top, second, y = (pooled.cat(n) for n in ("top_i", "top", "second", "label"))
    ti = ti.astype(int)
    y = y.astype(int)
    accepted = (top >= accept) & (top - second >= cfg.decision_margin)
    correct = accepted & (ti == y)
    wrong = accepted & (ti != y)
    metrics = {
        "accuracy": float(correct.mean()) if len(y) else 0.0,
        "wrong_student_rate": float(wrong.mean()) if len(y) else 0.0,
        "stranger_accept_rate": float((stranger >= accept).mean()) if len(stranger) else None,
        "samples": int(len(y)),
        "stranger_samples": int(len(stranger)),
    }
    s = int(y.max()) + 1 if len(y) else 0
    recall = [float(correct[y == i].mean()) if (y == i).any() else 0.0 for i in range(s)]
    return accept, strong, metrics, recall


def cross_validate(
    ds: Dataset,
    cfg: TrainConfig,
    method: str,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
    done_units: list[int] | None = None,
    total_units: int = 1,
) -> tuple[float, float, dict, list[float]]:
    pooled = _Pooled()
    seeds = cfg.seeds if method == "head" else 1
    for seed in range(seeds):
        folds = _grouped_folds(ds.group, cfg.folds, seed)
        neg_folds = _grouped_folds(ds.neg_group, cfg.folds, seed) if len(ds.neg) else [np.zeros(0, int)] * cfg.folds
        for k in range(cfg.folds):
            val = folds[k]
            if len(val) == 0:
                continue
            train = np.setdiff1d(np.arange(len(ds.emb)), val)
            neg_val = neg_folds[k]
            neg_train = np.setdiff1d(np.arange(len(ds.neg)), neg_val)

            def tick(seed=seed, k=k):
                if cancel and cancel():
                    raise Cancelled()
                if done_units is not None:
                    done_units[0] += 1
                    if progress:
                        progress(
                            f"Cross-validation ({method}), seed {seed + 1}, fold {k + 1}", done_units[0] / total_units
                        )

            if method == "head":
                w = train_head(
                    ds.emb[train], ds.label[train], ds.num_students, ds.neg[neg_train], cfg, seed * 100 + k, tick
                )
            else:
                w = class_means(ds.emb[train], ds.label[train], ds.num_students)
                tick()
            pooled.add(w, ds.emb[val], ds.label[val], ds.neg[neg_val])
    return _calibrate(pooled, cfg)


def train_class(
    ds: Dataset, cfg: TrainConfig, progress: ProgressFn | None = None, cancel: CancelFn | None = None
) -> TrainResult:
    """Cross-validate both methods, keep the better one, then train it on all photos."""
    if ds.num_students < 1:
        raise ValueError("The class has no students with usable photos.")
    total = cfg.seeds * cfg.folds * cfg.epochs + cfg.folds + cfg.seeds * cfg.epochs
    done = [0]
    head_cv = cross_validate(ds, cfg, "head", progress, cancel, done, total)
    proto_cv = cross_validate(ds, cfg, "prototype", progress, cancel, done, total)

    def score(cv):
        return cv[2]["accuracy"] - cv[2]["wrong_student_rate"] * 5

    method, (accept, strong, metrics, recall) = (
        ("head", head_cv) if score(head_cv) >= score(proto_cv) else ("prototype", proto_cv)
    )

    if method == "head":
        runs = []
        for seed in range(cfg.seeds):

            def tick(seed=seed):
                if cancel and cancel():
                    raise Cancelled()
                done[0] += 1
                if progress:
                    progress(f"Final training, round {seed + 1} of {cfg.seeds}", done[0] / total)

            runs.append(train_head(ds.emb, ds.label, ds.num_students, ds.neg, cfg, 10_000 + seed, tick))
        weights = _normalize(np.mean(runs, axis=0)).astype(np.float32)
    else:
        weights = class_means(ds.emb, ds.label, ds.num_students)
    if progress:
        progress("Done", 1.0)

    metrics = dict(metrics)
    metrics["method_scores"] = {
        "head": dict(head_cv[2]),
        "prototype": dict(proto_cv[2]),
    }
    metrics["passed"] = metrics["accuracy"] >= cfg.min_accuracy
    return TrainResult(method, weights, accept, strong, cfg.decision_margin, metrics, recall)


def find_lookalikes(centroids: dict[str, np.ndarray], threshold: float = 0.6) -> list[tuple[str, str, float]]:
    """Pairs of students (anywhere in the school) whose average faces are suspiciously similar."""
    keys = list(centroids)
    if len(keys) < 2:
        return []
    m = _normalize(np.stack([centroids[k] for k in keys]))
    sim = m @ m.T
    out = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if sim[i, j] >= threshold:
                out.append((keys[i], keys[j], float(sim[i, j])))
    return sorted(out, key=lambda t: -t[2])
