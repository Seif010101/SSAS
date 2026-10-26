import numpy as np

from ssas_studio.core.train import Dataset, TrainConfig, find_lookalikes, train_class


def _clusters(rng, n_ids, photos, aug, spread=0.045, aug_noise=0.07, offset=0):
    centers = rng.normal(size=(n_ids, 512))
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)
    emb, lab, grp = [], [], []
    g = offset
    for s in range(n_ids):
        for _ in range(photos):
            base = centers[s] + rng.normal(0, spread, 512)
            for a in range(aug + 1):
                e = base + rng.normal(0, aug_noise if a else 0.02, 512)
                emb.append(e / np.linalg.norm(e))
                lab.append(s)
                grp.append(g)
            g += 1
    return np.array(emb, np.float32), np.array(lab), np.array(grp)


def test_training_reaches_high_accuracy_and_rejects_strangers():
    rng = np.random.default_rng(1)
    emb, lab, grp = _clusters(rng, 8, 12, 4)
    neg, _, ngrp = _clusters(rng, 30, 3, 2)
    ds = Dataset(emb, lab, grp, 8, neg, ngrp)
    cfg = TrainConfig(epochs=25, folds=3, seeds=2)
    seen = []
    r = train_class(ds, cfg, progress=lambda m, f: seen.append(f))
    assert r.weights.shape == (8, 512)
    assert r.metrics["accuracy"] >= 0.99
    assert r.metrics["stranger_accept_rate"] <= 0.01
    assert r.accept < r.strong
    assert seen and abs(seen[-1] - 1.0) < 1e-9 and all(0 <= f <= 1.0 + 1e-9 for f in seen)
    # Weights identify a fresh photo of student 3.
    e = emb[lab == 3][0]
    assert int(np.argmax(r.weights @ e)) == 3


def test_lookalikes_flags_near_duplicates():
    a = np.ones(512)
    b = a + 0.01
    c = -a
    pairs = find_lookalikes({"x": a, "y": b, "z": c})
    assert [(p[0], p[1]) for p in pairs] == [("x", "y")]
