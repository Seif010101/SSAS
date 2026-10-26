package org.ssas.board.core

import kotlin.test.Test
import kotlin.test.assertEquals

class AttendanceTest {
    private fun frame(vararg ids: Int, strong: Boolean = false, unknown: Int = 0, bodies: Int = -1, faces: Int = ids.size + unknown) =
        FrameObservation(true, ids.associateWith { strong }, unknown, bodies, faces)

    @Test
    fun presentNeedsTwoFramesOrOneStrong() {
        val a = AttendanceAggregator(3)
        a.add(frame(0))
        a.add(frame(0, 1))
        a.add(frame(2, strong = true))
        a.add(frame())
        val r = a.result()
        assertEquals(listOf(Status.PRESENT, Status.ABSENT, Status.PRESENT), r.statuses)
    }

    @Test
    fun absentOnlyWhenNobodyIsUnexplained() {
        val a = AttendanceAggregator(3)
        repeat(4) { a.add(frame(0, 1, unknown = 1)) } // someone the board could not recognise
        assertEquals(listOf(Status.PRESENT, Status.PRESENT, Status.NEEDS_REVIEW), a.result().statuses)
    }

    @Test
    fun sleepingRecognisedStudentExplainsAFacelessBody() {
        val a = AttendanceAggregator(3)
        a.add(frame(0, 1, bodies = 2, faces = 2))
        a.add(frame(0, 1, bodies = 2, faces = 2))
        // Student 1 puts their head down: 2 bodies, 1 face. Still explained by student 1.
        repeat(3) { a.add(frame(0, bodies = 2, faces = 1)) }
        assertEquals(listOf(Status.PRESENT, Status.PRESENT, Status.ABSENT), a.result().statuses)
    }

    @Test
    fun facelessBodyNotExplainedMeansReview() {
        val a = AttendanceAggregator(3)
        repeat(4) { a.add(frame(0, 1, bodies = 3, faces = 2)) }
        assertEquals(Status.NEEDS_REVIEW, a.result().statuses[2])
    }

    @Test
    fun tooFewGoodFramesOrNoneAtAll() {
        val a = AttendanceAggregator(2, minValidFrames = 3)
        a.add(frame(0, strong = true))
        a.add(FrameObservation(valid = false))
        assertEquals(listOf(Status.PRESENT, Status.NEEDS_REVIEW), a.result().statuses)
        val b = AttendanceAggregator(2)
        b.add(FrameObservation(valid = false))
        assertEquals(listOf(Status.NO_DATA, Status.NO_DATA), b.result().statuses)
    }

    @Test
    fun earlyStopWhenEveryoneIsPresent() {
        val a = AttendanceAggregator(2)
        a.add(frame(0, 1, strong = true))
        assertEquals(true, a.allPresent())
    }
}
