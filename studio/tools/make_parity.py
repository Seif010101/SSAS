"""Write test fixtures so the board app (Kotlin) can be checked against the Python pipeline.

    python tools/make_parity.py <models dir> <output dir>

Writes astronaut.png, cameraman.png, frame_small_face.png and parity.json.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from skimage import data

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ssas_studio.core import classmodel  # noqa: E402
from ssas_studio.core.align import norm_crop  # noqa: E402
from ssas_studio.core.detect import FaceDetector, detect_size_for  # noqa: E402
from ssas_studio.core.embed import FaceEmbedder  # noqa: E402
from ssas_studio.core.models import make_session  # noqa: E402

models, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
det = FaceDetector(make_session(models / "det_10g.onnx", prefer_gpu=False))
emb = FaceEmbedder(make_session(models / "w600k_r50.onnx", prefer_gpu=False))

astro = cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)
camera = cv2.cvtColor(data.camera(), cv2.COLOR_GRAY2BGR)
frame = np.full((1080, 1920, 3), 90, np.uint8)
frame[700:860, 1500:1660] = cv2.resize(astro, (160, 160), interpolation=cv2.INTER_AREA)
cv2.imwrite(str(out / "astronaut.png"), astro)
cv2.imwrite(str(out / "cameraman.png"), camera)
cv2.imwrite(str(out / "frame_small_face.png"), frame)


def faces_json(img, size):
    return [{"box": f.box.tolist(), "score": f.score, "kps": f.kps.reshape(-1).tolist()} for f in det.detect(img, size)]


a_face = det.detect(astro, (640, 640))[0]
c_face = det.detect(camera, detect_size_for(camera.shape))[0]
a_emb = emb.embed([norm_crop(astro, a_face.kps)])[0]
c_emb = emb.embed([norm_crop(camera, c_face.kps)])[0]
model = classmodel.build(
    "TEST",
    [{"id": "T-001", "name": "Astronaut"}, {"id": "T-002", "name": "Camera Man"}],
    np.stack([a_emb, c_emb]),
    {"accept": 0.3, "strong": 0.6, "margin": 0.05},
    {},
    "prototype",
    {},
    "2026-01-01T00:00:00",
    "test",
)
classmodel.write(out / "class-TEST.json", model)

parity = {
    "astronaut_640": faces_json(astro, (640, 640)),
    "frame_1920": faces_json(frame, (1920, 1088)),
    "astronaut_embedding": a_emb.tolist(),
    "cameraman_embedding": c_emb.tolist(),
}
(out / "parity.json").write_text(json.dumps(parity, indent=1))
print("wrote", sorted(p.name for p in out.iterdir()))
