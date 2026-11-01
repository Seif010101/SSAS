package org.ssas.board.core

/** What one camera frame showed. */
data class FrameObservation(
    val valid: Boolean,
    /** Index of each recognised person in this frame (strong = very confident). */
    val recognised: Map<Int, Boolean> = emptyMap(),
    /** Faces seen but not matched to anyone in the group. */
    val unknownFaces: Int = 0,
    /** Number of bodies found by the pose model, or -1 when there is no pose model. */
    val bodies: Int = -1,
    /** Faces in the frame (recognised + unknown). */
    val faces: Int = 0,
    /** Faces rejected because no body was attached (photo / phone held up). */
    val suspicious: Int = 0,
)

enum class Status { PRESENT, ABSENT, NEEDS_REVIEW, NO_DATA }

data class AttendanceResult(
    val statuses: List<Status>,
    val bestScore: List<Float>,
    val validFrames: Int,
    val totalFrames: Int,
    val unknownMax: Int,
    val suspiciousMax: Int,
)

/**
 * Collects the frames of one start-of-session capture and decides each person's status.
 *
 * PRESENT: recognised in 2 frames, or once with a very confident match.
 * ABSENT: never recognised AND enough good frames AND nobody unexplained in the room.
 * NEEDS_REVIEW: not recognised but there are unexplained faces/bodies, or too few good frames.
 * NO_DATA: the camera gave no usable frame at all.
 */
class AttendanceAggregator(private val numPeople: Int, private val minValidFrames: Int = 3) {
    private val hits = IntArray(numPeople)
    private val strong = BooleanArray(numPeople)
    private val best = FloatArray(numPeople) { -1f }
    private val frames = ArrayList<FrameObservation>()

    fun add(frame: FrameObservation, scores: Map<Int, Float> = emptyMap()) {
        frames.add(frame)
        if (!frame.valid) return
        for ((i, isStrong) in frame.recognised) {
            hits[i]++
            if (isStrong) strong[i] = true
        }
        for ((i, s) in scores) if (s > best[i]) best[i] = s
    }

    fun isPresent(i: Int) = hits[i] >= 2 || strong[i]

    fun allPresent() = (0 until numPeople).all { isPresent(it) }

    val validFrames get() = frames.count { it.valid }

    fun result(): AttendanceResult {
        val valid = frames.filter { it.valid }
        val present = BooleanArray(numPeople) { isPresent(it) }
        // A frame is "unexplained" when it shows more people than the recognised people it contains,
        // beyond what present-but-not-visible people could explain.
        var unexplainedFrames = 0
        var unknownMax = 0
        for (f in valid) {
            val presentNotSeen = (0 until numPeople).count { present[it] && it !in f.recognised }
            val facelessBodies = if (f.bodies >= 0) maxOf(0, f.bodies - f.faces) else 0
            val unexplained = f.unknownFaces + maxOf(0, facelessBodies - presentNotSeen)
            unknownMax = maxOf(unknownMax, unexplained)
            if (unexplained > 0) unexplainedFrames++
        }
        val crowded = valid.isNotEmpty() && unexplainedFrames * 2 >= valid.size
        val statuses = List(numPeople) { i ->
            when {
                present[i] -> Status.PRESENT
                valid.isEmpty() -> Status.NO_DATA
                valid.size < minValidFrames -> Status.NEEDS_REVIEW
                crowded -> Status.NEEDS_REVIEW
                else -> Status.ABSENT
            }
        }
        return AttendanceResult(
            statuses, best.toList(), valid.size, frames.size, unknownMax,
            frames.maxOfOrNull { it.suspicious } ?: 0,
        )
    }
}
