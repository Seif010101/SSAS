from ssas_studio.core.capture_logic import RING_SEGMENTS, CaptureSession
from ssas_studio.core.student_capture import AutoStart, Measurement, StudentCapture


def _look(seg, scale=1.0):
    """Pose (camera space) that points at a ring segment."""
    dy, dp = CaptureSession.segment_vector(seg)
    return -dy * scale, dp * scale


def _blink(s):
    for _ in range(15):
        s.update([200], 0, 0, 0.3, None)
    s.update([200], 0, 0, 0.05, None)  # eyes closed
    s.update([200], 0, 0, 0.3, None)  # open again


def test_default_is_forty_photos_in_eight_parts():
    s = CaptureSession()
    assert RING_SEGMENTS == 8 and s.total_photos == 40


def test_free_sweep_fills_every_part_wherever_the_nose_points():
    s = CaptureSession(photos_per_segment=2, front_photos=3)
    assert s.phase == "front"
    for _ in range(3):
        assert s.update([200], 0, 0, 0.3, None).save
    assert s.phase == "ring" and s.current_target is None
    # Straight ahead no longer counts once the front photos are done.
    assert not s.update([200], 0, 0, 0.3, None).save
    # Parts fill in any order: go round backwards.
    for seg in reversed(range(RING_SEGMENTS)):
        for _ in range(2):
            fb = s.update([200], *_look(seg), 0.3, None)
            assert fb.save and fb.target == seg
    assert s.segments_done == RING_SEGMENTS and s.phase == "blink"
    # A full part is not saved again.
    assert not s.update([200], *_look(3), 0.3, None).save
    assert s.saved_photos == s.total_photos
    assert not s.finished
    _blink(s)
    assert s.blink_done and s.finished and s.phase == "done"


def test_blink_at_any_time_is_enough():
    s = CaptureSession(photos_per_segment=1, front_photos=1)
    _blink(s)  # blinking while still looking straight
    assert s.blink_done
    s.update([200], 0, 0, 0.3, None)
    for seg in range(RING_SEGMENTS):
        s.update([200], *_look(seg), 0.3, None)
    assert s.finished


def test_a_second_person_or_bad_quality_blocks_saving():
    s = CaptureSession(photos_per_segment=2, front_photos=2)
    fb = s.update([200, 150], 0, 0, 0.3, None)
    assert fb.blocked and "one person" in fb.message
    fb = s.update([200, 40], 0, 0, 0.3, None)  # a small face far behind is fine
    assert fb.save and s.front_saved == 1
    fb = s.update([200], 0, 0, 0.3, "Too dark — add light")
    assert fb.blocked and not fb.save
    fb = s.update([], None, None, None, None)
    assert fb.blocked


