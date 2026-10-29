import cv2
import numpy as np
from conftest import needs_face_models

from ssas_studio.core.align import norm_crop
from ssas_studio.core.detect import FaceDetector, detect_size_for
from ssas_studio.core.embed import FaceEmbedder
from ssas_studio.core.landmarks import LandmarkModel, eye_openness, head_pose
from ssas_studio.core.models import make_session


@needs_face_models
def test_detect_align_embed(models_dir, astronaut_bgr, cameraman_bgr):
    det = FaceDetector(make_session(models_dir / "det_10g.onnx"))
    emb = FaceEmbedder(make_session(models_dir / "w600k_r50.onnx"))

    faces = det.detect(astronaut_bgr, detect_size_for(astronaut_bgr.shape))
    assert len(faces) == 1
    f = faces[0]
    assert f.score > 0.7
    assert 150 < f.box[0] < 210 and 230 < f.box[2] < 300  # face is in the expected place
    assert f.kps[0, 0] < f.kps[1, 0]  # left eye is left of right eye

    crop = norm_crop(astronaut_bgr, f.kps)
    assert crop.shape == (112, 112, 3)
    e = emb.embed([crop, cv2.flip(crop, 1)])
    assert e.shape == (2, 512)
    np.testing.assert_allclose(np.linalg.norm(e, axis=1), 1.0, atol=1e-5)
    assert float(e[0] @ e[1]) > 0.85  # mirror image is the same person

    other = det.detect(cameraman_bgr)[0]
    e2 = emb.embed([norm_crop(cameraman_bgr, other.kps)])
    assert float(e[0] @ e2[0]) < 0.3  # a different person


@needs_face_models
def test_detector_finds_small_faces_in_a_big_frame(models_dir, astronaut_bgr):
    """A 'back row' face: the astronaut shrunk to ~30 px in a 1920x1080 frame."""
    det = FaceDetector(make_session(models_dir / "det_10g.onnx"))
    small = cv2.resize(astronaut_bgr, (160, 160), interpolation=cv2.INTER_AREA)
    frame = np.full((1080, 1920, 3), 90, np.uint8)
    frame[700:860, 1500:1660] = small
    faces = det.detect(frame, (1920, 1088))
    assert len(faces) >= 1
    assert 1500 < faces[0].box[0] < 1600


@needs_face_models
def test_landmarks_and_pose(models_dir, astronaut_bgr):
    det = FaceDetector(make_session(models_dir / "det_10g.onnx"))
    lm = LandmarkModel(make_session(models_dir / "2d106det.onnx"))
    f = det.detect(astronaut_bgr)[0]
    pts = lm.predict(astronaut_bgr, f.box)
    assert pts.shape == (106, 2)
    assert 0.05 < eye_openness(pts) < 0.8
    yaw, pitch = head_pose(f.kps)
    assert abs(yaw) < 25 and abs(pitch) < 30
    # Mirroring the image flips the sign of the yaw.
    flipped = cv2.flip(astronaut_bgr, 1)
    yaw2, _ = head_pose(det.detect(flipped)[0].kps)
    assert np.sign(yaw2) != np.sign(yaw) or abs(yaw) < 2
