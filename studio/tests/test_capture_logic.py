from ssas_studio.core.capture_logic import RING_SEGMENTS, CaptureSession


def _look(session, seg):
    """Pose (camera space) that points at a ring segment."""
    dy, dp = CaptureSession.segment_vector(seg)
    return -dy, dp


def test_full_capture_flow_requires_one_person_order_and_blink():
    s = CaptureSession(photos_per_segment=2, front_photos=3, seed=4)
    # A second person blocks everything.
    fb = s.update([200, 150], 0, 0, 0.3, None)
    assert fb.blocked and "one person" in fb.message
    # A small face far behind is fine.
    fb = s.update([200, 40], 0, 0, 0.3, None)
    assert fb.save and s.front_saved == 1
    for _ in range(2):
        s.update([200], 0, 0, 0.3, None)
    assert s.front_saved == 3
    # The prompted segment must be followed; looking elsewhere saves nothing.
    target = s.current_target
    wrong = (target + RING_SEGMENTS // 2) % RING_SEGMENTS
    fb = s.update([200], *_look(s, wrong), 0.3, None)
    assert not fb.save and fb.target == target
    # Bad quality blocks saving.
    fb = s.update([200], *_look(s, target), 0.3, "Too dark — add light")
    assert fb.blocked and not fb.save
    # Follow every prompt (eyes open the whole time).
    while s.current_target is not None:
        t = s.current_target
        assert s.update([200], *_look(s, t), 0.3, None).save
    assert s.saved_photos == s.total_photos
    assert not s.finished  # no blink yet
    for _ in range(15):
        s.update([200], 0, 0, 0.3, None)
    s.update([200], 0, 0, 0.05, None)  # eyes closed
    s.update([200], 0, 0, 0.3, None)  # open again
    assert s.blink_done and s.finished


def test_order_is_random_per_session():
    orders = {tuple(CaptureSession(seed=i).order) for i in range(5)}
    assert len(orders) > 1
