import numpy as np
from skimage.transform import SimilarityTransform

from ssas_studio.core.align import ARCFACE_DST, similarity_transform


def test_similarity_transform_matches_skimage():
    rng = np.random.default_rng(0)
    for _ in range(20):
        src = ARCFACE_DST * rng.uniform(0.5, 3) + rng.uniform(-50, 300, size=2) + rng.normal(0, 2, (5, 2))
        ours = similarity_transform(src, ARCFACE_DST)
        if hasattr(SimilarityTransform, "from_estimate"):
            ref = SimilarityTransform.from_estimate(src, ARCFACE_DST)
        else:
            ref = SimilarityTransform()
            ref.estimate(src, ARCFACE_DST)
        np.testing.assert_allclose(ours, ref.params[:2], atol=1e-6)


def test_identity_when_points_already_aligned():
    m = similarity_transform(ARCFACE_DST, ARCFACE_DST)
    np.testing.assert_allclose(m, [[1, 0, 0], [0, 1, 0]], atol=1e-9)
