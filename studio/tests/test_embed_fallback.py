import numpy as np
import pytest

from ssas_studio.core.embed import FaceEmbedder


class _Input:
    name = "input"


class _Output:
    name = "output"


class FakeSession:
    """Returns the mean of each crop as a 512-vector so the result tells which crops were really embedded."""

    def __init__(self, fail=False):
        self.fail = fail
        self.batch_sizes = []

    def get_inputs(self):
        return [_Input()]

    def get_outputs(self):
        return [_Output()]

    def run(self, outputs, feeds):
        if self.fail:
            raise RuntimeError("device lost")
        blob = feeds["input"]
        self.batch_sizes.append(len(blob))
        return [np.repeat(blob.reshape(len(blob), -1).mean(axis=1, keepdims=True) + 1.0, 512, axis=1)]


def _crops(n):
    return [np.full((112, 112, 3), i * 10, np.uint8) for i in range(n)]


def test_gpu_batches_are_padded_and_the_padding_is_dropped():
    s = FakeSession()
    e = FaceEmbedder(s, pad_to=8)
    out = e.embed(_crops(3))
    assert out.shape == (3, 512) and s.batch_sizes == [8]


def test_cpu_batches_are_not_padded():
    s = FakeSession()
    FaceEmbedder(s).embed(_crops(3))
    assert s.batch_sizes == [3]


def test_a_failing_gpu_falls_back_to_the_cpu_once():
    cpu = FakeSession()
    e = FaceEmbedder(FakeSession(fail=True), pad_to=8, cpu_fallback=lambda: cpu)
    assert e.embed(_crops(3)).shape == (3, 512)
    assert e.session is cpu and e.pad_to is None and cpu.batch_sizes == [3]
    e.embed(_crops(2))
    assert cpu.batch_sizes == [3, 2]


def test_without_a_fallback_the_error_is_raised():
    with pytest.raises(RuntimeError):
        FaceEmbedder(FakeSession(fail=True)).embed(_crops(1))
