import json

import cv2
import numpy as np

from conftest import needs_face_models
from ssas_studio.core import classmodel
from ssas_studio.core.align import norm_crop
from ssas_studio.core.pipeline import FaceEngine, train_and_save
from ssas_studio.core.storage import School


def _variants(img, n, rng):
    """Different 'photos' of one person: shifted, scaled, re-lit crops."""
    h, w = img.shape[:2]
    out = []
    for _ in range(n):
        s = rng.uniform(0.9, 1.1)
        m = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-6, 6), s)
        m[:, 2] += rng.uniform(-15, 15, 2)
        v = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)
        v = np.clip(v.astype(np.float32) * rng.uniform(0.8, 1.2), 0, 255).astype(np.uint8)
        out.append(v)
    return out


@needs_face_models
def test_train_and_save_end_to_end(tmp_path, models_dir, astronaut_bgr, cameraman_bgr):
    school = School(tmp_path)
    st = school.settings
    st.epochs, st.folds, st.seeds, st.augment_per_photo = 15, 3, 1, 3
    school.settings = st
    school.add_class("9A1", 9, "Advanced", 1)
    rng = np.random.default_rng(0)
    for name, img in (("Astronaut", astronaut_bgr), ("Camera Man", cameraman_bgr)):
        s = school.add_student("9A1", name)
        for i, v in enumerate(_variants(img, 6, rng)):
            cv2.imencode(".jpg", v)[1].tofile(str(school.student_dir("9A1", s) / f"p{i:02d}.jpg"))

    engine = FaceEngine(models_dir, prefer_gpu=False)
    report = train_and_save(school, "9A1", engine)
    assert report["passed"], report["metrics"]
    assert [s["photos"] for s in report["students"]] == [6, 6]
    assert not report["photo_problems"]

    model = classmodel.read(school.model_dir("9A1") / "class-model.json")
    assert [s["name"] for s in model["students"]] == ["Astronaut", "Camera Man"]
    assert model["models"]["embedder"]["file"] == "w600k_r50.onnx"

    # The saved model recognises a new, low-resolution picture of the astronaut ...
    face = engine.detect(astronaut_bgr)[0]
    crop = norm_crop(astronaut_bgr, face.kps)
    small = cv2.resize(cv2.resize(crop, (40, 40), interpolation=cv2.INTER_AREA), (112, 112))
    e = engine.embedder.embed([crop, small])
    ids = [r[0] for r in classmodel.identify(model, e)]
    assert ids == ["9A1-001", "9A1-001"]

    # ... and the cache is reused on the second run.
    cache = school.model_dir("9A1") / "embeddings.npz"
    mtime = cache.stat().st_mtime
    train_and_save(school, "9A1", engine)
    assert cache.stat().st_mtime == mtime
    assert json.loads((school.model_dir("9A1") / "report.json").read_text(encoding="utf-8"))["class_code"] == "9A1"
