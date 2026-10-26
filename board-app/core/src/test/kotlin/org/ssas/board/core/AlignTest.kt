package org.ssas.board.core

import kotlin.test.Test
import kotlin.test.assertEquals

class AlignTest {
    @Test
    fun identityWhenPointsMatch() {
        val m = Align.similarity(Align.ARCFACE_DST, Align.ARCFACE_DST)
        val expected = doubleArrayOf(1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        for (i in m.indices) assertEquals(expected[i], m[i], 1e-9)
    }

    @Test
    fun recoversScaleRotationTranslation() {
        val angle = Math.toRadians(17.0)
        val s = 2.5
        val src = DoubleArray(10)
        for (i in 0 until 5) {
            val x = Align.ARCFACE_DST[2 * i]
            val y = Align.ARCFACE_DST[2 * i + 1]
            src[2 * i] = s * (Math.cos(angle) * x - Math.sin(angle) * y) + 40
            src[2 * i + 1] = s * (Math.sin(angle) * x + Math.cos(angle) * y) - 12
        }
        val m = Align.similarity(src, Align.ARCFACE_DST)
        for (i in 0 until 5) {
            val x = m[0] * src[2 * i] + m[1] * src[2 * i + 1] + m[2]
            val y = m[3] * src[2 * i] + m[4] * src[2 * i + 1] + m[5]
            assertEquals(Align.ARCFACE_DST[2 * i], x, 1e-6)
            assertEquals(Align.ARCFACE_DST[2 * i + 1], y, 1e-6)
        }
    }
}
