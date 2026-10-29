"""Model registry, one-time download and ONNX Runtime sessions.

The face models are not shipped inside the installer (their licence is
non-commercial research only), so Studio downloads them once from the official
source and checks each file against a pinned SHA-256.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import onnxruntime as ort

from ..logs import get_logger

log = get_logger("models")

BUFFALO_L_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
BUFFALO_L_SHA256 = "80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f"

RTMO_S_URL = (
    "https://download.openmmlab.com/mmpose/v1/projects/rtmo/onnx_sdk/"
    "rtmo-s_8xb32-600e_body7-640x640-dac2bf74_20231211.zip"
)


@dataclass(frozen=True)
class ModelFile:
    key: str
    filename: str
    sha256: str | None  # None = not pinned yet (hash recorded on first download)
    purpose: str
    required: bool  # required for enrolment/training on the laptop
    for_board: bool  # copied to the USB for the boards


MODELS: dict[str, ModelFile] = {
    "detector": ModelFile(
        "detector",
        "det_10g.onnx",
        "5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91",
        "Face detection (SCRFD-10G) with 5 landmarks",
        True,
        True,
    ),
    "embedder": ModelFile(
        "embedder",
        "w600k_r50.onnx",
        "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43",
        "Face recognition (ArcFace R50, 512-d)",
        True,
        True,
    ),
    "landmarks": ModelFile(
        "landmarks",
        "2d106det.onnx",
        "f001b856447c413801ef5c42091ed0cd516fcd21f2d6b79635b1e733a7109dbf",
        "106 face landmarks (blink check while capturing)",
        True,
        False,
    ),
    "pose": ModelFile(
        "pose",
        "rtmo-s.onnx",
        None,
        "Body pose (RTMO-s) for the board's stick figures and head count",
        False,
        True,
    ),
}

BUFFALO_MEMBERS = {"det_10g.onnx", "w600k_r50.onnx", "2d106det.onnx"}

ProgressFn = Callable[[str, float], None]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def model_path(models_dir: Path, key: str) -> Path:
    return models_dir / MODELS[key].filename


def missing_models(models_dir: Path, include_optional: bool = False) -> list[str]:
    out = []
    for key, m in MODELS.items():
        if not (m.required or include_optional):
            continue
        p = models_dir / m.filename
        if not p.exists():
            out.append(key)
    return out


def verify_models(models_dir: Path) -> dict[str, str]:
    """Return {key: 'ok' | 'missing' | 'bad checksum'} for every model."""
    result = {}
    for key, m in MODELS.items():
        p = models_dir / m.filename
        if not p.exists():
            result[key] = "missing"
        elif m.sha256 and sha256_file(p) != m.sha256:
            result[key] = "bad checksum"
        else:
            result[key] = "ok"
    return result


def _download(url: str, progress: ProgressFn | None, label: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SSAS-Studio"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            buf.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(label, done / total)
        return buf.getvalue()


def download_models(models_dir: Path, progress: ProgressFn | None = None, include_pose: bool = True) -> None:
    """Download the face pack (and optionally the pose model) into ``models_dir``."""
    models_dir.mkdir(parents=True, exist_ok=True)
    need_buffalo = any(not (models_dir / f).exists() for f in BUFFALO_MEMBERS)
    if need_buffalo:
        data = _download(BUFFALO_L_URL, progress, "Face models")
        if hashlib.sha256(data).hexdigest() != BUFFALO_L_SHA256:
            raise RuntimeError("Downloaded face models failed the checksum check. Please try again.")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                base = os.path.basename(name)
                if base in BUFFALO_MEMBERS:
                    tmp = models_dir / (base + ".part")
                    with z.open(name) as src, open(tmp, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    tmp.replace(models_dir / base)
    if include_pose and not (models_dir / MODELS["pose"].filename).exists():
        data = _download(RTMO_S_URL, progress, "Body pose model")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            onnx_names = [n for n in z.namelist() if n.endswith(".onnx")]
            if not onnx_names:
                raise RuntimeError("The pose model archive did not contain an ONNX file.")
            tmp = models_dir / "rtmo-s.onnx.part"
            with z.open(onnx_names[0]) as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst)
            tmp.replace(models_dir / MODELS["pose"].filename)


def available_providers() -> list[str]:
    return ort.get_available_providers()


def make_session(path: Path, prefer_gpu: bool = True, threads: int = 0) -> ort.InferenceSession:
    """Create an ONNX Runtime session; uses the GPU (DirectML/CUDA) when available."""
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.log_severity_level = 3  # errors only (the embedder warns about its fixed batch size)
    if threads:
        opts.intra_op_num_threads = threads
    providers: list[str] = []
    avail = ort.get_available_providers()
    if prefer_gpu:
        for p in ("CUDAExecutionProvider", "DmlExecutionProvider"):
            if p in avail:
                providers.append(p)
    providers.append("CPUExecutionProvider")
    if "DmlExecutionProvider" in providers:
        # DirectML requires these settings.
        opts.enable_mem_pattern = False
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    try:
        return ort.InferenceSession(str(path), sess_options=opts, providers=providers)
    except Exception:
        if providers == ["CPUExecutionProvider"]:
            raise
        log.exception("Could not open %s on the GPU; using the CPU", Path(path).name)
        return make_session(path, prefer_gpu=False, threads=threads)


def gpu_name(session: ort.InferenceSession) -> str:
    used = session.get_providers()[0]
    return {
        "DmlExecutionProvider": "GPU (DirectML)",
        "CUDAExecutionProvider": "GPU (CUDA)",
    }.get(used, "CPU")
