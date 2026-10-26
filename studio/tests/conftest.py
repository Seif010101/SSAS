import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODELS_DIR = Path(os.environ.get("SSAS_MODELS_DIR", Path(__file__).resolve().parents[2] / ".models"))


def have_models(*files: str) -> bool:
    return all((MODELS_DIR / f).exists() for f in files)


needs_face_models = pytest.mark.skipif(
    not have_models("det_10g.onnx", "w600k_r50.onnx"),
    reason=f"face models not found in {MODELS_DIR} (set SSAS_MODELS_DIR)",
)


@pytest.fixture
def models_dir() -> Path:
    return MODELS_DIR


@pytest.fixture
def astronaut_bgr():
    import cv2
    from skimage import data

    return cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)


@pytest.fixture
def cameraman_bgr():
    import cv2
    from skimage import data

    return cv2.cvtColor(data.camera(), cv2.COLOR_GRAY2BGR)