def test_strict_mode_follows_the_random_order():
    s = CaptureSession(photos_per_segment=2, front_photos=2, strict_order=True, seed=4)
    for _ in range(2):
        s.update([200], 0, 0, 0.3, None)
    target = s.current_target
    assert target is not None
    wrong = (target + RING_SEGMENTS // 2) % RING_SEGMENTS
    fb = s.update([200], *_look(wrong), 0.3, None)
    assert not fb.save and fb.target == target
    while s.current_target is not None:
        t = s.current_target
        assert s.update([200], *_look(t), 0.3, None).save
    assert s.saved_photos == s.total_photos
    assert not s.finished
    _blink(s)
    assert s.finished


def test_order_is_random_per_session():
    orders = {tuple(CaptureSession(strict_order=True, seed=i).order) for i in range(5)}
    assert len(orders) > 1


def test_segment_at():
    assert CaptureSession.segment_at(0, 0) is None  # straight
    assert CaptureSession.segment_at(60, 0) is None  # turned away too far
    for seg in range(RING_SEGMENTS):
        dy, dp = CaptureSession.segment_vector(seg)
        assert CaptureSession.segment_at(dy, dp) == seg


def test_auto_start_needs_one_steady_face_and_the_previous_one_to_leave():
    a = AutoStart(hold_s=1.0, absent_s=0.5)
    assert a.update([], 0.0) == (0.0, False)
    assert a.update([200], 0.1) == (0.0, False)
    frac, ready = a.update([200], 0.6)
    assert 0 < frac < 1 and not ready
    assert a.update([200], 1.2)[1]
    # Two people, or a face that is too small, restarts the hold.
    b = AutoStart()
    b.update([200], 0.0)
    assert b.update([200, 180], 0.5) == (0.0, False)
    assert b.update([200], 0.6) == (0.0, False)
    assert b.update([60], 1.0) == (0.0, False)
    # After a finished student the same face does not start another capture.
    c = AutoStart()
    c.rearm()
    assert c.update([200], 0.0) == (0.0, False)
    assert c.update([200], 5.0) == (0.0, False)
    c.update([], 5.1)
    c.update([], 5.7)  # gone long enough
    c.update([200], 5.8)
    assert c.update([200], 7.0)[1]


# ----- StudentCapture: the whole hands-free flow without a camera -----

GOOD = Measurement(0.0, 0.0, 0.3, None)


def _capture(**kw):
    return StudentCapture(
        lambda: CaptureSession(photos_per_segment=1, front_photos=1, require_blink=False),
        save_interval_s=0.0,
        done_shown_s=1.0,
        give_up_s=5.0,
        auto_start=AutoStart(hold_s=0.5, absent_s=0.3),
        stamp=lambda: "S",
        **kw,
    )


def _measure_for(seg):
    dy, dp = CaptureSession.segment_vector(seg)
    return lambda: Measurement(-dy, dp, 0.3, None)


def test_no_student_chosen_means_idle():
    c = _capture()
    assert c.step([200], 0.0, lambda: GOOD).state == "idle"


def test_waits_for_a_steady_face_then_captures_and_finishes():
    c = _capture()
    c.set_student("Ahmed")
    r = c.step([], 0.0, lambda: GOOD)
    assert r.state == "waiting" and "step in" in r.message and r.name == "Ahmed"
    assert c.step([200], 0.1, lambda: GOOD).state == "waiting"
    r = c.step([200], 0.7, lambda: GOOD)  # steady for long enough: capturing starts in the same frame
    assert r.state == "capturing" and r.save_as == "S-001-front.jpg" and r.total == 1 + RING_SEGMENTS
    names = [r.save_as]
    now = 0.8
    for seg in range(RING_SEGMENTS):
        r = c.step([200], now, _measure_for(seg))
        names.append(r.save_as)
        now += 0.1
    assert names[1:] == [f"S-{i + 2:03d}-seg{seg:02d}.jpg" for i, seg in enumerate(range(RING_SEGMENTS))]
    assert r.student_done and r.state == "done" and c.name is None
    # "Done" stays on for a moment, then the camera waits for the next student.
    assert c.step([200], now + 0.5, lambda: GOOD).state == "done"
    c.set_student("Omar")
    r = c.step([200], now + 1.5, lambda: GOOD)
    assert r.state == "waiting" and "step in" in r.message  # the same face must leave first


def test_saves_are_throttled_and_the_count_stays_in_sync():
    c = StudentCapture(
        lambda: CaptureSession(photos_per_segment=2, front_photos=3, require_blink=False),
        save_interval_s=1.0,
        auto_start=AutoStart(hold_s=0.0, absent_s=0.0),
    )
    c.set_student("Ahmed")
    first = c.step([200], 0.0, lambda: GOOD)
    assert first.save_as and first.saved == 1
    too_soon = c.step([200], 0.2, lambda: GOOD)
    assert too_soon.save_as is None and too_soon.saved == 1  # not counted, will be taken again
    assert c.step([200], 1.5, lambda: GOOD).saved == 2


def test_skip_and_walking_away_go_back_to_waiting():
    c = _capture()
    c.set_student("Ahmed")
    c.step([200], 0.0, lambda: GOOD)
    assert c.step([200], 0.6, lambda: GOOD).state == "capturing"
    c.skip()
    assert c.step([200], 0.7, lambda: GOOD).state == "waiting"
    c = _capture()
    c.set_student("Ahmed")
    c.step([200], 0.0, lambda: GOOD)
    assert c.step([200], 0.6, lambda: GOOD).state == "capturing"
    r = c.step([], 6.0, lambda: GOOD)  # nobody for longer than give_up_s
    assert r.state == "waiting" and not c.capturing


def test_a_second_person_blocks_but_does_not_save():
    c = _capture()
    c.set_student("Ahmed")
    c.step([200], 0.0, lambda: GOOD)
    c.step([200], 0.6, lambda: GOOD)
    r = c.step([200, 190], 0.7, lambda: GOOD)
    assert r.blocked and r.save_as is None


def test_changing_the_student_mid_capture_abandons_it():
    c = _capture()
    c.set_student("Ahmed")
    c.step([200], 0.0, lambda: GOOD)
    assert c.step([200], 0.6, lambda: GOOD).state == "capturing"
    c.set_student("Omar")
    r = c.step([200], 0.7, lambda: GOOD)
    assert r.state == "waiting" and r.name == "Omar" and r.save_as is None
